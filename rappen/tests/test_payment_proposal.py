import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, today
from frappe.utils.file_manager import get_file

from rappen.core import schemas
from rappen.tests import utils
from rappen.tests.test_camt_import import camt_file, run_import

SUPPLIER = "Lieferant Muster AG"
SUPPLIER_IBAN = "CH5604835012345678009"
QR_BILL = "\n".join(
	[
		"SPC",
		"0200",
		"1",
		"CH4431999123000889012",
		"S",
		"Druckerei Beispiel AG",
		"Industriestrasse",
		"3",
		"3000",
		"Bern",
		"CH",
		*[""] * 7,
		"{amount}",
		"CHF",
		*[""] * 7,
		"QRR",
		"210000000003139471430009017",
		"Rechnung 4711",
		"EPD",
	]
)


def supplier() -> str:
	if not frappe.db.exists("Supplier", SUPPLIER):
		frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": SUPPLIER,
				"supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
			}
		).insert()
		frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": SUPPLIER,
				"address_type": "Billing",
				"address_line1": "Werkstrasse 5",
				"pincode": "6003",
				"city": "Luzern",
				"country": "Switzerland",
				"is_primary_address": 1,
				"links": [{"link_doctype": "Supplier", "link_name": SUPPLIER}],
			}
		).insert()
		if not frappe.db.exists("Bank", utils.BANK):
			frappe.get_doc({"doctype": "Bank", "bank_name": utils.BANK}).insert()
		frappe.get_doc(
			{
				"doctype": "Bank Account",
				"account_name": SUPPLIER,
				"bank": utils.BANK,
				"party_type": "Supplier",
				"party": SUPPLIER,
				"iban": SUPPLIER_IBAN,
				"is_default": 1,
			}
		).insert()
	return SUPPLIER


def purchase_invoice(company: str, rate: float, **fields):
	invoice = frappe.get_doc(
		{
			"doctype": "Purchase Invoice",
			"company": company,
			"supplier": supplier(),
			"posting_date": today(),
			"bill_no": f"R-{frappe.generate_hash(length=5)}",
			"due_date": add_days(today(), 10),
			"currency": "CHF",
			"items": [{"item_code": utils.item(), "qty": 1, "rate": rate}],
			**fields,
		}
	)
	invoice.set_missing_values()
	invoice.insert()
	invoice.submit()
	return invoice


class TestPaymentProposal(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = utils.swiss_company()
		cls.bank_account = utils.bank_account(cls.company, "Rappen QR", qr_iban=utils.QR_IBAN, default=True)
		utils.company_address(cls.company)

	def proposal(self, *invoices):
		doc = frappe.get_doc(
			{
				"doctype": "Payment Proposal",
				"company": self.company,
				"bank_account": self.bank_account,
				"execution_date": today(),
				"items": [
					{"purchase_invoice": invoice.name, "amount": invoice.outstanding_amount}
					for invoice in invoices
				],
			}
		)
		for row, invoice in zip(doc.items, invoices, strict=True):
			from rappen.payments import item_for

			row.update(item_for(invoice))
		return doc.insert()

	def test_qr_bill_of_supplier(self):
		invoice = purchase_invoice(self.company, 250, rappen_qr_code=QR_BILL.format(amount="250.00"))
		self.assertEqual(invoice.rappen_creditor_iban, utils.QR_IBAN)
		self.assertEqual(invoice.rappen_payment_reference, "210000000003139471430009017")

	def test_wrong_qr_code(self):
		with self.assertRaises(frappe.ValidationError):
			purchase_invoice(self.company, 250, rappen_qr_code="https://example.org")

	def test_payment_file_and_entries(self):
		with_qr = purchase_invoice(self.company, 250, rappen_qr_code=QR_BILL.format(amount="250.00"))
		with_iban = purchase_invoice(self.company, 80)
		doc = self.proposal(with_qr, with_iban)
		self.assertEqual([row.payment_type for row in doc.items], ["QR", "IBAN"])
		self.assertEqual(doc.items[1].creditor_iban, SUPPLIER_IBAN)
		self.assertEqual(flt(doc.total_chf), 330)
		doc.submit()

		xml = get_file(doc.payment_file)[1]
		xml = xml if isinstance(xml, bytes) else xml.encode()
		schemas.validate(xml, "pain.001.001.09.ch.03.xsd")
		self.assertIn(b"<Prtry>QRR</Prtry>", xml)
		self.assertIn(b"<TwnNm>Luzern</TwnNm>", xml)
		self.assertIn(b"<TwnNm>Bern</TwnNm>", xml)

		for row in doc.items:
			self.assertTrue(row.payment_entry)
			self.assertEqual(
				frappe.db.get_value("Payment Entry", row.payment_entry, "reference_no"), row.end_to_end_id
			)
		self.assertEqual(flt(frappe.db.get_value("Purchase Invoice", with_qr.name, "outstanding_amount")), 0)

		# The debit in the statement finds the payment entry by its end-to-end ID
		row = doc.items[1]
		key = frappe.generate_hash(length=6).upper()
		content = camt_file(
			"camt053_v08.xml",
			{
				"PP-2026-00001-1": row.end_to_end_id,
				"500.00": "80.00",
				"TX-": f"TX-{key}-",
				"ENTRY-": f"ENTRY-{key}-",
			},
		)
		result = run_import(self.company, content)
		debit = next(r for r in result.transactions if r.transaction_id.endswith("0004"))
		self.assertEqual(debit.result, "Booked", debit.message)
		self.assertEqual(debit.payment_entry, row.payment_entry)

	def test_get_open_invoices(self):
		invoice = purchase_invoice(self.company, 42)
		doc = frappe.get_doc(
			{
				"doctype": "Payment Proposal",
				"company": self.company,
				"bank_account": self.bank_account,
				"due_until": add_days(today(), 30),
			}
		)
		doc.get_open_invoices()
		self.assertIn(invoice.name, [row.purchase_invoice for row in doc.items])

	def test_missing_iban_is_reported(self):
		invoice = purchase_invoice(self.company, 99)
		doc = self.proposal(invoice)
		doc.items[0].creditor_iban = ""
		doc.save()
		with self.assertRaisesRegex(frappe.ValidationError, "has no IBAN"):
			doc.submit()

	def test_cancel_cancels_payment_entries(self):
		invoice = purchase_invoice(self.company, 55)
		doc = self.proposal(invoice)
		doc.submit()
		doc.cancel()
		self.assertEqual(frappe.db.get_value("Payment Entry", doc.items[0].payment_entry, "docstatus"), 2)
		self.assertEqual(flt(frappe.db.get_value("Purchase Invoice", invoice.name, "outstanding_amount")), 55)
