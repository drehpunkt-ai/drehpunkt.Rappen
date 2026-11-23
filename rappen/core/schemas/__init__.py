"""XML schemas for validating generated files.

- ``pain.001.001.09.ch.03.xsd``: Swiss version of pain.001.001.09 by SIX (www.iso-payments.ch), unchanged,
  with its copyright notice. Used to check every payment file before it is offered for download.
- ``ech/``: eCH-0217 V2.0.0 (VAT return for the ESTV) and the eCH schemas it imports, unchanged from
  www.ech.ch/xmlns. Their imports point to www.ech.ch; a resolver maps them to these files, so nothing is
  downloaded.

Validation needs lxml, which ERPNext installs anyway.
"""

from functools import cache
from pathlib import Path

from rappen.core.errors import RappenError, _

SCHEMAS = Path(__file__).parent


ECH_URL = "http://www.ech.ch/xmlns/"


def _parser():
	"""XML parser that never goes to the network and finds eCH schemas in the package."""
	from lxml import etree

	class LocalEch(etree.Resolver):
		def resolve(self, url, public_id, context):
			for prefix in (ECH_URL, ECH_URL.replace("http:", "https:")):
				if url.startswith(prefix):
					return self.resolve_filename(str(SCHEMAS / "ech" / url[len(prefix) :]), context)
			return None

	parser = etree.XMLParser(resolve_entities=False, no_network=True)
	parser.resolvers.add(LocalEch())
	return parser


@cache
def _schema(name: str):
	from lxml import etree

	return etree.XMLSchema(etree.parse(str(SCHEMAS / name), _parser()))


def validate(xml: bytes, name: str) -> None:
	"""Raise ``RappenError`` with the first schema violation of ``xml`` against the schema ``name``."""
	from lxml import etree

	parser = etree.XMLParser(resolve_entities=False, no_network=True)
	document = etree.fromstring(xml, parser)
	schema = _schema(name)
	if not schema.validate(document):
		error = schema.error_log.last_error
		raise RappenError(
			_("The generated file does not match the schema {schema}: line {line}, {detail}"),
			schema=name,
			line=error.line,
			detail=error.message,
		)
