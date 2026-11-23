import frappe
from frappe import _

from rappen.core.errors import RappenError


def translate(error: RappenError) -> str:
	"""The message of a core error in the user's language."""
	return _(error.message).format(**error.params)


def country_code(country: str | None) -> str:
	"""ISO 3166-1 alpha-2 code of an ERPNext country, e.g. ``CH`` for «Switzerland»."""
	if not country:
		return ""
	return (frappe.get_cached_value("Country", country, "code") or "").upper()
