"""Payment files in ISO 20022 pain.001.001.09 after the Swiss Payment Standards 2026.

Source: SIX, Swiss Payment Standards, Implementation Guidelines Customer Credit Transfer Initiation
(pain.001.001.09), valid from 14 November 2026: only version 001.09, structured addresses (town and country
at least) for creditor and debtor.

Supported payment types:
- QR: to a QR-IBAN with a QR reference (QRR), CHF or EUR
- IBAN: to a Swiss or Liechtenstein IBAN, CHF or EUR, with a Creditor Reference (SCOR) or a message
- SEPA: EUR to an IBAN in a SEPA country outside Switzerland and Liechtenstein

Payments to other countries or in other currencies are not supported yet.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from rappen.core import charset, iban, reference
from rappen.core.address import Address
from rappen.core.errors import RappenError, _

NAMESPACE = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.09"
QR, DOMESTIC, SEPA = "QR", "IBAN", "SEPA"
ID_MAX = 35
MESSAGE_MAX = 140
# SEPA countries outside Switzerland and Liechtenstein (EPC list of SEPA countries, EEA and associated)
SEPA_COUNTRIES = frozenset(
	"AT BE BG CY CZ DE DK EE ES FI FR GR HR HU IE IT LT LU LV MT NL PL PT RO SE SI SK "
	"IS NO MC SM VA AD GB GI".split()
)
# Identifiers: letters, digits and a few separators (SPS, restricted character set for references)
_ID = re.compile(r"[A-Za-z0-9/\-?:().,'+ ]{1,35}")


@dataclass(frozen=True)
class Payment:
	"""One credit transfer."""

	end_to_end_id: str
	amount: Decimal
	currency: str
	creditor: Address
	creditor_iban: str
	reference: str = ""
	message: str = ""
	creditor_bic: str = ""

	def __post_init__(self):
		object.__setattr__(self, "amount", Decimal(str(self.amount)).quantize(Decimal("0.01"), ROUND_HALF_UP))
		object.__setattr__(self, "currency", (self.currency or "").upper())
		object.__setattr__(self, "creditor_iban", iban.compact(self.creditor_iban))
		object.__setattr__(self, "reference", reference.compact(self.reference))
		object.__setattr__(self, "message", charset.clean(self.message))
		object.__setattr__(self, "creditor_bic", (self.creditor_bic or "").replace(" ", "").upper())

	@property
	def payment_type(self) -> str | None:
		country = self.creditor_iban[:2]
		if iban.is_qr_iban(self.creditor_iban):
			return QR
		if country in iban.QR_IBAN_COUNTRIES and self.currency in ("CHF", "EUR"):
			return DOMESTIC
		if country in SEPA_COUNTRIES and self.currency == "EUR":
			return SEPA
		return None

	def problems(self) -> list[RappenError]:
		problems: list[RappenError] = []
		if not _ID.fullmatch(self.end_to_end_id or ""):
			problems.append(
				RappenError(
					_("The end-to-end ID {id} needs 1 to 35 letters, digits or separators."),
					id=self.end_to_end_id,
				)
			)
		if self.amount <= 0:
			problems.append(
				RappenError(_("The amount of payment {id} must be positive."), id=self.end_to_end_id)
			)
		try:
			iban.validate_iban(self.creditor_iban)
		except RappenError as error:
			problems.append(error)
			return problems
		kind = self.payment_type
		if kind is None:
			problems.append(
				RappenError(
					_(
						"Payment {id} goes to {country} in {currency}. Rappen pays to Swiss and Liechtenstein IBANs "
						"in CHF or EUR and to SEPA countries in EUR."
					),
					id=self.end_to_end_id,
					country=self.creditor_iban[:2],
					currency=self.currency,
				)
			)
		try:
			reference_type = reference.reference_type(self.reference)
		except RappenError as error:
			problems.append(error)
			reference_type = None
		if kind == QR and reference_type != reference.QRR:
			problems.append(
				RappenError(
					_("Payment {id} goes to a QR-IBAN and needs the QR reference of the QR-bill."),
					id=self.end_to_end_id,
				)
			)
		if kind != QR and reference_type == reference.QRR:
			problems.append(
				RappenError(
					_("Payment {id} has a QR reference, which only works with a QR-IBAN."),
					id=self.end_to_end_id,
				)
			)
		if len(self.message) > MESSAGE_MAX:
			problems.append(
				RappenError(
					_("The message of payment {id} is longer than 140 characters."), id=self.end_to_end_id
				)
			)
		problems += self.creditor.problems()
		return problems


@dataclass(frozen=True)
class PaymentRun:
	"""A pain.001 message: all payments from one account on one execution date."""

	message_id: str
	created: datetime
	execution_date: date
	debtor: Address
	debtor_iban: str
	debtor_bic: str = ""
	batch_booking: bool = False
	payments: tuple[Payment, ...] = field(default_factory=tuple)

	def problems(self) -> list[RappenError]:
		problems: list[RappenError] = []
		if not _ID.fullmatch(self.message_id or ""):
			problems.append(
				RappenError(
					_("The message ID {id} needs 1 to 35 letters, digits or separators."), id=self.message_id
				)
			)
		try:
			account = iban.validate_iban(self.debtor_iban)
			if iban.is_qr_iban(account):
				problems.append(RappenError(_("Payments are made from an IBAN, not from a QR-IBAN.")))
		except RappenError as error:
			problems.append(error)
		problems += self.debtor.problems()
		if not self.payments:
			problems.append(RappenError(_("The payment run contains no payments.")))
		ids = [p.end_to_end_id for p in self.payments]
		if len(ids) != len(set(ids)):
			problems.append(RappenError(_("Every payment needs its own end-to-end ID.")))
		for payment in self.payments:
			problems += payment.problems()
		return problems

	def validate(self) -> "PaymentRun":
		problems = self.problems()
		if problems:
			raise problems[0]
		return self

	def groups(self) -> list[tuple[str, list[Payment]]]:
		"""Payments grouped for the PmtInf blocks: SEPA apart, the rest by currency."""
		keys: dict[str, list[Payment]] = {}
		for payment in self.payments:
			key = SEPA if payment.payment_type == SEPA else payment.currency
			keys.setdefault(key, []).append(payment)
		return list(keys.items())

	def to_xml(self) -> bytes:
		"""The pain.001.001.09 message as UTF-8 XML."""
		self.validate()
		document = ET.Element("Document", xmlns=NAMESPACE)
		root = ET.SubElement(document, "CstmrCdtTrfInitn")
		header = ET.SubElement(root, "GrpHdr")
		_add(header, "MsgId", self.message_id)
		_add(header, "CreDtTm", self.created.replace(microsecond=0).isoformat())
		_add(header, "NbOfTxs", str(len(self.payments)))
		_add(header, "CtrlSum", _amount(sum(p.amount for p in self.payments)))
		ET.SubElement(ET.SubElement(header, "InitgPty"), "Nm").text = self.debtor.name

		for number, (key, payments) in enumerate(self.groups(), start=1):
			block = ET.SubElement(root, "PmtInf")
			_add(block, "PmtInfId", f"{self.message_id[: ID_MAX - 4]}-{number}")
			_add(block, "PmtMtd", "TRF")
			_add(block, "BtchBookg", "true" if self.batch_booking else "false")
			_add(block, "NbOfTxs", str(len(payments)))
			_add(block, "CtrlSum", _amount(sum(p.amount for p in payments)))
			if key == SEPA:
				ET.SubElement(ET.SubElement(ET.SubElement(block, "PmtTpInf"), "SvcLvl"), "Cd").text = "SEPA"
			_add(ET.SubElement(block, "ReqdExctnDt"), "Dt", self.execution_date.isoformat())
			_party(block, "Dbtr", self.debtor)
			ET.SubElement(ET.SubElement(ET.SubElement(block, "DbtrAcct"), "Id"), "IBAN").text = iban.compact(
				self.debtor_iban
			)
			_agent(block, "DbtrAgt", self.debtor_bic, iban.compact(self.debtor_iban))
			if key == SEPA:
				_add(block, "ChrgBr", "SLEV")
			for payment in payments:
				_transaction(block, payment)

		ET.indent(document, space="  ")
		body = ET.tostring(document, encoding="unicode")
		return ('<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n").encode("utf-8")


def _transaction(block: ET.Element, payment: Payment):
	tx = ET.SubElement(block, "CdtTrfTxInf")
	_add(ET.SubElement(tx, "PmtId"), "EndToEndId", payment.end_to_end_id)
	instructed = ET.SubElement(ET.SubElement(tx, "Amt"), "InstdAmt", Ccy=payment.currency)
	instructed.text = _amount(payment.amount)
	if payment.creditor_bic:
		_agent(tx, "CdtrAgt", payment.creditor_bic, "")
	_party(tx, "Cdtr", payment.creditor)
	ET.SubElement(ET.SubElement(ET.SubElement(tx, "CdtrAcct"), "Id"), "IBAN").text = payment.creditor_iban

	kind = reference.reference_type(payment.reference)
	if kind == reference.NON and not payment.message:
		return
	remittance = ET.SubElement(tx, "RmtInf")
	if kind == reference.NON:
		_add(remittance, "Ustrd", payment.message)
		return
	structured = ET.SubElement(remittance, "Strd")
	info = ET.SubElement(structured, "CdtrRefInf")
	code = ET.SubElement(ET.SubElement(info, "Tp"), "CdOrPrtry")
	if kind == reference.QRR:
		_add(code, "Prtry", "QRR")
	else:
		_add(code, "Cd", "SCOR")
	_add(info, "Ref", payment.reference)
	if payment.message:
		# The message of a QR-bill goes into AddtlRmtInf next to the reference (SPS 2026)
		_add(structured, "AddtlRmtInf", payment.message)


def _party(parent: ET.Element, tag: str, address: Address):
	party = ET.SubElement(parent, tag)
	_add(party, "Nm", address.name)
	postal = ET.SubElement(party, "PstlAdr")
	for name, value in (
		("StrtNm", address.street),
		("BldgNb", address.building_number),
		("PstCd", address.postal_code),
		("TwnNm", address.town),
		("Ctry", address.country),
	):
		if value:
			_add(postal, name, value)


def _agent(parent: ET.Element, tag: str, bic: str, account: str):
	institution = ET.SubElement(ET.SubElement(parent, tag), "FinInstnId")
	if bic:
		_add(institution, "BICFI", bic)
	elif account[:2] in iban.QR_IBAN_COUNTRIES:
		# Swiss institution ID (IID) from positions 5 to 9 of the IBAN
		member = ET.SubElement(institution, "ClrSysMmbId")
		_add(ET.SubElement(member, "ClrSysId"), "Cd", "CHBCC")
		_add(member, "MmbId", account[4:9])


def _add(parent: ET.Element, tag: str, text: str) -> ET.Element:
	element = ET.SubElement(parent, tag)
	element.text = text
	return element


def _amount(value: Decimal) -> str:
	return f"{value:.2f}"
