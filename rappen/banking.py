"""Incoming camt files: Bank Transactions, matching by payment reference and booking of exact matches."""

from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import flt

from rappen.core import camt
from rappen.core.iban import compact

REFERENCE_DOCTYPES = ("Sales Invoice", "Dunning")


def find_bank_account(company: str, iban: str, preset: str | None = None) -> str:
	"""The company's Bank Account with this IBAN (or QR-IBAN)."""
	iban = compact(iban)
	if preset:
		values = frappe.db.get_value(
			"Bank Account", preset, ["iban", "rappen_qr_iban", "company"], as_dict=True
		)
		if not values or iban not in (compact(values.iban), compact(values.rappen_qr_iban)):
			frappe.throw(
				_("The file is for the account {0}, but Bank Account {1} has a different IBAN.").format(
					iban, preset
				)
			)
		return preset
	for field in ("iban", "rappen_qr_iban"):
		name = frappe.db.get_value(
			"Bank Account", {field: iban, "company": company, "is_company_account": 1, "disabled": 0}, "name"
		)
		if name:
			return name
	frappe.throw(
		_(
			"No bank account of company {0} has the IBAN {1}. Create it or enter the IBAN on the Bank Account."
		).format(company, iban)
	)


def find_document(value: str, company: str) -> tuple[str, str] | tuple[None, None]:
	"""Submitted Sales Invoice or Dunning with this payment reference."""
	if not value:
		return None, None
	for doctype in REFERENCE_DOCTYPES:
		name = frappe.db.get_value(
			doctype, {"rappen_payment_reference": value, "docstatus": 1, "company": company}, "name"
		)
		if name:
			return doctype, name
	return None, None


def amount_due(doctype: str, name: str) -> float:
	if doctype == "Dunning":
		doc = frappe.get_doc("Dunning", name)
		if doc.status in ("Resolved", "Cancelled") or doc.get_settled_successor():
			return 0.0
		return flt(doc.grand_total)
	return flt(frappe.db.get_value("Sales Invoice", name, "outstanding_amount"))


class Importer:
	"""Imports the statements of one camt file for one company."""

	def __init__(self, import_doc):
		self.doc = import_doc
		self.auto_book = frappe.db.get_single_value("Rappen Settings", "book_exact_matches")

	def run(self, statements: list[camt.Statement]):
		first = statements[0]
		bank_account = find_bank_account(self.doc.company, first.account_iban, self.doc.bank_account)
		self.doc.bank_account = bank_account
		self.doc.kind = first.kind
		self.doc.message_id = first.message_id
		self.doc.from_date = min((s.from_date for s in statements if s.from_date), default=None)
		self.doc.to_date = max((s.to_date for s in statements if s.to_date), default=None)
		self.doc.currency = first.currency
		self.doc.opening_balance = first.opening_balance
		self.doc.closing_balance = statements[-1].closing_balance
		self.doc.transactions = []

		for statement in statements:
			account = find_bank_account(self.doc.company, statement.account_iban, None)
			if account != bank_account:
				frappe.throw(_("The file contains statements of more than one account."))
			for transaction in statement.transactions:
				self.import_transaction(transaction, bank_account)

		rows = self.doc.transactions
		self.doc.created = sum(r.result in ("Created", "Booked", "Replaced batch") for r in rows)
		self.doc.booked = sum(r.result == "Booked" for r in rows)
		self.doc.duplicates = sum(r.result in ("Already imported", "Skipped") for r in rows)
		self.doc.errors = sum(r.result == "Error" for r in rows)
		self.doc.status = "Imported with errors" if self.doc.errors else "Imported"

	def import_transaction(self, transaction: camt.Transaction, bank_account: str):
		row = self.doc.append(
			"transactions",
			{
				"transaction_id": transaction.transaction_id,
				"booking_date": transaction.booking_date,
				"amount": float(transaction.amount if transaction.credit else -transaction.amount),
				"reference": transaction.reference or transaction.end_to_end_id,
				"party_name": transaction.party_name,
			},
		)
		savepoint = "rappen_camt_transaction"
		frappe.db.savepoint(savepoint)
		try:
			self._import(transaction, bank_account, row)
		except Exception as error:
			frappe.db.rollback(save_point=savepoint)
			row.result = "Error"
			row.message = str(error)[:1000]
			frappe.clear_last_message()

	def _import(self, transaction: camt.Transaction, bank_account: str, row):
		existing = frappe.db.get_value(
			"Bank Transaction",
			{"bank_account": bank_account, "transaction_id": transaction.transaction_id, "docstatus": 1},
			"name",
		)
		if existing:
			row.result, row.bank_transaction = "Already imported", existing
			return

		if transaction.batch:
			if frappe.db.exists(
				"Bank Transaction",
				{
					"bank_account": bank_account,
					"rappen_entry_reference": transaction.entry_reference,
					"docstatus": 1,
				},
			):
				row.result = "Skipped"
				row.message = _("The single payments of this batch were imported already.")
				return
		else:
			replaced = self._replace_batch(transaction, bank_account)
			if replaced is False:
				row.result = "Skipped"
				row.message = _(
					"The batch entry of these payments is reconciled already, so they are not imported again."
				)
				return

		document_type, document = (None, None)
		if transaction.credit:
			document_type, document = find_document(transaction.reference, self.doc.company)

		bank_transaction = frappe.get_doc(
			{
				"doctype": "Bank Transaction",
				"date": transaction.booking_date,
				"bank_account": bank_account,
				"company": self.doc.company,
				"currency": transaction.currency,
				"deposit": float(transaction.amount) if transaction.credit else 0,
				"withdrawal": 0 if transaction.credit else float(transaction.amount),
				"description": _description(transaction),
				"reference_number": transaction.reference
				or transaction.end_to_end_id
				or transaction.entry_reference,
				"transaction_id": transaction.transaction_id,
				"transaction_type": transaction.bank_transaction_code,
				"bank_party_name": transaction.party_name,
				"bank_party_iban": transaction.party_iban or None,
				"included_fee": float(transaction.charges) if transaction.charges else 0,
				"rappen_entry_reference": transaction.entry_reference,
				"rappen_camt_import": self.doc.name,
				"rappen_document_type": document_type,
				"rappen_document": document,
			}
		)
		if document:
			bank_transaction.party_type = "Customer"
			bank_transaction.party = frappe.db.get_value(document_type, document, "customer")
		bank_transaction.insert()
		bank_transaction.submit()

		row.bank_transaction = bank_transaction.name
		row.document_type, row.document = document_type, document
		row.result = "Replaced batch" if replaced else "Created"

		if document and self.auto_book and _equal(transaction.amount, amount_due(document_type, document)):
			row.payment_entry = book_payment(bank_transaction)
			row.result = "Booked"

	def _replace_batch(self, transaction: camt.Transaction, bank_account: str) -> bool | None:
		"""Cancel the batch entry that these details replace. False if it is reconciled already."""
		summary = frappe.db.get_value(
			"Bank Transaction",
			{
				"bank_account": bank_account,
				"transaction_id": transaction.entry_reference,
				"rappen_entry_reference": transaction.entry_reference,
				"docstatus": 1,
			},
			["name", "allocated_amount"],
			as_dict=True,
		)
		if not summary:
			return None
		if flt(summary.allocated_amount):
			return False
		frappe.get_doc("Bank Transaction", summary.name).cancel()
		return True


def _equal(amount: Decimal, due: float) -> bool:
	return due > 0 and abs(float(amount) - due) < 0.005


def _description(transaction: camt.Transaction) -> str:
	parts = [transaction.party_name, transaction.message]
	if transaction.batch:
		parts.append(_("Batch of {0} payments").format(transaction.batch_count))
	if transaction.reversal:
		parts.append(_("Reversal", context="Rappen"))
	return " | ".join(part for part in parts if part)


def book_payment(bank_transaction, amount: float | None = None) -> str:
	"""Create a Payment Entry for the document of a Bank Transaction and reconcile the two.

	``amount`` defaults to the unallocated amount of the Bank Transaction. A payment above the amount due
	stays on the customer as an unallocated advance.
	"""
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	if isinstance(bank_transaction, str):
		bank_transaction = frappe.get_doc("Bank Transaction", bank_transaction)
	if not bank_transaction.rappen_document:
		frappe.throw(_("Bank Transaction {0} has no matching document.").format(bank_transaction.name))
	if flt(bank_transaction.deposit) <= 0:
		frappe.throw(_("Only incoming payments can be booked against an invoice or dunning."))

	amount = flt(amount) or flt(bank_transaction.unallocated_amount)
	if amount <= 0:
		frappe.throw(_("Bank Transaction {0} is reconciled already.").format(bank_transaction.name))
	ledger_account = frappe.db.get_value("Bank Account", bank_transaction.bank_account, "account")
	payment = get_payment_entry(
		bank_transaction.rappen_document_type,
		bank_transaction.rappen_document,
		party_amount=amount,
		bank_account=ledger_account,
		bank_amount=amount,
		reference_date=bank_transaction.date,
	)
	payment.posting_date = bank_transaction.date
	payment.reference_no = bank_transaction.reference_number
	payment.reference_date = bank_transaction.date
	payment.bank_account = bank_transaction.bank_account
	payment.insert()
	payment.submit()

	bank_transaction.add_payment_entries([{"payment_doctype": "Payment Entry", "payment_name": payment.name}])
	bank_transaction.save()
	return payment.name


@frappe.whitelist()
def book_against_document(bank_transaction: str) -> str:
	"""Button on the Bank Transaction: book the payment against its invoice or dunning."""
	frappe.has_permission("Bank Transaction", "write", bank_transaction, throw=True)
	return book_payment(bank_transaction)
