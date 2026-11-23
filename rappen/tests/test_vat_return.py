import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, get_first_day, get_last_day, today
from frappe.utils.file_manager import get_file

from rappen.core import schemas
from rappen.tests import utils


class TestVatReturn(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = utils.swiss_company()
		frappe.db.set_value("Company", cls.company, "tax_id", "CHE-123.456.788")
		utils.bank_account(cls.company, "Rappen QR", qr_iban=utils.QR_IBAN, default=True)
		cls.template = next(
			(
				name
				for name in frappe.get_all(
					"Sales Taxes and Charges Template", filters={"company": cls.company}, pluck="name"
				)
				if any(
					flt(t.rate) == 8.1 for t in frappe.get_doc("Sales Taxes and Charges Template", name).taxes
				)
			),
			None,
		)

	def test_effective_method_from_the_books(self):
		if not self.template:
			self.skipTest("No sales tax template with 8.1 % from the setup wizard")
		utils.sales_invoice(self.company, rate=1000, taxes_and_charges=self.template)
		doc = frappe.get_doc(
			{
				"doctype": "VAT Return",
				"company": self.company,
				"method": "Effective",
				"period_from": get_first_day(today()),
				"period_till": get_last_day(today()),
			}
		).insert()
		doc.calculate()
		rate = next(r for r in doc.rates if flt(r.rate) == 8.1)
		self.assertGreaterEqual(flt(rate.turnover), 1000)
		self.assertAlmostEqual(flt(rate.tax), flt(rate.turnover) * 0.081, delta=0.01)

		# Invoices without VAT in the same period are assigned by hand, here as exempt supplies
		doc.supplies_exempt_from_tax = doc.untaxed_turnover
		doc.save()
		doc.submit()
		xml = get_file(doc.vat_file)[1]
		xml = xml if isinstance(xml, bytes) else xml.encode()
		schemas.validate(xml, "ech/eCH-0217/2/eCH-0217-2-0-0.xsd")
		self.assertIn(b"<eCH-0217:uid>CHE123456788</eCH-0217:uid>", xml)

	def test_unassigned_turnover_blocks_submit(self):
		doc = frappe.get_doc(
			{
				"doctype": "VAT Return",
				"company": self.company,
				"method": "Effective",
				"period_from": get_first_day(today()),
				"period_till": get_last_day(today()),
				"total_consideration": 1000,
			}
		).insert()
		with self.assertRaisesRegex(frappe.ValidationError, "299"):
			doc.submit()
