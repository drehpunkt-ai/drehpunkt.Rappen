"""Errors raised by the core, with messages that the Frappe layer can translate."""


def _(message: str) -> str:
	"""Mark a message for translation without translating it.

	The core does not depend on Frappe. Frappe's extractor still finds every ``_("...")`` call, so the
	message lands in the app's translation catalog, and the Frappe layer translates it when shown.
	"""
	return message


class RappenError(ValueError):
	"""A rule from a Swiss standard is violated.

	``message`` is the untranslated template with ``{name}`` placeholders, ``params`` fills them.
	"""

	def __init__(self, message: str, **params: object):
		self.message = message
		self.params = params
		super().__init__(message.format(**params))
