"""Address: show how it appears on payments and warn about what a structured address cannot hold."""

import frappe
from frappe import _

from rappen.core.address import Address
from rappen.utils import country_code, translate


def payment_address(doc) -> Address:
	"""The address as it appears on QR-bills and in pain.001, named after the address title."""
	return Address.from_line(
		doc.address_title, doc.address_line1, doc.pincode, doc.city, country_code(doc.country)
	)


def onload(doc, method=None):
	address = payment_address(doc)
	doc.set_onload(
		"rappen_payment_address",
		{
			"street": address.street,
			"building_number": address.building_number,
			"postal_code": address.postal_code,
			"town": address.town,
			"country": address.country,
			"problems": [translate(problem) for problem in address.problems()],
		},
	)


def validate(doc, method=None):
	warnings = [translate(problem) for problem in payment_address(doc).problems()]
	if doc.address_line2:
		warnings.append(
			_(
				"Address line 2 ({0}) does not appear on QR-bills and in payment files. They only know street, "
				"building number, postal code, town and country."
			).format(doc.address_line2)
		)
	if warnings:
		frappe.msgprint(
			"<br>".join(frappe.utils.escape_html(warning) for warning in warnings),
			title=_("Address on payments"),
			indicator="orange",
		)
