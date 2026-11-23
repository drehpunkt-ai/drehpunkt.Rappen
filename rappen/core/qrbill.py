"""QR-bill: content of the Swiss QR Code, the code itself as SVG and the texts of the payment part.

Source: SIX, Swiss Implementation Guidelines for the QR-bill, version 2.3 (valid from 22 November 2025) and
2.4 (from 14 November 2026, unchanged for CHF). Only structured addresses (type S) are allowed.

The QR code is generated here with segno, on the server. Nothing is sent anywhere.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import segno

from rappen.core import charset, iban, reference
from rappen.core.address import Address
from rappen.core.errors import RappenError, _

QR_TYPE = "SPC"
VERSION = "0200"
CODING = "1"
TRAILER = "EPD"
ADDRESS_TYPE = "S"
CURRENCIES = ("CHF", "EUR")
AMOUNT_MIN = Decimal("0.01")
AMOUNT_MAX = Decimal("999999999.99")
MESSAGE_MAX = 140  # unstructured message and billing information together
ALTERNATIVE_MAX = 100
ALTERNATIVES_MAX = 2
PAYLOAD_MAX = 997
QR_VERSION_MAX = 25
SEPARATOR = "\n"

# Size of the Swiss QR Code and of the Swiss cross in its middle, in millimetres
QR_SIZE_MM = 46
CROSS_SIZE_MM = 7

# Fixed texts of the payment part and the receipt (IG QR-bill, chapter 3). Not translated through Frappe,
# because the guidelines prescribe them word for word in these four languages.
LABELS = {
	"de": {
		"payment_part": "Zahlteil",
		"receipt": "Empfangsschein",
		"account": "Konto / Zahlbar an",
		"reference": "Referenz",
		"additional_information": "Zusätzliche Informationen",
		"payable_by": "Zahlbar durch",
		"payable_by_blank": "Zahlbar durch (Name/Adresse)",
		"currency": "Währung",
		"amount": "Betrag",
		"acceptance_point": "Annahmestelle",
		"separate": "Vor der Einzahlung abzutrennen",
	},
	"fr": {
		"payment_part": "Section paiement",
		"receipt": "Récépissé",
		"account": "Compte / Payable à",
		"reference": "Référence",
		"additional_information": "Informations supplémentaires",
		"payable_by": "Payable par",
		"payable_by_blank": "Payable par (nom/adresse)",
		"currency": "Monnaie",
		"amount": "Montant",
		"acceptance_point": "Point de dépôt",
		"separate": "A détacher avant le versement",
	},
	"it": {
		"payment_part": "Sezione pagamento",
		"receipt": "Ricevuta",
		"account": "Conto / Pagabile a",
		"reference": "Riferimento",
		"additional_information": "Informazioni supplementari",
		"payable_by": "Pagabile da",
		"payable_by_blank": "Pagabile da (nome/indirizzo)",
		"currency": "Valuta",
		"amount": "Importo",
		"acceptance_point": "Punto di accettazione",
		"separate": "Da staccare prima del versamento",
	},
	"en": {
		"payment_part": "Payment part",
		"receipt": "Receipt",
		"account": "Account / Payable to",
		"reference": "Reference",
		"additional_information": "Additional information",
		"payable_by": "Payable by",
		"payable_by_blank": "Payable by (name/address)",
		"currency": "Currency",
		"amount": "Amount",
		"acceptance_point": "Acceptance point",
		"separate": "Separate before paying in",
	},
}
DEFAULT_LANGUAGE = "de"


def labels(language: str | None) -> dict[str, str]:
	"""Texts of the payment part in ``language`` (``de``, ``fr``, ``it`` or ``en``, also ``de-CH`` etc.)."""
	return LABELS.get((language or "").split("-")[0].split("_")[0].lower(), LABELS[DEFAULT_LANGUAGE])


def parse_amount(value: object) -> Decimal | None:
	"""Amount rounded to the Rappen (cent), or ``None`` for an open amount."""
	if value is None or value == "":
		return None
	try:
		amount = Decimal(str(value))
	except InvalidOperation:
		raise RappenError(_("The amount {amount} is not a number."), amount=value)
	return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class QRBill:
	"""Everything that goes into the Swiss QR Code."""

	account: str
	creditor: Address
	currency: str = "CHF"
	amount: Decimal | None = None
	debtor: Address | None = None
	reference: str = ""
	message: str = ""
	billing_information: str = ""
	alternative_procedures: tuple[str, ...] = field(default_factory=tuple)

	def __post_init__(self):
		# Normalise once, so that payload, print and checks all see the same values
		object.__setattr__(self, "account", iban.compact(self.account))
		object.__setattr__(self, "currency", (self.currency or "").strip().upper())
		object.__setattr__(self, "amount", parse_amount(self.amount))
		object.__setattr__(self, "reference", reference.compact(self.reference))
		object.__setattr__(self, "message", charset.clean(self.message))
		object.__setattr__(self, "billing_information", charset.clean(self.billing_information))
		object.__setattr__(
			self, "alternative_procedures", tuple(charset.clean(a) for a in self.alternative_procedures)
		)

	@property
	def reference_type(self) -> str:
		return reference.reference_type(self.reference)

	def problems(self) -> list[RappenError]:
		"""Every rule of the guidelines that this QR-bill violates."""
		problems: list[RappenError] = []
		try:
			account = iban.validate_iban(self.account)
		except RappenError as error:
			problems.append(error)
			account = None
		if account and account[:2] not in iban.QR_IBAN_COUNTRIES:
			problems.append(
				RappenError(
					_("A QR-bill needs a Swiss or Liechtenstein IBAN, {iban} is from {country}."),
					iban=account,
					country=account[:2],
				)
			)

		try:
			reference_type = self.reference_type
		except RappenError as error:
			problems.append(error)
			reference_type = None
		if account and reference_type:
			if iban.is_qr_iban(account) and reference_type != reference.QRR:
				problems.append(
					RappenError(_("A QR-IBAN can only be used with a QR reference (QRR)."), iban=account)
				)
			elif not iban.is_qr_iban(account) and reference_type == reference.QRR:
				problems.append(
					RappenError(
						_("A QR reference (QRR) can only be used with a QR-IBAN, {iban} is a regular IBAN."),
						iban=account,
					)
				)

		problems += self.creditor.problems()
		if self.debtor:
			problems += self.debtor.problems()

		if self.currency not in CURRENCIES:
			problems.append(
				RappenError(_("A QR-bill is in CHF or EUR, not in {currency}."), currency=self.currency)
			)
		if self.amount is not None and not AMOUNT_MIN <= self.amount <= AMOUNT_MAX:
			problems.append(
				RappenError(
					_("The amount of a QR-bill is between 0.01 and 999999999.99, {amount} is not."),
					amount=self.amount,
				)
			)

		if len(self.message) + len(self.billing_information) > MESSAGE_MAX:
			problems.append(
				RappenError(
					_(
						"Message and billing information of a QR-bill have at most {limit} characters together, "
						"here they have {length}."
					),
					limit=MESSAGE_MAX,
					length=len(self.message) + len(self.billing_information),
				)
			)
		if len(self.alternative_procedures) > ALTERNATIVES_MAX or any(
			len(a) > ALTERNATIVE_MAX for a in self.alternative_procedures
		):
			problems.append(
				RappenError(
					_("A QR-bill has at most two alternative procedures of at most 100 characters each.")
				)
			)

		if not problems and len(self.payload()) > PAYLOAD_MAX:
			problems.append(
				RappenError(
					_("The content of the QR code has {length} characters, at most {limit} are allowed."),
					length=len(self.payload()),
					limit=PAYLOAD_MAX,
				)
			)
		return problems

	def validate(self) -> "QRBill":
		"""Raise the first problem as ``RappenError``, return ``self`` if there is none."""
		problems = self.problems()
		if problems:
			raise problems[0]
		return self

	def payload(self) -> str:
		"""The text in the Swiss QR Code, elements separated by a line feed."""
		elements = [
			QR_TYPE,
			VERSION,
			CODING,
			self.account,
			*_address_elements(self.creditor),
			*[""] * 7,  # ultimate creditor, reserved for future use
			f"{self.amount:.2f}" if self.amount is not None else "",
			self.currency,
			*(_address_elements(self.debtor) if self.debtor else [""] * 7),
			self.reference_type,
			self.reference,
			self.message,
			TRAILER,
		]
		optional = [self.billing_information, *self.alternative_procedures]
		while optional and not optional[-1]:
			optional.pop()
		return SEPARATOR.join(elements + optional)

	def qr_code(self) -> segno.QRCode:
		"""The Swiss QR Code: byte mode, UTF-8, error correction level M, at most version 25."""
		code = segno.make_qr(self.payload(), error="m", encoding="utf-8", boost_error=False)
		if code.version > QR_VERSION_MAX:
			raise RappenError(
				_("The QR code would need version {version}, at most 25 is allowed. Shorten the texts."),
				version=code.version,
			)
		return code

	def svg(self) -> str:
		"""The Swiss QR Code as SVG, 46 x 46 mm, with the Swiss cross in the middle."""
		return qr_svg(self.qr_code())


def _address_elements(address: Address) -> list[str]:
	return [
		ADDRESS_TYPE,
		address.name,
		address.street,
		address.building_number,
		address.postal_code,
		address.town,
		address.country,
	]


def parse(payload: str) -> QRBill:
	"""Read the content of a Swiss QR Code, e.g. from a hand scanner, and check it."""
	lines = re.split(r"\r\n|\n", (payload or "").strip("\r\n"))
	if len(lines) < 31 or lines[0] != QR_TYPE or lines[2] != CODING:
		raise RappenError(_("This is not the content of a Swiss QR Code."))
	if not lines[1].startswith("02"):
		raise RappenError(_("QR-bill version {version} is not supported."), version=lines[1])
	if lines[30] != TRAILER:
		raise RappenError(_("The QR code content is incomplete: the trailer EPD is missing."))

	def address(first: int) -> Address | None:
		part = lines[first : first + 7]
		if not any(part):
			return None
		if part[0] != ADDRESS_TYPE:
			raise RappenError(
				_(
					"The QR-bill uses an unstructured address (type {type}), which is no longer valid. "
					"Ask the creditor for a new QR-bill."
				),
				type=part[0],
			)
		return Address(*part[1:])

	creditor = address(4)
	if creditor is None:
		raise RappenError(_("The creditor is missing in the QR code."))
	bill = QRBill(
		account=lines[3],
		creditor=creditor,
		amount=lines[18] or None,
		currency=lines[19],
		debtor=address(20),
		reference=lines[28],
		message=lines[29],
		billing_information=lines[31] if len(lines) > 31 else "",
		alternative_procedures=tuple(a for a in lines[32:34] if a),
	)
	if lines[27] != bill.reference_type:
		raise RappenError(
			_("The QR code declares reference type {declared}, but its reference is of type {actual}."),
			declared=lines[27],
			actual=bill.reference_type,
		)
	return bill


def qr_svg(code: segno.QRCode) -> str:
	"""SVG of a QR code without quiet zone, scaled to 46 mm, with the Swiss cross on top."""
	size = len(code.matrix)
	runs = []
	for y, row in enumerate(code.matrix):
		x = 0
		while x < size:
			if row[x]:
				start = x
				while x < size and row[x]:
					x += 1
				runs.append(f"M{start} {y}h{x - start}v1h-{x - start}z")
			else:
				x += 1
	return (
		f'<svg xmlns="http://www.w3.org/2000/svg" width="{QR_SIZE_MM}mm" height="{QR_SIZE_MM}mm" '
		f'viewBox="0 0 {size} {size}" shape-rendering="crispEdges">'
		f'<rect width="{size}" height="{size}" fill="#fff"/>'
		f'<path fill="#000" d="{"".join(runs)}"/>'
		f"{_swiss_cross(size)}"
		"</svg>"
	)


def _swiss_cross(size: int) -> str:
	"""Swiss cross of 7 x 7 mm: white margin, black square, white cross with arms 1/6 longer than wide."""
	scale = size / QR_SIZE_MM
	origin = (QR_SIZE_MM - CROSS_SIZE_MM) / 2 * scale
	return (
		f'<g transform="translate({_n(origin)} {_n(origin)}) scale({_n(scale)})" shape-rendering="geometricPrecision">'
		'<rect width="7" height="7" fill="#fff"/>'
		'<rect x="0.5" y="0.5" width="6" height="6" fill="#000"/>'
		'<rect x="2.915" y="1.55" width="1.17" height="3.9" fill="#fff"/>'
		'<rect x="1.55" y="2.915" width="3.9" height="1.17" fill="#fff"/>'
		"</g>"
	)


def cross_box(size: int) -> tuple[float, float]:
	"""First and last module coordinate covered by the Swiss cross, for tests that simulate it."""
	scale = size / QR_SIZE_MM
	start = (QR_SIZE_MM - CROSS_SIZE_MM) / 2 * scale
	return start, start + CROSS_SIZE_MM * scale


def _n(value: float) -> str:
	return f"{value:.4f}".rstrip("0").rstrip(".")


# Printing


def format_amount(amount: Decimal | None) -> str:
	"""``1 949.75``: space as thousands separator, two decimals (IG QR-bill, 3.5.5)."""
	if amount is None:
		return ""
	whole, cents = f"{amount:.2f}".split(".")
	groups = []
	while whole:
		groups.insert(0, whole[-3:])
		whole = whole[:-3]
	return f"{' '.join(groups)}.{cents}"


def address_lines(address: Address | None) -> list[str]:
	"""Lines of an address on the payment part. The country code is shown for addresses abroad only."""
	if not address:
		return []
	street = " ".join(part for part in (address.street, address.building_number) if part)
	town = " ".join(part for part in (address.postal_code, address.town) if part)
	if address.country and address.country not in iban.QR_IBAN_COUNTRIES:
		town = f"{address.country}-{town}"
	return [line for line in (address.name, street, town) if line]


# Swico syntax S1 for the billing information (structured information for the debtor's accounting)


def _swico_escape(value: str) -> str:
	return value.replace("\\", "\\\\").replace("/", "\\/")


def swico_s1(
	invoice_number: str | None = None,
	invoice_date: date | None = None,
	customer_reference: str | None = None,
	vat_number: str | None = None,
) -> str:
	"""Billing information in Swico syntax S1, e.g. ``//S1/10/10201409/11/190512/30/106017086``.

	``vat_number`` is the Swiss UID, with or without «CHE» and separators; only its nine digits are used.
	Fields without a value are left out, an empty string is returned if there is nothing to tell.
	"""
	parts = []
	if invoice_number:
		parts.append(f"/10/{_swico_escape(charset.clean(invoice_number))}")
	if invoice_date:
		parts.append(f"/11/{invoice_date:%y%m%d}")
	if customer_reference:
		parts.append(f"/20/{_swico_escape(charset.clean(customer_reference))}")
	digits = re.sub(r"\D", "", vat_number or "")
	if len(digits) == 9:
		parts.append(f"/30/{digits}")
	return "//S1" + "".join(parts) if parts else ""
