"""Character set of the Swiss Payment Standards (QR-bill and ISO 20022 messages).

Allowed are Basic Latin, Latin-1 Supplement and Latin Extended-A, plus Ș ș Ț ț and the euro sign.
"""

import unicodedata

_EXTRA = frozenset(map(chr, (0x218, 0x219, 0x21A, 0x21B, 0x20AC)))
REPLACEMENT = "."


def is_allowed(char: str) -> bool:
	code = ord(char)
	return 0x20 <= code <= 0x7E or 0xA0 <= code <= 0x17F or char in _EXTRA


def is_clean(text: str) -> bool:
	"""True if every character of ``text`` is allowed."""
	return all(is_allowed(c) for c in text)


def _replace(char: str) -> str:
	# Try the decomposed form first, e.g. «ǎ» becomes «a» with a combining mark that is dropped
	base = "".join(
		c for c in unicodedata.normalize("NFKD", char) if is_allowed(c) and not unicodedata.combining(c)
	)
	return base or REPLACEMENT


def clean(text: str | None) -> str:
	"""Make ``text`` fit the character set.

	Line breaks, tabs and repeated spaces become a single space (QR-bill fields are one line each). Characters
	outside the set are replaced by their base letter where Unicode has one, otherwise by a full stop.
	"""
	text = unicodedata.normalize("NFC", text or "")
	text = " ".join(text.split())
	return "".join(c if is_allowed(c) else _replace(c) for c in text)
