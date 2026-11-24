import os
import re
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase

from rappen.core import reference
from rappen.qr import build_qr_bill, payment_part_html, recipient_lines, set_payment_reference
from rappen.tests import utils

MM = 72 / 25.4  # PDF points per millimetre


class TestQrBill(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = utils.swiss_company()
		cls.qr_account = utils.bank_account(cls.company, "Rappen QR", qr_iban=utils.QR_IBAN, default=True)
		cls.iban_account = utils.bank_account(cls.company, "Rappen IBAN", iban=utils.OTHER_IBAN)

	def test_qr_reference_from_invoice_number(self):
		invoice = utils.sales_invoice(self.company)
		self.assertEqual(invoice.rappen_bank_account, self.qr_account)
		self.assertEqual(invoice.rappen_reference_type, reference.QRR)
		self.assertEqual(
			reference.validate_qrr(invoice.rappen_payment_reference), invoice.rappen_payment_reference
		)
		digits = re.sub(r"\D", "", invoice.name)
		self.assertTrue(invoice.rappen_payment_reference[:-1].endswith("1" + digits))

	def test_recipient_without_country_within_switzerland(self):
		invoice = utils.sales_invoice(self.company, submit=False)
		self.assertEqual(recipient_lines(invoice), ["Route de Genève 7bis", "1260 Nyon"])

	def test_recipient_with_country_abroad(self):
		address = frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": "Rappen Ausland",
				"address_type": "Billing",
				"address_line1": "Musterweg 3",
				"pincode": "79539",
				"city": "Lörrach",
				"country": "Germany",
			}
		).insert()
		invoice = frappe._dict(company=self.company, customer_address=address.name)
		self.assertEqual(recipient_lines(invoice)[:2], ["Musterweg 3", "79539 Lörrach"])
		self.assertEqual(len(recipient_lines(invoice)), 3)

	def test_creditor_reference_for_iban_account(self):
		invoice = utils.sales_invoice(self.company, rappen_bank_account=self.iban_account)
		self.assertEqual(invoice.rappen_reference_type, reference.SCOR)
		self.assertTrue(invoice.rappen_payment_reference.startswith("RF"))
		reference.validate_scor(invoice.rappen_payment_reference)

	def test_reference_is_stable_and_unique(self):
		invoice = utils.sales_invoice(self.company, submit=False)
		first = invoice.rappen_payment_reference
		invoice.save()
		self.assertEqual(invoice.rappen_payment_reference, first)
		other = utils.sales_invoice(self.company, submit=False)
		self.assertNotEqual(other.rappen_payment_reference, first)

	def test_no_reference_in_other_currencies(self):
		invoice = utils.sales_invoice(self.company, submit=False)
		invoice.currency = "USD"
		set_payment_reference(invoice)
		self.assertEqual(invoice.rappen_reference_type, reference.NON)
		self.assertEqual(invoice.rappen_payment_reference, "")
		self.assertEqual(str(payment_part_html(invoice)), "")

	def test_no_payment_part_on_credit_notes(self):
		invoice = utils.sales_invoice(self.company, submit=False)
		invoice.is_return = 1
		set_payment_reference(invoice)
		self.assertEqual(invoice.rappen_reference_type, reference.NON)

	def test_qr_bill_content(self):
		invoice = utils.sales_invoice(self.company)
		bill = build_qr_bill(invoice).validate()
		self.assertEqual(bill.account, utils.QR_IBAN)
		self.assertEqual(str(bill.amount), "1949.75")
		self.assertEqual(bill.debtor.street, "Route de Genève")
		self.assertEqual(bill.debtor.building_number, "7bis")
		self.assertEqual(bill.creditor.town, "Zürich")
		self.assertIn(invoice.name, bill.message)
		self.assertTrue(bill.billing_information.startswith("//S1/10/"))

	def test_payment_part_in_german(self):
		invoice = utils.sales_invoice(self.company)
		html = str(payment_part_html(invoice, language="de"))
		self.assertIn("Zahlteil", html)
		self.assertIn("Empfangsschein", html)
		self.assertIn("CH44 3199 9123 0008 8901 2", html)
		self.assertIn("1 949.75", html)
		self.assertIn("<svg", html)
		self.assertIn(reference.format_qrr(invoice.rappen_payment_reference), html)

	def test_payment_part_shows_problems(self):
		invoice = utils.sales_invoice(self.company, submit=False)
		invoice.rappen_bank_account = None
		html = str(payment_part_html(invoice, language="en"))
		self.assertIn("cannot be paid", html)
		self.assertNotIn("<svg", html)

	def test_pdf(self):
		"""The payment part sits at the bottom of the last page, as the guidelines require."""
		from pypdf import PdfReader

		invoice = utils.sales_invoice(self.company, language="de")
		pdf = frappe.get_print("Sales Invoice", invoice.name, "Sales Invoice QR-bill", as_pdf=True)
		target = os.environ.get("RAPPEN_PDF_DIR")
		if target:
			Path(target).mkdir(parents=True, exist_ok=True)
			Path(target, "sales-invoice-qr-bill.pdf").write_bytes(pdf)

		reader = PdfReader(_bytes_io(pdf))
		page = reader.pages[-1]
		self.assertAlmostEqual(float(page.mediabox.height), 297 * MM, delta=1)
		positions = {}

		def visit(text, cm, tm, font, size):
			if text.strip() in ("Zahlteil", "Empfangsschein"):
				# Position on the page: text matrix times current transformation matrix
				x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
				y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
				positions[text.strip()] = (x, y)

		page.extract_text(visitor_text=visit)
		self.assertIn("Zahlteil", positions, page.extract_text())
		x, y = positions["Zahlteil"]
		# Title of the payment part: 5 mm from the left edge of the payment part (62 mm) and below its top edge
		self.assertAlmostEqual(x, 67 * MM, delta=2 * MM)
		self.assertTrue(85 * MM < y < 100 * MM, f"Zahlteil at {y / MM:.1f} mm from the bottom")
		x, y = positions["Empfangsschein"]
		self.assertAlmostEqual(x, 5 * MM, delta=2 * MM)


def _bytes_io(data: bytes):
	from io import BytesIO

	return BytesIO(data)
