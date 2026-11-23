import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from rappen.core import camt, reference
from rappen.core.errors import RappenError

DATA = Path(__file__).parent / "data"


def read(name: str) -> list[camt.Statement]:
	return camt.parse((DATA / name).read_bytes())


class TestStatement(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		(cls.statement,) = read("camt053_v08.xml")
		cls.by_id = {t.transaction_id: t for t in cls.statement.transactions}

	def test_header(self):
		s = self.statement
		self.assertEqual((s.kind, s.version), ("camt.053", "001.08"))
		self.assertEqual(s.message_id, "STMT-20261123-0001")
		self.assertEqual(s.account_iban, "CH9300762011623852957")
		self.assertEqual(s.currency, "CHF")
		self.assertEqual(s.from_date, date(2026, 11, 23))
		self.assertEqual(s.opening_balance, Decimal("10000.00"))
		self.assertEqual(s.closing_balance, Decimal("11899.75"))

	def test_only_booked_entries(self):
		self.assertEqual(sorted(self.by_id), ["ENTRY-0005", "TX-0001", "TX-0002", "TX-0003", "TX-0004"])

	def test_qr_payment(self):
		t = self.by_id["TX-0001"]
		self.assertEqual(t.entry_reference, "ENTRY-0001")
		self.assertEqual(t.amount, Decimal("1949.75"))
		self.assertTrue(t.credit)
		self.assertEqual(t.reference, "210000000003139471430009017")
		self.assertEqual(t.reference_type, reference.QRR)
		self.assertEqual(t.end_to_end_id, "")
		self.assertEqual(t.party_name, "Anna Beispiel")
		self.assertEqual(t.party_iban, "CH5604835012345678009")
		self.assertEqual(t.booking_date, date(2026, 11, 23))
		self.assertEqual(t.bank_transaction_code, "PMNT/RCDT/VCOM")

	def test_batch_with_details_is_split(self):
		first, second = self.by_id["TX-0002"], self.by_id["TX-0003"]
		self.assertEqual((first.amount, second.amount), (Decimal("100.00"), Decimal("50.00")))
		self.assertEqual(first.reference_type, reference.SCOR)
		self.assertEqual(first.party_name, "Max Muster GmbH")
		self.assertEqual(second.reference_type, reference.NON)
		self.assertEqual(second.message, "Spende")
		self.assertFalse(first.batch)

	def test_outgoing_payment(self):
		t = self.by_id["TX-0004"]
		self.assertFalse(t.credit)
		self.assertEqual(t.end_to_end_id, "PP-2026-00001-1")
		self.assertEqual(t.party_name, "Lieferant AG")
		self.assertEqual(t.party_iban, "DE89370400440532013000")
		self.assertEqual(t.charges, Decimal("0.50"))
		self.assertEqual(t.message, "Rechnung 4711")

	def test_batch_without_details(self):
		t = self.by_id["ENTRY-0005"]
		self.assertTrue(t.batch)
		self.assertEqual(t.batch_count, 3)
		self.assertEqual(t.amount, Decimal("300.00"))
		self.assertEqual(t.message, "Sammelgutschrift QR-Rechnungen")


class TestNotification(unittest.TestCase):
	def test_details_of_batch(self):
		(notification,) = read("camt054_v08.xml")
		self.assertEqual(notification.kind, "camt.054")
		self.assertIsNone(notification.opening_balance)
		transactions = notification.transactions
		self.assertEqual([t.transaction_id for t in transactions], ["TX-0051", "TX-0052", "TX-0053"])
		self.assertEqual({t.entry_reference for t in transactions}, {"ENTRY-0005"})
		self.assertEqual(sum(t.amount for t in transactions), Decimal("300.00"))
		# Amount from AmtDtls/TxAmt when the transaction has no Amt of its own
		self.assertEqual(transactions[2].amount, Decimal("80.00"))

	def test_invalid_reference_is_ignored(self):
		(notification,) = read("camt054_v08.xml")
		second = notification.transactions[1]
		self.assertEqual(second.reference, "")
		self.assertEqual(second.reference_type, reference.NON)


class TestOldVersion(unittest.TestCase):
	def test_version_04(self):
		(statement,) = read("camt053_v04.xml")
		self.assertEqual(statement.version, "001.04")
		self.assertEqual(statement.account_iban, "CH9300762011623852957")
		(t,) = statement.transactions
		self.assertEqual(t.transaction_id, "OLD-ENTRY-1/1")
		self.assertEqual(t.party_name, "Hans Beispiel")
		self.assertEqual(t.end_to_end_id, "E2E-42")
		self.assertEqual(t.amount, Decimal("42.00"))
		self.assertEqual(t.message, "Mitgliederbeitrag")


class TestInvalidFiles(unittest.TestCase):
	def test_not_xml(self):
		with self.assertRaisesRegex(RappenError, "not valid XML"):
			camt.parse(b"Datum;Betrag\n23.11.2026;100.00")

	def test_other_message(self):
		with self.assertRaisesRegex(RappenError, "not a camt"):
			camt.parse(b'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.09"/>')

	def test_entities_are_refused(self):
		data = b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]><d>&x;</d>'
		with self.assertRaisesRegex(RappenError, "document type declaration"):
			camt.parse(data)

	def test_missing_iban(self):
		data = (
			(DATA / "camt053_v04.xml").read_bytes().replace(b"<IBAN>CH93 0076 2011 6238 5295 7</IBAN>", b"")
		)
		with self.assertRaisesRegex(RappenError, "no IBAN"):
			camt.parse(data)
