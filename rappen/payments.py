"""Outgoing payments: payment proposals from open purchase invoices, the pain.001 file and payment entries."""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, getdate, now_datetime, nowdate

from rappen.core import iban, pain001, qrbill, reference, schemas
from rappen.core.address import Address
from rappen.core.errors import RappenError
from rappen.utils import country_code, translate

SCHEMA = "pain.001.001.09.ch.03.xsd"


# Purchase Invoice: QR-bill of the supplier


def read_supplier_qr_bill(doc, method=None):
	"""Validate of Purchase Invoice: take IBAN and reference from the scanned QR-bill."""
	content = (doc.get("rappen_qr_code") or "").strip()
	if content and (doc.has_value_changed("rappen_qr_code") or not doc.get("rappen_creditor_iban")):
		try:
			bill = qrbill.parse(content)
			iban.validate_iban(bill.account)
			bill_type = bill.reference_type
		except RappenError as error:
			frappe.throw(translate(error), title=_("QR-bill of the supplier"))
		doc.rappen_creditor_iban = bill.account
		doc.rappen_payment_reference = bill.reference if bill_type != reference.NON else ""
		if bill.currency != doc.currency:
			frappe.throw(
				_("The QR-bill is in {0}, the invoice in {1}.").format(bill.currency, doc.currency),
				title=_("QR-bill of the supplier"),
			)
		total = flt(doc.rounded_total) or flt(doc.grand_total)
		if bill.amount is not None and abs(float(bill.amount) - total) >= 0.005:
			frappe.msgprint(
				_("The QR-bill asks for {0} {1}, the invoice totals {0} {2}.").format(
					bill.currency,
					qrbill.format_amount(bill.amount),
					qrbill.format_amount(qrbill.parse_amount(total)),
				),
				title=_("QR-bill of the supplier"),
				indicator="orange",
			)
	if doc.get("rappen_creditor_iban"):
		try:
			doc.rappen_creditor_iban = iban.validate_iban(doc.rappen_creditor_iban)
		except RappenError as error:
			frappe.throw(translate(error), title=_("Invalid IBAN"))
	if doc.get("rappen_payment_reference"):
		try:
			reference.reference_type(doc.rappen_payment_reference)
			doc.rappen_payment_reference = reference.compact(doc.rappen_payment_reference)
		except RappenError as error:
			frappe.throw(translate(error), title=_("QR-bill of the supplier"))


def supplier_iban(supplier: str) -> str | None:
	"""IBAN of the supplier's default bank account, or of its only one."""
	accounts = frappe.get_all(
		"Bank Account",
		filters={"party_type": "Supplier", "party": supplier, "disabled": 0},
		fields=["iban", "is_default"],
		order_by="is_default desc, creation asc",
	)
	return accounts[0].iban if accounts and accounts[0].iban else None


def creditor_address(invoice) -> Address:
	"""The creditor as on the supplier's QR-bill, otherwise from the address on the invoice or the supplier."""
	content = (invoice.get("rappen_qr_code") or "").strip()
	if content:
		try:
			return qrbill.parse(content).creditor
		except RappenError:
			pass
	address_name = invoice.get("supplier_address")
	if not address_name:
		from frappe.contacts.doctype.address.address import get_default_address

		address_name = get_default_address("Supplier", invoice.supplier)
	values = (
		frappe.db.get_value(
			"Address", address_name, ["address_line1", "pincode", "city", "country"], as_dict=True
		)
		if address_name
		else None
	)
	if not values:
		return Address(name=invoice.supplier_name)
	return Address.from_line(
		invoice.supplier_name, values.address_line1, values.pincode, values.city, country_code(values.country)
	)


# Payment Proposal


def open_invoices(proposal) -> list[dict]:
	"""Rows for the open purchase invoices of the company that are due until ``due_until``."""
	filters = {
		"company": proposal.company,
		"docstatus": 1,
		"outstanding_amount": (">", 0),
		"currency": ("in", list(qrbill.CURRENCIES)),
		"is_return": 0,
	}
	if proposal.due_until:
		filters["due_date"] = ("<=", proposal.due_until)
	in_other_proposals = set(
		frappe.get_all(
			"Payment Proposal Item",
			filters={"docstatus": 0, "parent": ("!=", proposal.name or "")},
			pluck="purchase_invoice",
		)
	)
	present = {row.purchase_invoice for row in proposal.items}
	rows = []
	for invoice in frappe.get_all(
		"Purchase Invoice",
		filters=filters,
		fields=["name", "on_hold", "release_date"],
		order_by="due_date asc, name asc",
	):
		if invoice.name in present or invoice.name in in_other_proposals:
			continue
		if invoice.on_hold and (
			not invoice.release_date or getdate(invoice.release_date) > getdate(nowdate())
		):
			continue
		rows.append(item_for(frappe.get_doc("Purchase Invoice", invoice.name)))
	return rows


def item_for(invoice) -> dict:
	account = invoice.get("rappen_creditor_iban") or supplier_iban(invoice.supplier) or ""
	payment_reference = invoice.get("rappen_payment_reference") or ""
	return {
		"purchase_invoice": invoice.name,
		"supplier": invoice.supplier,
		"supplier_name": invoice.supplier_name,
		"due_date": invoice.due_date,
		"currency": invoice.currency,
		"outstanding_amount": invoice.outstanding_amount,
		"amount": invoice.outstanding_amount,
		"creditor_iban": account,
		"payment_reference": payment_reference,
		"message": "" if payment_reference else (invoice.bill_no or invoice.name)[:140],
	}


def build_run(proposal) -> pain001.PaymentRun:
	company_name = frappe.get_cached_value("Company", proposal.company, "company_name") or proposal.company
	from erpnext.setup.doctype.company.company import get_default_company_address

	address_name = get_default_company_address(proposal.company)
	values = (
		frappe.db.get_value(
			"Address", address_name, ["address_line1", "pincode", "city", "country"], as_dict=True
		)
		if address_name
		else None
	)
	debtor = (
		Address.from_line(
			company_name, values.address_line1, values.pincode, values.city, country_code(values.country)
		)
		if values
		else Address(name=company_name)
	)
	account = frappe.db.get_value("Bank Account", proposal.bank_account, ["iban", "bank"], as_dict=True)
	bic = frappe.db.get_value("Bank", account.bank, "swift_number") if account.bank else ""
	payments = []
	for row in proposal.items:
		invoice = frappe.get_doc("Purchase Invoice", row.purchase_invoice)
		payments.append(
			pain001.Payment(
				end_to_end_id=row.end_to_end_id or end_to_end_id(proposal, row),
				amount=flt(row.amount),
				currency=row.currency,
				creditor=creditor_address(invoice),
				creditor_iban=row.creditor_iban or "",
				reference=row.payment_reference or "",
				message=row.message or "",
			)
		)
	return pain001.PaymentRun(
		message_id=proposal.name,
		created=get_datetime(proposal.get("creation") or now_datetime()),
		execution_date=getdate(proposal.execution_date),
		debtor=debtor,
		debtor_iban=account.iban or "",
		debtor_bic=(bic or "").replace(" ", ""),
		payments=tuple(payments),
	)


def end_to_end_id(proposal, row) -> str:
	return f"{proposal.name}-{row.idx}"[: pain001.ID_MAX]


def update_items(proposal):
	"""Payment type and end-to-end ID of every row, totals per currency."""
	for row in proposal.items:
		row.creditor_iban = iban.compact(row.creditor_iban) if row.creditor_iban else row.creditor_iban
		row.payment_reference = reference.compact(row.payment_reference) if row.payment_reference else ""
		row.end_to_end_id = end_to_end_id(proposal, row)
		try:
			kind = pain001.Payment(
				end_to_end_id=row.end_to_end_id,
				amount=flt(row.amount) or 0,
				currency=row.currency or "",
				creditor=Address(name=row.supplier_name or ""),
				creditor_iban=row.creditor_iban or "",
				reference=row.payment_reference,
			).payment_type
		except Exception:
			kind = None
		row.payment_type = kind or ""
	proposal.total_chf = sum(flt(r.amount) for r in proposal.items if r.currency == "CHF")
	proposal.total_eur = sum(flt(r.amount) for r in proposal.items if r.currency == "EUR")


def check(proposal):
	"""Throw all problems of the proposal at once, in the user's language."""
	problems = []
	for row in proposal.items:
		if flt(row.amount) > flt(row.outstanding_amount) + 0.005:
			problems.append(
				_("Row {0}: {1} is more than the outstanding amount of {2}.").format(
					row.idx, row.amount, row.purchase_invoice
				)
			)
		if not row.creditor_iban:
			problems.append(
				_("Row {0}: {1} has no IBAN. Scan the QR-bill or add a bank account to the supplier.").format(
					row.idx, row.supplier_name
				)
			)
	if not problems:
		problems = [translate(problem) for problem in build_run(proposal).problems()]
	if problems:
		frappe.throw(
			"<br>".join(frappe.utils.escape_html(p) for p in problems), title=_("Payment file not possible")
		)


def create_file(proposal) -> str:
	xml = build_run(proposal).to_xml()
	try:
		schemas.validate(xml, SCHEMA)
	except RappenError as error:
		frappe.throw(translate(error), title=_("Payment file not possible"))
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{proposal.name}.xml",
			"content": xml,
			"is_private": 1,
			"attached_to_doctype": proposal.doctype,
			"attached_to_name": proposal.name,
			"attached_to_field": "payment_file",
		}
	).insert()
	return file.file_url


def create_payment_entries(proposal):
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	ledger_account = frappe.db.get_value("Bank Account", proposal.bank_account, "account")
	for row in proposal.items:
		payment = get_payment_entry(
			"Purchase Invoice",
			row.purchase_invoice,
			party_amount=flt(row.amount),
			bank_account=ledger_account,
			reference_date=proposal.execution_date,
		)
		payment.posting_date = proposal.execution_date
		payment.reference_no = row.end_to_end_id
		payment.reference_date = proposal.execution_date
		payment.bank_account = proposal.bank_account
		payment.insert()
		payment.submit()
		row.db_set("payment_entry", payment.name)


def cancel_payment_entries(proposal):
	for row in proposal.items:
		if not row.payment_entry:
			continue
		payment = frappe.get_doc("Payment Entry", row.payment_entry)
		if payment.docstatus != 1:
			continue
		if payment.clearance_date:
			frappe.throw(
				_("Payment Entry {0} is reconciled with the bank already and cannot be cancelled.").format(
					payment.name
				)
			)
		payment.cancel()
