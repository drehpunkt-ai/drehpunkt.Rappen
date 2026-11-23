import unittest
from datetime import date, datetime
from pathlib import Path

from rappen.core import pain001, schemas
from rappen.core.address import Address
from rappen.core.errors import RappenError

try:
	import lxml
except ImportError:  # only installed where the schema is checked
	lxml = None

DATA = Path(__file__).parent / "data"
SCHEMA = "pain.001.001.09.ch.03.xsd"
DEBTOR = Address.from_line("Muster Schreinerei AG", "Bahnhofstrasse 12a", "8000", "Zürich", "CH")


def payment(**changes) -> pain001.Payment:
	fields = {
		"end_to_end_id": "PP-2026-00001-1",
		"amount": "1949.75",
		"currency": "CHF",
		"creditor": Address.from_line("Anna Beispiel", "Route de Genève 7bis", "1260", "Nyon", "CH"),
		"creditor_iban": "CH44 3199 9123 0008 8901 2",
		"reference": "210000000003139471430009017",
		"message": "Rechnung 4711",
	}
	fields.update(changes)
	return pain001.Payment(**fields)


def run(*payments, **changes) -> pain001.PaymentRun:
	fields = {
		"message_id": "PP-2026-00001",
		"created": datetime(2026, 11, 23, 10, 30, 0),
		"execution_date": date(2026, 11, 25),
		"debtor": DEBTOR,
		"debtor_iban": "CH93 0076 2011 6238 5295 7",
		"payments": payments,
	}
	fields.update(changes)
	return pain001.PaymentRun(**fields)


def golden_run() -> pain001.PaymentRun:
	return run(
		payment(),
		payment(
			end_to_end_id="PP-2026-00001-2",
			amount="500",
			creditor=Address.from_line("Lieferant AG", "Industriestrasse 3", "3000", "Bern", "CH"),
			creditor_iban="CH56 0483 5012 3456 7800 9",
			reference="RF18539007547034",
			message="",
		),
		payment(
			end_to_end_id="PP-2026-00001-3",
			amount="80.5",
			creditor=Address.from_line("Hans Beispiel", "Dorfweg 1", "9490", "Vaduz", "LI"),
			creditor_iban="CH56 0483 5012 3456 7800 9",
			reference="",
			message="Mitgliederbeitrag 2027",
		),
		payment(
			end_to_end_id="PP-2026-00001-4",
			amount="120",
			currency="EUR",
			creditor=Address.from_line("Max Muster GmbH", "Musterweg 3", "80331", "München", "DE"),
			creditor_iban="DE89 3704 0044 0532 0130 00",
			reference="",
			message="Invoice 2026-17",
		),
	)


class TestPaymentTypes(unittest.TestCase):
	def test_types(self):
		self.assertEqual(payment().payment_type, pain001.QR)
		self.assertEqual(payment(creditor_iban="CH56 0483 5012 3456 7800 9").payment_type, pain001.DOMESTIC)
		self.assertEqual(
			payment(creditor_iban="DE89 3704 0044 0532 0130 00", currency="EUR").payment_type, pain001.SEPA
		)
		self.assertIsNone(payment(creditor_iban="DE89 3704 0044 0532 0130 00", currency="CHF").payment_type)


class TestRules(unittest.TestCase):
	def assertProblem(self, item, text):
		self.assertIn(text, " | ".join(str(p) for p in item.problems()))

	def test_qr_iban_needs_qr_reference(self):
		self.assertProblem(payment(reference=""), "needs the QR reference")
		self.assertProblem(payment(reference="RF18539007547034"), "needs the QR reference")

	def test_qr_reference_needs_qr_iban(self):
		self.assertProblem(payment(creditor_iban="CH56 0483 5012 3456 7800 9"), "only works with a QR-IBAN")

	def test_unsupported_destination(self):
		self.assertProblem(
			payment(creditor_iban="DE89 3704 0044 0532 0130 00", currency="CHF", reference=""),
			"goes to DE in CHF",
		)

	def test_amount_and_ids(self):
		self.assertProblem(payment(amount="0"), "must be positive")
		self.assertProblem(payment(end_to_end_id=""), "end-to-end ID")
		self.assertProblem(payment(end_to_end_id="x" * 36), "end-to-end ID")
		self.assertProblem(run(payment(), payment()), "its own end-to-end ID")
		self.assertProblem(
			run(payment(), message_id="Zahlung über 35 Zeichen lang, viel zu lang"), "message ID"
		)

	def test_debtor(self):
		self.assertProblem(run(payment(), debtor_iban="CH44 3199 9123 0008 8901 2"), "not from a QR-IBAN")
		self.assertProblem(run(payment(), debtor=Address(name="Muster AG")), "town is missing")
		self.assertProblem(run(), "no payments")

	def test_creditor_address(self):
		self.assertProblem(payment(creditor=Address(name="Anna Beispiel", country="CH")), "town is missing")

	def test_to_xml_raises_first_problem(self):
		with self.assertRaises(RappenError):
			run(payment(reference="")).to_xml()


class TestXml(unittest.TestCase):
	def test_golden_file(self):
		self.assertEqual(golden_run().to_xml(), (DATA / "pain001_run.xml").read_bytes())

	def test_groups(self):
		groups = golden_run().groups()
		self.assertEqual([(key, len(items)) for key, items in groups], [("CHF", 3), (pain001.SEPA, 1)])

	@unittest.skipUnless(lxml, "lxml is needed to check the schema")
	def test_valid_against_swiss_schema(self):
		schemas.validate(golden_run().to_xml(), SCHEMA)
		schemas.validate(run(payment()).to_xml(), SCHEMA)

	@unittest.skipUnless(lxml, "lxml is needed to check the schema")
	def test_schema_violation_is_reported(self):
		broken = golden_run().to_xml().replace(b"<PmtMtd>TRF</PmtMtd>", b"<PmtMtd>XXX</PmtMtd>")
		with self.assertRaisesRegex(RappenError, "does not match the schema"):
			schemas.validate(broken, SCHEMA)
