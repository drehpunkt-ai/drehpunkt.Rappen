import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from rappen.core import schemas, vat
from rappen.core.errors import RappenError

try:
	import lxml
except ImportError:  # only installed where the schema is checked
	lxml = None

DATA = Path(__file__).parent / "data"
SCHEMA = "ech/eCH-0217/2/eCH-0217-2-0-0.xsd"
UID = "CHE-123.456.788"  # made up, with a valid check digit


def effective(**changes) -> vat.VatReturn:
	fields = {
		"uid": UID,
		"organisation_name": "Muster Schreinerei AG",
		"period_from": date(2026, 7, 1),
		"period_till": date(2026, 9, 30),
		"generated": datetime(2026, 10, 15, 9, 0, 0),
		"business_reference": "VAT-2026-00003",
		"product_version": "0.1.0",
		"total_consideration": Decimal("108000"),
		"supplies_to_foreign_countries": Decimal("8000"),
		"supplies": (
			vat.RateTurnover(Decimal("8.1"), Decimal("95000")),
			vat.RateTurnover(Decimal("2.6"), Decimal("5000")),
		),
		"input_tax_material_and_services": Decimal("2000"),
		"input_tax_investments": Decimal("500"),
	}
	fields.update(changes)
	return vat.VatReturn(**fields)


class TestUid(unittest.TestCase):
	def test_valid(self):
		self.assertEqual(vat.validate_uid(UID), "CHE123456788")
		self.assertEqual(vat.validate_uid("CHE123456788"), "CHE123456788")

	def test_invalid(self):
		for value in ("CHE-123.456.789", "123456788", "CHE-123.456", ""):
			with self.subTest(value=value):
				with self.assertRaises(RappenError):
					vat.validate_uid(value)


class TestComputation(unittest.TestCase):
	def test_effective(self):
		r = effective()
		self.assertEqual(r.deductions, Decimal("8000.00"))
		self.assertEqual(r.taxable_turnover, Decimal("100000.00"))
		self.assertEqual(r.output_tax, Decimal("7825.00"))  # 7695.00 + 130.00
		self.assertEqual(r.input_tax, Decimal("2500.00"))
		self.assertEqual(r.payable_tax, Decimal("5325.00"))
		self.assertEqual(r.problems(), [])

	def test_credit(self):
		r = effective(input_tax_material_and_services=Decimal("9000"))
		self.assertEqual(r.payable_tax, Decimal("-1675.00"))

	def test_net_tax_rate(self):
		r = effective(
			method=vat.NET_TAX_RATE,
			total_consideration=Decimal("54050"),
			supplies_to_foreign_countries=Decimal(0),
			supplies=(vat.RateTurnover(Decimal("6.2"), Decimal("54050")),),
		)
		self.assertEqual(r.input_tax, Decimal(0))
		self.assertEqual(r.payable_tax, Decimal("3351.10"))

	def test_turnover_must_add_up(self):
		r = effective(supplies_to_foreign_countries=Decimal(0))
		self.assertIn("box 299", str(r.problems()[0]))

	def test_various_deduction_needs_description(self):
		r = effective(
			supplies_to_foreign_countries=Decimal("7000"),
			various_deduction=Decimal("1000"),
		)
		self.assertIn("description", str(r.problems()[0]))

	def test_at_most_two_net_tax_rates(self):
		rates = tuple(vat.RateTurnover(Decimal(r), Decimal("100")) for r in ("6.2", "2.1", "0.6"))
		r = effective(
			method=vat.NET_TAX_RATE,
			total_consideration=Decimal(300),
			supplies_to_foreign_countries=0,
			supplies=rates,
		)
		self.assertIn("two net tax rates", " ".join(str(p) for p in r.problems()))


class TestXml(unittest.TestCase):
	def test_golden_file(self):
		self.assertEqual(effective().to_xml(), (DATA / "ech0217_effective.xml").read_bytes())

	@unittest.skipUnless(lxml, "lxml is needed to check the schema")
	def test_valid_against_schema(self):
		schemas.validate(effective().to_xml(), SCHEMA)
		net = effective(
			method=vat.NET_TAX_RATE,
			submission=vat.CORRECTION,
			total_consideration=Decimal("54050"),
			supplies_to_foreign_countries=Decimal(0),
			supplies=(vat.RateTurnover(Decimal("6.2"), Decimal("54050")),),
			donations=Decimal("100"),
		)
		schemas.validate(net.to_xml(), SCHEMA)
		various = effective(
			supplies_to_foreign_countries=Decimal("7000"),
			various_deduction=Decimal("1000"),
			various_deduction_description="Verkauf Liegenschaft",
			input_tax_corrections=Decimal("50"),
		)
		schemas.validate(various.to_xml(), SCHEMA)
