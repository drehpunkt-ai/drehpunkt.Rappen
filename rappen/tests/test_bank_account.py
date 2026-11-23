import frappe
from frappe.tests import IntegrationTestCase

# Sample IBANs from the SIX implementation guidelines, no real accounts
IBAN = "CH9300762011623852957"
QR_IBAN = "CH4431999123000889012"


def bank_account(**fields):
	if not frappe.db.exists("Bank", "Rappen Test Bank"):
		frappe.get_doc({"doctype": "Bank", "bank_name": "Rappen Test Bank"}).insert()
	return frappe.get_doc(
		{
			"doctype": "Bank Account",
			"account_name": f"Rappen {frappe.generate_hash(length=8)}",
			"bank": "Rappen Test Bank",
			**fields,
		}
	)


class TestBankAccount(IntegrationTestCase):
	def test_valid_accounts(self):
		account = bank_account(
			iban="ch93 0076 2011 6238 5295 7", rappen_qr_iban=QR_IBAN, rappen_qr_reference_prefix=" 123456 "
		).insert()
		self.assertEqual(account.iban, IBAN)
		self.assertEqual(account.rappen_qr_iban, QR_IBAN)
		self.assertEqual(account.rappen_qr_reference_prefix, "123456")

	def test_iban_with_wrong_length(self):
		with self.assertRaises(frappe.ValidationError):
			bank_account(iban="CH93 0076 2011 6238 5295").insert()

	def test_qr_iban_in_iban_field(self):
		with self.assertRaisesRegex(frappe.ValidationError, "QR-IBAN"):
			bank_account(iban=QR_IBAN).insert()

	def test_regular_iban_in_qr_iban_field(self):
		with self.assertRaisesRegex(frappe.ValidationError, "QR-IBAN"):
			bank_account(iban=IBAN, rappen_qr_iban=IBAN).insert()

	def test_prefix_needs_qr_iban(self):
		with self.assertRaises(frappe.ValidationError):
			bank_account(iban=IBAN, rappen_qr_reference_prefix="123456").insert()

	def test_prefix_digits_only(self):
		for prefix in ("12a456", "12345678901"):
			with self.subTest(prefix=prefix):
				with self.assertRaises(frappe.ValidationError):
					bank_account(rappen_qr_iban=QR_IBAN, rappen_qr_reference_prefix=prefix).insert()
