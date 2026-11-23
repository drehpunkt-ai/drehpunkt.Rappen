"""Checks on Bank Account: IBAN per country, QR-IBAN and the prefix of QR references."""

import frappe
from frappe import _

from rappen.core import iban
from rappen.core.errors import RappenError
from rappen.utils import translate

PREFIX_MAX = 10


def validate(doc, method=None):
	if doc.iban:
		try:
			doc.iban = iban.validate_iban(doc.iban)
		except RappenError as error:
			frappe.throw(translate(error), title=_("Invalid IBAN"))
		if iban.is_qr_iban(doc.iban):
			frappe.throw(
				_(
					"{0} is a QR-IBAN. It only works together with a QR reference, so it belongs in the "
					"field QR-IBAN, not in the field IBAN."
				).format(iban.format_iban(doc.iban)),
				title=_("Invalid IBAN"),
			)

	if doc.get("rappen_qr_iban"):
		try:
			doc.rappen_qr_iban = iban.validate_qr_iban(doc.rappen_qr_iban)
		except RappenError as error:
			frappe.throw(translate(error), title=_("Invalid QR-IBAN"))

	prefix = (doc.get("rappen_qr_reference_prefix") or "").strip()
	if prefix:
		if not doc.get("rappen_qr_iban"):
			frappe.throw(_("A QR reference prefix only applies to a QR-IBAN. Enter the QR-IBAN first."))
		if not (prefix.isdigit() and prefix.isascii() and len(prefix) <= PREFIX_MAX):
			frappe.throw(
				_("The QR reference prefix consists of digits only, at most {0} of them.").format(PREFIX_MAX)
			)
	doc.rappen_qr_reference_prefix = prefix
