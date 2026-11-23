from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from rappen.banking import book_payment
from rappen.tests import utils

DATA = Path(__file__).parents[1] / "core" / "tests" / "data"
SAMPLE_QRR = "210000000003139471430009017"


def camt_file(name: str, replacements: dict[str, str]) -> bytes:
	text = (DATA / name).read_text(encoding="utf-8")
	for old, new in replacements.items():
		text = text.replace(old, new)
	return text.encode()


def run_import(company: str, content: bytes):
	doc = frappe.get_doc({"doctype": "CAMT Import", "company": company, "file": "/private/files/placeholder"})
	doc.flags.ignore_mandatory = True
	doc.insert()
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{doc.name}.xml",
			"content": content,
			"is_private": 1,
			"attached_to_doctype": "CAMT Import",
			"attached_to_name": doc.name,
		}
	).insert()
	doc.file = file.file_url
	doc.save()
	doc.run_import()
	return doc.reload()


class TestCamtImport(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = utils.swiss_company()
		cls.bank_account = utils.bank_account(cls.company, "Rappen QR", qr_iban=utils.QR_IBAN, default=True)
		frappe.db.set_single_value("Rappen Settings", "book_exact_matches", 1)

	def unique(self) -> dict[str, str]:
		"""Transaction and entry references that no other test uses."""
		key = frappe.generate_hash(length=6).upper()
		return {"TX-": f"TX-{key}-", "ENTRY-": f"ENTRY-{key}-"}

	def rows(self, doc) -> dict[str, object]:
		return {row.transaction_id.split("-")[-1]: row for row in doc.transactions}

	def test_exact_payment_is_booked(self):
		invoice = utils.sales_invoice(self.company, rate=1949.75)
		content = camt_file(
			"camt053_v08.xml", {**self.unique(), SAMPLE_QRR: invoice.rappen_payment_reference}
		)
		doc = run_import(self.company, content)

		self.assertEqual(doc.status, "Imported")
		self.assertEqual(doc.bank_account, self.bank_account)
		self.assertEqual(doc.kind, "camt.053")
		self.assertEqual(flt(doc.closing_balance), 11899.75)
		rows = self.rows(doc)
		self.assertEqual(rows["0001"].result, "Booked")
		self.assertEqual(rows["0001"].document, invoice.name)
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", invoice.name, "outstanding_amount")), 0)
		self.assertEqual(
			frappe.db.get_value("Bank Transaction", rows["0001"].bank_transaction, "status"), "Reconciled"
		)
		payment = frappe.get_doc("Payment Entry", rows["0001"].payment_entry)
		self.assertEqual(payment.reference_no, invoice.rappen_payment_reference)
		self.assertEqual(flt(payment.paid_amount), 1949.75)

		# The other entries become Bank Transactions without a booking
		self.assertEqual(rows["0002"].result, "Created")
		self.assertEqual(rows["0004"].result, "Created")
		debit = frappe.get_doc("Bank Transaction", rows["0004"].bank_transaction)
		self.assertEqual(flt(debit.withdrawal), 500)
		self.assertEqual(debit.reference_number, "PP-2026-00001-1")
		self.assertEqual(flt(debit.included_fee), 0.5)
		self.assertEqual(doc.created, 5)
		self.assertEqual(doc.booked, 1)

	def test_same_file_twice(self):
		content = camt_file("camt053_v08.xml", self.unique())
		run_import(self.company, content)
		again = run_import(self.company, content)
		self.assertEqual(again.created, 0)
		self.assertEqual(again.duplicates, 5)

	def test_batch_details_replace_the_batch_entry(self):
		unique = self.unique()
		first = run_import(self.company, camt_file("camt053_v08.xml", unique))
		summary = next(row for row in first.transactions if row.transaction_id.endswith("0005"))
		self.assertEqual(
			flt(frappe.db.get_value("Bank Transaction", summary.bank_transaction, "deposit")), 300
		)

		details = run_import(self.company, camt_file("camt054_v08.xml", unique))
		self.assertEqual(
			[row.result for row in details.transactions], ["Replaced batch", "Created", "Created"]
		)
		self.assertEqual(frappe.db.get_value("Bank Transaction", summary.bank_transaction, "docstatus"), 2)

		# The statement again: the batch entry is not created a second time
		again = run_import(self.company, camt_file("camt053_v08.xml", unique))
		summary_again = next(row for row in again.transactions if row.transaction_id.endswith("0005"))
		self.assertEqual(summary_again.result, "Skipped")

	def test_partial_payment_waits_for_a_human(self):
		invoice = utils.sales_invoice(self.company, rate=2500)
		content = camt_file(
			"camt053_v08.xml", {**self.unique(), SAMPLE_QRR: invoice.rappen_payment_reference}
		)
		row = self.rows(run_import(self.company, content))["0001"]
		self.assertEqual(row.result, "Created")
		self.assertEqual(row.document, invoice.name)
		bank_transaction = frappe.get_doc("Bank Transaction", row.bank_transaction)
		self.assertEqual(bank_transaction.party, invoice.customer)

		book_payment(bank_transaction.name)
		self.assertEqual(
			flt(frappe.db.get_value("Sales Invoice", invoice.name, "outstanding_amount")), 550.25
		)
		self.assertEqual(
			frappe.db.get_value("Bank Transaction", bank_transaction.name, "status"), "Reconciled"
		)

	def test_automatic_booking_can_be_switched_off(self):
		frappe.db.set_single_value("Rappen Settings", "book_exact_matches", 0)
		try:
			invoice = utils.sales_invoice(self.company, rate=1949.75)
			content = camt_file(
				"camt053_v08.xml", {**self.unique(), SAMPLE_QRR: invoice.rappen_payment_reference}
			)
			row = self.rows(run_import(self.company, content))["0001"]
			self.assertEqual(row.result, "Created")
			self.assertEqual(row.document, invoice.name)
		finally:
			frappe.db.set_single_value("Rappen Settings", "book_exact_matches", 1)

	def test_unknown_account(self):
		unknown = "CH0804835012345678000"
		content = camt_file("camt053_v08.xml", {**self.unique(), "CH9300762011623852957": unknown})
		with self.assertRaisesRegex(frappe.ValidationError, unknown):
			run_import(self.company, content)

	def test_not_a_camt_file(self):
		doc = run_import(self.company, b"Datum;Betrag\n")
		self.assertEqual(doc.status, "Failed")
		self.assertIn("XML", doc.error_log)
