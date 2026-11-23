"""IBAN and QR-IBAN (ISO 13616, SIX Swiss Implementation Guidelines for the QR-bill)."""

import re

from rappen.core.errors import RappenError, _

# Length of the IBAN per country, from the SWIFT IBAN registry
IBAN_LENGTHS: dict[str, int] = {
	"AD": 24, "AE": 23, "AL": 28, "AT": 20, "AZ": 28, "BA": 20, "BE": 16, "BG": 22, "BH": 22, "BI": 27,
	"BR": 29, "BY": 28, "CH": 21, "CR": 22, "CY": 28, "CZ": 24, "DE": 22, "DJ": 27, "DK": 18, "DO": 28,
	"EE": 20, "EG": 29, "ES": 24, "FI": 18, "FK": 18, "FO": 18, "FR": 27, "GB": 22, "GE": 22, "GI": 23,
	"GL": 18, "GR": 27, "GT": 28, "HN": 28, "HR": 21, "HU": 28, "IE": 22, "IL": 23, "IQ": 23, "IS": 26,
	"IT": 27, "JO": 30, "KW": 30, "KZ": 20, "LB": 28, "LC": 32, "LI": 21, "LT": 20, "LU": 20, "LV": 21,
	"LY": 25, "MC": 27, "MD": 24, "ME": 22, "MK": 19, "MN": 20, "MR": 27, "MT": 31, "MU": 30, "NI": 28,
	"NL": 18, "NO": 15, "OM": 23, "PK": 24, "PL": 28, "PS": 29, "PT": 25, "QA": 29, "RO": 24, "RS": 22,
	"RU": 33, "SA": 24, "SC": 31, "SD": 18, "SE": 24, "SI": 19, "SK": 24, "SM": 27, "SO": 23, "ST": 25,
	"SV": 28, "TL": 23, "TN": 24, "TR": 26, "UA": 29, "VA": 22, "VG": 24, "XK": 20, "YE": 30,
}  # fmt: skip

# Countries whose IBANs can be QR-IBANs, and the range of institution IDs (IID) reserved for them
QR_IBAN_COUNTRIES = ("CH", "LI")
QR_IID_FIRST = 30000
QR_IID_LAST = 31999

_FORMAT = re.compile(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}")


def compact(value: str | None) -> str:
	"""Remove all whitespace and upper-case the value."""
	return "".join((value or "").split()).upper()


def _checksum_ok(iban: str) -> bool:
	rearranged = iban[4:] + iban[:4]
	return int("".join(str(int(c, 36)) for c in rearranged)) % 97 == 1


def validate_iban(value: str | None) -> str:
	"""Return the IBAN in compact form, or raise ``RappenError`` with the reason it is invalid."""
	iban = compact(value)
	if not _FORMAT.fullmatch(iban):
		raise RappenError(
			_(
				"IBAN {iban} is invalid: it must start with a country code and two check digits, "
				"followed by 11 to 30 letters or digits."
			),
			iban=iban,
		)
	country = iban[:2]
	expected = IBAN_LENGTHS.get(country)
	if expected and len(iban) != expected:
		raise RappenError(
			_("IBAN {iban} has {length} characters, IBANs from {country} have {expected}."),
			iban=iban,
			length=len(iban),
			country=country,
			expected=expected,
		)
	if not _checksum_ok(iban):
		raise RappenError(_("IBAN {iban} is invalid: the check digits do not match."), iban=iban)
	return iban


def is_valid_iban(value: str | None) -> bool:
	try:
		validate_iban(value)
	except RappenError:
		return False
	return True


def _is_qr_iid(iban: str) -> bool:
	return iban[:2] in QR_IBAN_COUNTRIES and QR_IID_FIRST <= int(iban[4:9]) <= QR_IID_LAST


def is_qr_iban(value: str | None) -> bool:
	"""True for a valid Swiss or Liechtenstein IBAN with an IID from 30000 to 31999."""
	try:
		iban = validate_iban(value)
	except RappenError:
		return False
	return _is_qr_iid(iban)


def validate_qr_iban(value: str | None) -> str:
	"""Return the QR-IBAN in compact form, or raise ``RappenError``."""
	iban = validate_iban(value)
	if not _is_qr_iid(iban):
		raise RappenError(
			_(
				"{iban} is not a QR-IBAN. A QR-IBAN is a Swiss or Liechtenstein IBAN with an institution "
				"ID (digits 5 to 9) from 30000 to 31999."
			),
			iban=iban,
		)
	return iban


def format_iban(value: str | None) -> str:
	"""Group the IBAN in blocks of four, as printed on the QR-bill: ``CH44 3199 9123 0008 8901 2``."""
	iban = compact(value)
	return " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))
