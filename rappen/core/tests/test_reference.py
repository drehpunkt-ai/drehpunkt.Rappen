import unittest

from rappen.core import reference
from rappen.core.errors import RappenError

# QR reference from the SIX implementation guidelines, Creditor Reference from ISO 11649
SIX_QRR = "210000000003139471430009017"
ISO_SCOR = "RF18539007547034"


class TestQrReference(unittest.TestCase):
	def test_check_digit(self):
		self.assertEqual(reference.qrr_check_digit(SIX_QRR[:-1]), 7)

	def test_make(self):
		self.assertEqual(reference.make_qrr(SIX_QRR[:-1]), SIX_QRR)
		self.assertEqual(reference.make_qrr("1"), "000000000000000000000000011")

	def test_make_rejects_letters_and_length(self):
		for body in ("12a", "", "\N{FULLWIDTH DIGIT ONE}\N{FULLWIDTH DIGIT TWO}", "1" * 27):
			with self.subTest(body=body):
				with self.assertRaises(RappenError):
					reference.make_qrr(body)

	def test_validate(self):
		self.assertEqual(reference.validate_qrr("21 00000 00003 13947 14300 09017"), SIX_QRR)

	def test_wrong_check_digit(self):
		with self.assertRaises(RappenError) as error:
			reference.validate_qrr(SIX_QRR[:-1] + "8")
		self.assertIn("check digit", str(error.exception))

	def test_wrong_length(self):
		with self.assertRaises(RappenError):
			reference.validate_qrr(SIX_QRR[1:])

	def test_every_single_digit_error_is_detected(self):
		for position in range(len(SIX_QRR) - 1):
			for digit in "0123456789":
				if digit == SIX_QRR[position]:
					continue
				changed = SIX_QRR[:position] + digit + SIX_QRR[position + 1 :]
				with self.subTest(changed=changed):
					with self.assertRaises(RappenError):
						reference.validate_qrr(changed)

	def test_format(self):
		self.assertEqual(reference.format_qrr(SIX_QRR), "21 00000 00003 13947 14300 09017")


class TestCreditorReference(unittest.TestCase):
	def test_make(self):
		self.assertEqual(reference.make_scor("539007547034"), ISO_SCOR)

	def test_roundtrip_with_letters(self):
		for body in ("INV2026A1", "a", "Z" * 21, "0"):
			with self.subTest(body=body):
				made = reference.make_scor(body)
				self.assertEqual(reference.validate_scor(made), made)

	def test_make_rejects_invalid_body(self):
		for body in ("", "Z" * 22, "INV-2026", "ÄBC"):
			with self.subTest(body=body):
				with self.assertRaises(RappenError):
					reference.make_scor(body)

	def test_wrong_check_digits(self):
		with self.assertRaises(RappenError) as error:
			reference.validate_scor("RF19539007547034")
		self.assertIn("check digits", str(error.exception))

	def test_bad_format(self):
		for value in ("RF1", "RFAB123", "XX18539007547034", "RF18" + "1" * 22):
			with self.subTest(value=value):
				with self.assertRaises(RappenError):
					reference.validate_scor(value)

	def test_format(self):
		self.assertEqual(reference.format_scor(ISO_SCOR), "RF18 5390 0754 7034")


class TestReferenceType(unittest.TestCase):
	def test_types(self):
		self.assertEqual(reference.reference_type(None), reference.NON)
		self.assertEqual(reference.reference_type(" "), reference.NON)
		self.assertEqual(reference.reference_type(SIX_QRR), reference.QRR)
		self.assertEqual(reference.reference_type("rf18 5390 0754 7034"), reference.SCOR)

	def test_invalid_reference_raises(self):
		with self.assertRaises(RappenError):
			reference.reference_type("12345")

	def test_format_reference(self):
		self.assertEqual(reference.format_reference(SIX_QRR), "21 00000 00003 13947 14300 09017")
		self.assertEqual(reference.format_reference(ISO_SCOR), "RF18 5390 0754 7034")
		self.assertEqual(reference.format_reference(""), "")
