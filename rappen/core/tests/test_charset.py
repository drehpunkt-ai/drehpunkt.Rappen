import unittest

from rappen.core import charset


class TestCharset(unittest.TestCase):
	def test_allowed_characters_stay(self):
		for text in ("Zürich", "Genève", "Ștefan Țepeș", "Łódź", "Preis in €", "Crème brûlée"):
			with self.subTest(text=text):
				self.assertTrue(charset.is_clean(text))
				self.assertEqual(charset.clean(text), text)

	def test_whitespace_becomes_one_space(self):
		self.assertEqual(charset.clean(" Zeile 1\n\tZeile 2  \r\n"), "Zeile 1 Zeile 2")

	def test_base_letter_replaces_unknown_letter(self):
		# «ǎ» (U+01CE) is outside the set, its base letter «a» is inside
		self.assertEqual(charset.clean("Hǎn"), "Han")

	def test_full_stop_replaces_the_rest(self):
		self.assertEqual(charset.clean("Lee 李"), "Lee .")
		self.assertFalse(charset.is_clean("Lee 李"))

	def test_none(self):
		self.assertEqual(charset.clean(None), "")

	def test_decomposed_input_is_composed(self):
		# «u» followed by a combining diaeresis is the same as «ü»
		self.assertEqual(charset.clean("Zu\N{COMBINING DIAERESIS}rich"), "Zürich")
