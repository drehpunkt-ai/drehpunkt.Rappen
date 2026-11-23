import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, today

from rappen.core import reference
from rappen.dunning import LEVELS, create_dunning_types, dunning_title
from rappen.qr import payment_part_html
from rappen.tests import utils
from rappen.tests.test_camt_import import SAMPLE_QRR, camt_file, run_import


def overdue_invoice(company: str, rate: float):
	return utils.sales_invoice(
		company,
		rate=rate,
		posting_date=add_days(today(), -60),
		due_date=add_days(today(), -30),
		set_posting_time=1,
	)


def dunning(invoice, dunning_type: str):
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import create_dunning

	doc = create_dunning(invoice.name)
	doc.dunning_type = dunning_type
	doc.posting_date = today()
	doc.get_dunning_letter_text()
	doc.insert()
	doc.submit()
	return doc


class TestDunning(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = utils.swiss_company()
		utils.bank_account(cls.company, "Rappen QR", qr_iban=utils.QR_IBAN, default=True)
		create_dunning_types(cls.company, fees=[0, 20, 30])
		abbr = frappe.get_cached_value("Company", cls.company, "abbr")
		cls.levels = [f"{level} - {abbr}" for level in LEVELS]

	def test_levels_with_letters(self):
		first = frappe.get_doc("Dunning Type", self.levels[1])
		self.assertEqual(flt(first.dunning_fee), 20)
		languages = {row.language for row in first.dunning_letter_text}
		self.assertTrue({"de", "fr", "it", "en"} <= languages)
		self.assertIn("Mahnung", next(r.body_text for r in first.dunning_letter_text if r.language == "de"))
		# Running it again leaves the existing levels alone
		self.assertEqual(create_dunning_types(self.company, fees=[1, 2, 3]), [])

	def test_dunning_with_qr_bill(self):
		invoice = overdue_invoice(self.company, 100)
		doc = dunning(invoice, self.levels[1])
		self.assertEqual(flt(doc.grand_total), 120)
		self.assertEqual(doc.rappen_reference_type, reference.QRR)
		self.assertNotEqual(doc.rappen_payment_reference, invoice.rappen_payment_reference)
		html = str(payment_part_html(doc, language="de"))
		self.assertIn("120.00", html)
		self.assertIn(reference.format_qrr(doc.rappen_payment_reference), html)
		self.assertEqual(dunning_title(doc), "First dunning")

	def test_payment_of_dunning_settles_invoice_and_fee(self):
		invoice = overdue_invoice(self.company, 100)
		doc = dunning(invoice, self.levels[1])
		content = camt_file(
			"camt053_v08.xml",
			{
				SAMPLE_QRR: doc.rappen_payment_reference,
				"1949.75": "120.00",
				"TX-": f"TX-{doc.name}-",
				"ENTRY-": f"ENTRY-{doc.name}-",
			},
		)
		result = run_import(self.company, content)
		row = next(r for r in result.transactions if r.transaction_id.endswith("0001"))
		self.assertEqual(row.result, "Booked", row.message)
		self.assertEqual(row.document, doc.name)
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", invoice.name, "outstanding_amount")), 0)
		self.assertEqual(frappe.db.get_value("Dunning", doc.name, "status"), "Resolved")

	def test_print_format(self):
		invoice = overdue_invoice(self.company, 100)
		doc = dunning(invoice, self.levels[0])
		html = frappe.get_print("Dunning", doc.name, "Dunning QR-bill")
		self.assertIn("Payment reminder", html)
		self.assertIn(invoice.name, html)
