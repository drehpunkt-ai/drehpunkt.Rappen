"""Functions for print formats. Every function defined here is available in Jinja under its own name."""

from markupsafe import Markup


def rappen_payment_part(doc, page: bool = True, language: str | None = None) -> Markup:
	"""Payment part with receipt of the QR-bill for a Sales Invoice or Dunning.

	``{{ rappen_payment_part(doc) }}`` puts it on a page of its own, at the bottom edge of the paper.
	``{{ rappen_payment_part(doc, page=False) }}`` returns only the 210 x 105 mm block, to be placed at the
	bottom of a page by the print format itself.
	"""
	from rappen.qr import payment_part_html

	return payment_part_html(doc, page=page, language=language or doc.get("language"))


def rappen_sender_line(doc) -> str:
	"""Company and address in one line, printed small above the recipient in the envelope window."""
	from rappen.qr import sender_line

	return sender_line(doc)


def rappen_dunning_title(doc) -> str:
	"""Title of a dunning letter, e.g. «1. Mahnung»."""
	from rappen.dunning import dunning_title

	return dunning_title(doc)
