import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from rappen.core import qrbill
from rappen.core.address import Address
from rappen.core.errors import RappenError

try:
	import zxingcpp
	from PIL import Image
except ImportError:  # only installed in the core test job, not in a bench
	zxingcpp = None

DATA = Path(__file__).parent / "data"

# Made-up parties, sample IBANs and references from SIX and ISO 11649
QR_IBAN = "CH44 3199 9123 0008 8901 2"
IBAN = "CH93 0076 2011 6238 5295 7"
QRR = "21 00000 00003 13947 14300 09017"
SCOR = "RF18 5390 0754 7034"
CREDITOR = Address.from_line("Muster Schreinerei AG", "Bahnhofstrasse 12a", "8000", "Zürich", "CH")
DEBTOR = Address.from_line("Anna Beispiel", "Route de Genève 7bis", "1260", "Nyon", "CH")


def golden(name: str) -> str:
	return (DATA / name).read_text(encoding="utf-8")


def qrr_bill(**changes) -> qrbill.QRBill:
	fields = {
		"account": QR_IBAN,
		"creditor": CREDITOR,
		"amount": "1949.75",
		"currency": "CHF",
		"debtor": DEBTOR,
		"reference": QRR,
		"message": "Rechnung RE-2026-0042",
		"billing_information": qrbill.swico_s1(
			"RE-2026-0042", date(2026, 11, 23), vat_number="CHE-123.456.789"
		),
	}
	fields.update(changes)
	return qrbill.QRBill(**fields)


class TestPayload(unittest.TestCase):
	def test_qr_reference(self):
		bill = qrr_bill().validate()
		self.assertEqual(bill.payload(), golden("qrbill_qrr.txt"))

	def test_creditor_reference_open_amount_without_debtor(self):
		creditor = Address.from_line("Muster Schreinerei AG", "Postfach 123", "9490", "Vaduz", "LI")
		bill = qrbill.QRBill(account=IBAN, creditor=creditor, currency="EUR", reference=SCOR).validate()
		self.assertEqual(bill.payload(), golden("qrbill_scor_open.txt"))

	def test_without_reference_with_alternative_procedure(self):
		debtor = Address.from_line("Max Muster GmbH", "Musterweg 3", "80331", "München", "DE")
		bill = qrbill.QRBill(
			account=IBAN,
			creditor=CREDITOR,
			amount=50,
			debtor=debtor,
			message="Spende",
			alternative_procedures=("Name AV1: UV;Beispiel;12345",),
		).validate()
		self.assertEqual(bill.payload(), golden("qrbill_non.txt"))

	def test_amount_is_rounded_to_cents(self):
		self.assertEqual(qrr_bill(amount=Decimal("10.005")).amount, Decimal("10.01"))
		self.assertIsNone(qrr_bill(amount=None).amount)
		self.assertIsNone(qrr_bill(amount="").amount)

	def test_texts_are_cleaned(self):
		bill = qrr_bill(message="Rechnung\nRE-2026-0042  李")
		self.assertEqual(bill.message, "Rechnung RE-2026-0042 .")


class TestRules(unittest.TestCase):
	def assertProblem(self, bill, text):
		messages = " | ".join(str(problem) for problem in bill.problems())
		self.assertIn(text, messages)

	def test_qr_iban_needs_qr_reference(self):
		self.assertProblem(qrr_bill(reference=SCOR), "QR-IBAN can only be used with a QR reference")
		self.assertProblem(qrr_bill(reference=""), "QR-IBAN can only be used with a QR reference")

	def test_qr_reference_needs_qr_iban(self):
		self.assertProblem(qrr_bill(account=IBAN), "can only be used with a QR-IBAN")

	def test_invalid_reference(self):
		self.assertProblem(qrr_bill(reference="210000000003139471430009018"), "check digit")

	def test_foreign_iban(self):
		self.assertProblem(qrr_bill(account="DE89 3704 0044 0532 0130 00", reference=""), "is from DE")

	def test_currency(self):
		self.assertProblem(qrr_bill(currency="USD"), "CHF or EUR")

	def test_amount_range(self):
		self.assertProblem(qrr_bill(amount="0"), "between 0.01")
		self.assertProblem(qrr_bill(amount="1000000000"), "between 0.01")
		with self.assertRaises(RappenError):
			qrr_bill(amount="abc")

	def test_message_and_billing_information_together(self):
		self.assertProblem(qrr_bill(message="x" * 100, billing_information="//S1/10/" + "1" * 40), "together")

	def test_alternative_procedures(self):
		self.assertProblem(qrr_bill(alternative_procedures=("a", "b", "c")), "alternative procedures")
		self.assertProblem(qrr_bill(alternative_procedures=("a" * 101,)), "alternative procedures")

	def test_addresses_are_checked(self):
		self.assertProblem(qrr_bill(creditor=Address(name="Muster AG")), "postal code is missing")
		self.assertProblem(
			qrr_bill(debtor=Address.from_line("Anna", "Weg 1", "", "Nyon", "CH")), "postal code is missing"
		)

	def test_validate_raises_first_problem(self):
		with self.assertRaises(RappenError):
			qrr_bill(currency="USD").validate()


class TestParse(unittest.TestCase):
	def test_roundtrip(self):
		for name in ("qrbill_qrr.txt", "qrbill_scor_open.txt", "qrbill_non.txt"):
			with self.subTest(name=name):
				payload = golden(name)
				self.assertEqual(qrbill.parse(payload).payload(), payload)

	def test_crlf_and_trailing_newline(self):
		payload = golden("qrbill_qrr.txt")
		bill = qrbill.parse(payload.replace("\n", "\r\n") + "\r\n")
		self.assertEqual(bill.payload(), payload)
		self.assertEqual(bill.amount, Decimal("1949.75"))
		self.assertEqual(bill.debtor, DEBTOR)

	def test_not_a_qr_bill(self):
		with self.assertRaises(RappenError):
			qrbill.parse("https://example.org")

	def test_unstructured_address_is_rejected(self):
		lines = golden("qrbill_qrr.txt").split("\n")
		lines[4:11] = ["K", "Muster Schreinerei AG", "Bahnhofstrasse 12a", "8000 Zürich", "", "", "CH"]
		with self.assertRaisesRegex(RappenError, "unstructured address"):
			qrbill.parse("\n".join(lines))

	def test_reference_type_must_match(self):
		payload = golden("qrbill_qrr.txt").replace("\nQRR\n", "\nNON\n")
		with self.assertRaisesRegex(RappenError, "reference type"):
			qrbill.parse(payload)


class TestQrCode(unittest.TestCase):
	def test_error_correction_m(self):
		code = qrr_bill().qr_code()
		self.assertEqual(code.error, "M")
		self.assertLessEqual(code.version, qrbill.QR_VERSION_MAX)

	def test_svg(self):
		svg = qrr_bill().svg()
		self.assertTrue(svg.startswith('<svg xmlns="http://www.w3.org/2000/svg" width="46mm" height="46mm"'))
		self.assertIn('fill="#000"', svg)
		self.assertEqual(svg, qrr_bill().svg(), "the SVG must be deterministic")

	def test_too_long(self):
		# Under 997 characters, but «é» takes two bytes in UTF-8, so the code needs more than version 25
		long = Address(name="é" * 70, street="é" * 70, postal_code="8000", town="é" * 35, country="CH")
		bill = qrr_bill(
			creditor=long,
			debtor=long,
			message="é" * 140,
			billing_information="",
			alternative_procedures=("é" * 100, "é" * 100),
		)
		self.assertLess(len(bill.payload()), qrbill.PAYLOAD_MAX)
		with self.assertRaisesRegex(RappenError, "version"):
			bill.qr_code()

	@unittest.skipUnless(zxingcpp, "zxing-cpp and Pillow are needed to read QR codes back")
	def test_readable_with_swiss_cross(self):
		for bill in (
			qrr_bill(),
			qrbill.parse(golden("qrbill_non.txt")),
			qrr_bill(message="é" * 60, billing_information=""),
		):
			with self.subTest(payload=bill.payload()[:60]):
				self.assertEqual(_read(bill), bill.payload())


def _read(bill: qrbill.QRBill) -> str:
	"""Render the QR code with the Swiss cross on top, the way it is printed, and read it back."""
	matrix = bill.qr_code().matrix
	size = len(matrix)
	scale, border = 8, 4
	image = Image.new("L", ((size + 2 * border) * scale,) * 2, 255)
	pixels = image.load()
	start, end = qrbill.cross_box(size)
	for y, row in enumerate(matrix):
		for x, dark in enumerate(row):
			if dark:
				for dy in range(scale):
					for dx in range(scale):
						pixels[(x + border) * scale + dx, (y + border) * scale + dy] = 0
	# The cross: a white square with a black square inside, which hides the modules beneath
	for py in range(int(start * scale), int(end * scale)):
		for px in range(int(start * scale), int(end * scale)):
			inner = (end - start) * scale * 0.5 / 7
			black = (
				start * scale + inner <= px < end * scale - inner
				and start * scale + inner <= py < end * scale - inner
			)
			pixels[px + border * scale, py + border * scale] = 0 if black else 255
	results = zxingcpp.read_barcodes(image)
	assert results, "no QR code found"
	return results[0].text
