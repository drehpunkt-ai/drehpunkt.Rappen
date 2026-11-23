import unittest

from rappen.core.address import Address, split_street


class TestSplitStreet(unittest.TestCase):
	def test_cases(self):
		cases = {
			"Musterstrasse 12": ("Musterstrasse", "12"),
			"Musterstrasse 12a": ("Musterstrasse", "12a"),
			"Musterstrasse 12 A": ("Musterstrasse", "12 A"),
			"Musterstrasse Nr. 12": ("Musterstrasse", "12"),
			"Hauptstrasse 12-14": ("Hauptstrasse", "12-14"),
			"Route de Genève 7bis": ("Route de Genève", "7bis"),
			"Route de Genève 7 bis": ("Route de Genève", "7 bis"),
			"Via San Gottardo 1/A": ("Via San Gottardo", "1/A"),
			"Rue du 31-Décembre 47": ("Rue du 31-Décembre", "47"),
			"Strasse des 1. August 5": ("Strasse des 1. August", "5"),
			"12, rue du Rhône": ("rue du Rhône", "12"),
			"17 Avenue de la Gare": ("Avenue de la Gare", "17"),
			"Postfachstrasse 5": ("Postfachstrasse", "5"),
			"  Musterstrasse   12  ": ("Musterstrasse", "12"),
		}
		for line, expected in cases.items():
			with self.subTest(line=line):
				self.assertEqual(split_street(line), expected)

	def test_stays_whole(self):
		for line in (
			"Bahnhofplatz",
			"Postfach 123",
			"Case postale 45",
			"Casella postale 7",
			"Bahnhofstrasse 1 Zürich",
			"",
		):
			with self.subTest(line=line):
				self.assertEqual(split_street(line), (line, ""))

	def test_none(self):
		self.assertEqual(split_street(None), ("", ""))


class TestAddress(unittest.TestCase):
	def test_from_line(self):
		address = Address.from_line("Muster AG", "Musterstrasse 12a", "8000", "Zürich", "ch")
		self.assertEqual(
			address,
			Address(
				name="Muster AG",
				street="Musterstrasse",
				building_number="12a",
				postal_code="8000",
				town="Zürich",
				country="CH",
			),
		)
		self.assertEqual(address.problems(), [])

	def test_characters_are_cleaned(self):
		address = Address.from_line("Muster\nAG", "Musterstrasse 1", "8000", "Zürich 李", "CH")
		self.assertEqual(address.name, "Muster AG")
		self.assertEqual(address.town, "Zürich .")

	def test_missing_fields(self):
		problems = Address.from_line("", "", "", "", "").problems()
		messages = [problem.message for problem in problems]
		self.assertEqual(len(messages), 4)
		self.assertIn("The name is missing in the address.", messages)

	def test_street_is_optional(self):
		self.assertEqual(Address.from_line("Muster AG", "", "9490", "Vaduz", "LI").problems(), [])

	def test_swiss_postal_code(self):
		problems = Address.from_line("Muster AG", "Weg 1", "80000", "Zürich", "CH").problems()
		self.assertEqual(len(problems), 1)
		self.assertIn("four digits", str(problems[0]))
		# Other countries keep their own formats
		self.assertEqual(Address.from_line("Muster GmbH", "Weg 1", "80331", "München", "DE").problems(), [])

	def test_lengths(self):
		address = Address.from_line("N" * 71, "S" * 71, "8000", "T" * 36, "CH")
		self.assertEqual(len(address.problems()), 3)

	def test_country_code(self):
		problems = Address.from_line("Muster AG", "Weg 1", "8000", "Zürich", "CHE").problems()
		self.assertIn("ISO 3166-1", str(problems[0]))
