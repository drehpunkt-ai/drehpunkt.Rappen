import unittest

from rappen.core import iban
from rappen.core.errors import RappenError

# Sample IBANs from the SIX implementation guidelines and the SWIFT IBAN registry, no real accounts
SIX_IBAN = "CH93 0076 2011 6238 5295 7"
SIX_QR_IBAN = "CH44 3199 9123 0008 8901 2"


class TestIban(unittest.TestCase):
	def test_valid(self):
		for value in (
			SIX_IBAN,
			SIX_QR_IBAN,
			"DE89 3704 0044 0532 0130 00",
			"LI21 0881 0000 2324 013A A",
			"GB29 NWBK 6016 1331 9268 19",
			"NO93 8601 1117 947",
		):
			with self.subTest(value=value):
				self.assertTrue(iban.is_valid_iban(value))

	def test_compact(self):
		self.assertEqual(
			iban.validate_iban(" ch93 0076\N{NO-BREAK SPACE}2011 6238 5295 7 "), "CH9300762011623852957"
		)

	def test_wrong_check_digits(self):
		with self.assertRaises(RappenError) as error:
			iban.validate_iban("CH94 0076 2011 6238 5295 7")
		self.assertIn("check digits", str(error.exception))

	def test_wrong_length(self):
		with self.assertRaises(RappenError) as error:
			iban.validate_iban("CH93 0076 2011 6238 5295")
		self.assertEqual(error.exception.params["expected"], 21)

	def test_bad_format(self):
		for value in ("", "1234", "CHXX00762011623852957", "CH93-0076-2011"):
			with self.subTest(value=value):
				self.assertFalse(iban.is_valid_iban(value))

	def test_unknown_country_uses_checksum_only(self):
		# A country that is not in the registry table: format and checksum still apply
		self.assertFalse(iban.is_valid_iban("ZZ00 1234 5678 9012 3"))

	def test_qr_iban(self):
		self.assertTrue(iban.is_qr_iban(SIX_QR_IBAN))
		self.assertFalse(iban.is_qr_iban(SIX_IBAN))
		self.assertFalse(iban.is_qr_iban("DE89 3704 0044 0532 0130 00"))
		self.assertEqual(iban.validate_qr_iban(SIX_QR_IBAN), "CH4431999123000889012")

	def test_regular_iban_is_no_qr_iban(self):
		with self.assertRaises(RappenError) as error:
			iban.validate_qr_iban(SIX_IBAN)
		self.assertIn("not a QR-IBAN", str(error.exception))

	def test_format(self):
		self.assertEqual(iban.format_iban("CH4431999123000889012"), SIX_QR_IBAN)
