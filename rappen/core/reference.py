"""Payment references: QR reference (QRR) and Creditor Reference (SCOR, ISO 11649).

QRR: 27 digits, the last one a check digit computed with the recursive modulo 10 algorithm. Only valid
together with a QR-IBAN.
SCOR: ``RF``, two check digits (ISO 7064 MOD 97-10) and 1 to 21 letters or digits. Only valid with a
regular IBAN.
"""

import re

from rappen.core.errors import RappenError, _

QRR = "QRR"
SCOR = "SCOR"
NON = "NON"

QRR_LENGTH = 27
SCOR_MAX_BODY = 21

# Table of the recursive modulo 10 algorithm (SIX, Implementation Guidelines QR-bill, appendix B)
_MOD10_TABLE = (0, 9, 4, 6, 8, 2, 7, 1, 3, 5)
_SCOR_BODY = re.compile(r"[A-Z0-9]{1,21}")


def compact(value: str | None) -> str:
	"""Remove all whitespace and upper-case the value."""
	return "".join((value or "").split()).upper()


def qrr_check_digit(digits: str) -> int:
	"""Check digit for a string of digits, recursive modulo 10."""
	carry = 0
	for digit in digits:
		carry = _MOD10_TABLE[(carry + int(digit)) % 10]
	return (10 - carry) % 10


def make_qrr(body: str) -> str:
	"""Build a QR reference from up to 26 digits: zero-padded on the left, check digit appended."""
	if not body.isdigit() or not body.isascii():
		raise RappenError(_("A QR reference can only contain digits, got {body}."), body=body)
	if len(body) > QRR_LENGTH - 1:
		raise RappenError(
			_("A QR reference holds at most 26 digits before the check digit, {body} has {length}."),
			body=body,
			length=len(body),
		)
	padded = body.zfill(QRR_LENGTH - 1)
	return padded + str(qrr_check_digit(padded))


def validate_qrr(value: str | None) -> str:
	"""Return the QR reference in compact form, or raise ``RappenError``."""
	reference = compact(value)
	if len(reference) != QRR_LENGTH or not reference.isdigit() or not reference.isascii():
		raise RappenError(
			_("A QR reference has exactly 27 digits, {reference} does not."), reference=reference
		)
	if qrr_check_digit(reference[:-1]) != int(reference[-1]):
		raise RappenError(
			_("QR reference {reference} is invalid: the check digit does not match."), reference=reference
		)
	return reference


def _scor_number(body: str, check: str) -> int:
	return int("".join(str(int(c, 36)) for c in body + "RF" + check))


def make_scor(body: str) -> str:
	"""Build a Creditor Reference from 1 to 21 letters or digits."""
	body = compact(body)
	if not _SCOR_BODY.fullmatch(body):
		raise RappenError(
			_("A Creditor Reference holds 1 to 21 letters (A to Z) or digits, got {body}."), body=body
		)
	check = 98 - _scor_number(body, "00") % 97
	return f"RF{check:02d}{body}"


def validate_scor(value: str | None) -> str:
	"""Return the Creditor Reference in compact form, or raise ``RappenError``."""
	reference = compact(value)
	body = reference[4:]
	if (
		not reference.startswith("RF")
		or not reference[2:4].isdigit()
		or not reference[2:4].isascii()
		or not _SCOR_BODY.fullmatch(body)
	):
		raise RappenError(
			_(
				"A Creditor Reference starts with RF and two check digits, followed by 1 to 21 letters or "
				"digits. {reference} does not."
			),
			reference=reference,
		)
	if _scor_number(body, reference[2:4]) % 97 != 1:
		raise RappenError(
			_("Creditor Reference {reference} is invalid: the check digits do not match."),
			reference=reference,
		)
	return reference


def reference_type(value: str | None) -> str:
	"""``QRR``, ``SCOR`` or ``NON`` (no reference). Raises ``RappenError`` for an invalid reference."""
	reference = compact(value)
	if not reference:
		return NON
	if reference.startswith("RF"):
		validate_scor(reference)
		return SCOR
	validate_qrr(reference)
	return QRR


def format_qrr(value: str | None) -> str:
	"""Group a QR reference as printed on the QR-bill: ``21 00000 00003 13947 14300 09017``."""
	reference = compact(value)
	head = len(reference) % 5
	groups = [reference[:head]] if head else []
	groups += [reference[i : i + 5] for i in range(head, len(reference), 5)]
	return " ".join(groups)


def format_scor(value: str | None) -> str:
	"""Group a Creditor Reference in blocks of four: ``RF18 5390 0754 7034``."""
	reference = compact(value)
	return " ".join(reference[i : i + 4] for i in range(0, len(reference), 4))


def format_reference(value: str | None) -> str:
	"""Format a QRR or SCOR for print, leave anything else as it is."""
	reference = compact(value)
	if reference.startswith("RF"):
		return format_scor(reference)
	if reference.isdigit():
		return format_qrr(reference)
	return reference
