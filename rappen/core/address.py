"""Structured addresses (type S) for the QR-bill and ISO 20022 payment messages.

Since November 2025 the QR-bill only accepts structured addresses, and from November 2026 the Swiss Payment
Standards require them in pain.001 as well. ERPNext keeps street and building number together in one line,
so ``split_street`` separates them when the address is printed or exported.
"""

import re
from dataclasses import dataclass

from rappen.core import charset
from rappen.core.errors import RappenError, _

NAME_MAX = 70
STREET_MAX = 70
BUILDING_NUMBER_MAX = 16
POSTAL_CODE_MAX = 16
TOWN_MAX = 35

# Building number: digits, optional letters («12a», «7bis», «12 A», «7 bis»), optional range or part («12-14», «1/A»)
_LETTERS = r"(?:[^\W\d_]{1,6}|\s(?:[^\W\d_]|bis|ter|quater))"
_NUMBER = rf"\d{{1,5}}{_LETTERS}?(?:\s?[-/]\s?(?:\d{{1,5}}{_LETTERS}?|[^\W\d_]))?"
_TRAILING = re.compile(rf"(?P<street>.*?[^\W\d_].*?)[\s,]+(?P<number>{_NUMBER})", re.IGNORECASE)
_LEADING = re.compile(rf"(?P<number>{_NUMBER})[\s,]+(?P<street>[^\W\d_].*)", re.IGNORECASE)
_NUMBER_LABEL = re.compile(r"[\s,]*\b(?:nr|no|n°|nº)\.?$", re.IGNORECASE)
_POSTBOX = re.compile(
	r"(?:postfach|case postale|casella postale|postbox|post box|p\.?\s?o\.?\s?box|c\.?p\.?)(?:\s|$)",
	re.IGNORECASE,
)


def split_street(line: str | None) -> tuple[str, str]:
	"""Split an address line into street and building number.

	``Musterstrasse 12a`` gives ``("Musterstrasse", "12a")``, ``12, rue du Rhône`` gives
	``("rue du Rhône", "12")``. A post office box or a line without a recognisable number stays whole in
	the street, which is valid for a structured address as well.
	"""
	line = " ".join((line or "").split())
	if not line or _POSTBOX.match(line):
		return line, ""
	for pattern in (_TRAILING, _LEADING):
		match = pattern.fullmatch(line)
		if match:
			street = _NUMBER_LABEL.sub("", match["street"]).strip(" ,")
			number = match["number"]
			if street and len(number) <= BUILDING_NUMBER_MAX:
				return street, number
	return line, ""


@dataclass(frozen=True)
class Address:
	"""A structured address as the QR-bill and pain.001 expect it. ``country`` is ISO 3166-1 alpha-2."""

	name: str
	street: str = ""
	building_number: str = ""
	postal_code: str = ""
	town: str = ""
	country: str = ""

	@classmethod
	def from_line(
		cls,
		name: str | None,
		address_line: str | None,
		postal_code: str | None,
		town: str | None,
		country: str | None,
	) -> "Address":
		"""Build the address from ERPNext's fields, with characters outside the Swiss set replaced."""
		street, building_number = split_street(charset.clean(address_line))
		return cls(
			name=charset.clean(name),
			street=street,
			building_number=building_number,
			postal_code=charset.clean(postal_code),
			town=charset.clean(town),
			country="".join((country or "").split()).upper(),
		)

	def problems(self) -> list[RappenError]:
		"""Everything that keeps this address from being used on a QR-bill or in pain.001."""
		name = self.name
		problems = []
		if not self.name:
			problems.append(RappenError(_("The name is missing in the address.")))
		elif len(self.name) > NAME_MAX:
			problems.append(
				RappenError(
					_("The name {name} is too long: {length} characters, at most {limit} are allowed."),
					name=name,
					length=len(self.name),
					limit=NAME_MAX,
				)
			)
		if len(self.street) > STREET_MAX:
			problems.append(
				RappenError(
					_("The street {street} is too long: {length} characters, at most {limit} are allowed."),
					street=self.street,
					length=len(self.street),
					limit=STREET_MAX,
				)
			)
		if not self.postal_code:
			problems.append(RappenError(_("The postal code is missing in the address of {name}."), name=name))
		elif len(self.postal_code) > POSTAL_CODE_MAX:
			problems.append(
				RappenError(
					_("The postal code {postal_code} is too long: at most {limit} characters are allowed."),
					postal_code=self.postal_code,
					limit=POSTAL_CODE_MAX,
				)
			)
		elif self.country in ("CH", "LI") and not re.fullmatch(r"\d{4}", self.postal_code):
			problems.append(
				RappenError(
					_("Swiss and Liechtenstein postal codes have four digits, {postal_code} does not."),
					postal_code=self.postal_code,
				)
			)
		if not self.town:
			problems.append(RappenError(_("The town is missing in the address of {name}."), name=name))
		elif len(self.town) > TOWN_MAX:
			problems.append(
				RappenError(
					_("The town {town} is too long: {length} characters, at most {limit} are allowed."),
					town=self.town,
					length=len(self.town),
					limit=TOWN_MAX,
				)
			)
		if not self.country:
			problems.append(RappenError(_("The country is missing in the address of {name}."), name=name))
		elif not re.fullmatch(r"[A-Z]{2}", self.country):
			problems.append(
				RappenError(
					_("Country code {country} is invalid, it needs two letters (ISO 3166-1)."),
					country=self.country,
				)
			)
		return problems
