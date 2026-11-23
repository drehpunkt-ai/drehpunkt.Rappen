"""Swiss VAT return (MWST-Abrechnung) as XML after eCH-0217 V2.0.0 for the ESTV ePortal.

Source: eCH-0217 V2.0.0 «MWST-Abrechnung», schema eCH-0217-2-0-0.xsd. Supported: effective reporting method
(effektive Abrechnungsmethode) and net tax rate method (Saldosteuersatzmethode), first submission, correction
and annual reconciliation. The numbers in the comments are the boxes (Ziffern) of the ESTV form.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from rappen.core.errors import RappenError, _

NAMESPACE = "http://www.ech.ch/xmlns/eCH-0217/2"
NAMESPACE_0058 = "http://www.ech.ch/xmlns/eCH-0058/5"
EFFECTIVE, NET_TAX_RATE = "effective", "net_tax_rate"
FIRST, CORRECTION, ANNUAL = 1, 2, 3
AGREED, RECEIVED = 1, 2  # vereinbarte und vereinnahmte Entgelte
CENT = Decimal("0.01")
_UID_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4)


def money(value) -> Decimal:
	return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def validate_uid(value: str | None) -> str:
	"""Swiss business identification number (UID) as ``CHE123456789``, check digit modulo 11."""
	digits = re.sub(r"\D", "", value or "")
	if not (value or "").upper().lstrip().startswith("CHE") or len(digits) != 9:
		raise RappenError(_("{uid} is not a UID. A UID looks like CHE-123.456.789."), uid=value or "")
	remainder = sum(int(d) * w for d, w in zip(digits[:8], _UID_WEIGHTS, strict=True)) % 11
	check = 0 if remainder == 0 else 11 - remainder
	if check == 10 or check != int(digits[8]):
		raise RappenError(_("UID {uid} is invalid: the check digit does not match."), uid=value)
	return "CHE" + digits


@dataclass(frozen=True)
class RateTurnover:
	"""Turnover at one tax rate (in percent) and the tax on it."""

	rate: Decimal
	turnover: Decimal

	def __post_init__(self):
		object.__setattr__(self, "rate", Decimal(str(self.rate)).quantize(CENT))
		object.__setattr__(self, "turnover", money(self.turnover))

	@property
	def tax(self) -> Decimal:
		return money(self.turnover * self.rate / 100)


@dataclass(frozen=True)
class VatReturn:
	uid: str
	organisation_name: str
	period_from: date
	period_till: date
	generated: datetime
	business_reference: str
	method: str = EFFECTIVE
	submission: int = FIRST
	reporting: int = AGREED
	product_version: str = "0"
	# Turnover (Ziffern 200 to 280)
	total_consideration: Decimal = Decimal(0)  # 200
	opted: Decimal = Decimal(0)  # 205, effective method only
	supplies_to_foreign_countries: Decimal = Decimal(0)  # 220
	supplies_abroad: Decimal = Decimal(0)  # 221
	transfer_notification_procedure: Decimal = Decimal(0)  # 225
	supplies_exempt_from_tax: Decimal = Decimal(0)  # 230
	reduction_of_consideration: Decimal = Decimal(0)  # 235
	various_deduction: Decimal = Decimal(0)  # 280
	various_deduction_description: str = ""
	# Tax (Ziffern 302 to 383)
	supplies: tuple[RateTurnover, ...] = field(default_factory=tuple)
	acquisition_tax: tuple[RateTurnover, ...] = field(default_factory=tuple)  # 382/383
	# Input tax, effective method only (Ziffern 400 to 420)
	input_tax_material_and_services: Decimal = Decimal(0)  # 400
	input_tax_investments: Decimal = Decimal(0)  # 405
	subsequent_input_tax_deduction: Decimal = Decimal(0)  # 410
	input_tax_corrections: Decimal = Decimal(0)  # 415
	input_tax_reductions: Decimal = Decimal(0)  # 420
	# Other flows of funds (Ziffern 900, 910)
	subsidies: Decimal = Decimal(0)
	donations: Decimal = Decimal(0)

	@property
	def deductions(self) -> Decimal:
		"""Ziffer 289: total of the deductions 220 to 280."""
		return money(
			self.supplies_to_foreign_countries
			+ self.supplies_abroad
			+ self.transfer_notification_procedure
			+ self.supplies_exempt_from_tax
			+ self.reduction_of_consideration
			+ self.various_deduction
		)

	@property
	def taxable_turnover(self) -> Decimal:
		"""Ziffer 299: taxable turnover."""
		return money(self.total_consideration) - self.deductions

	@property
	def output_tax(self) -> Decimal:
		"""Ziffer 399: tax on supplies and on acquisitions."""
		return money(sum((s.tax for s in self.supplies + self.acquisition_tax), Decimal(0)))

	@property
	def input_tax(self) -> Decimal:
		"""Ziffer 479: input tax, net of corrections and reductions."""
		if self.method != EFFECTIVE:
			return Decimal(0)
		return money(
			self.input_tax_material_and_services
			+ self.input_tax_investments
			+ self.subsequent_input_tax_deduction
			- self.input_tax_corrections
			- self.input_tax_reductions
		)

	@property
	def payable_tax(self) -> Decimal:
		"""Ziffer 500 (positive) or credit 510 (negative)."""
		return self.output_tax - self.input_tax

	def problems(self) -> list[RappenError]:
		problems: list[RappenError] = []
		try:
			validate_uid(self.uid)
		except RappenError as error:
			problems.append(error)
		if self.period_till < self.period_from:
			problems.append(RappenError(_("The period ends before it starts.")))
		if self.method not in (EFFECTIVE, NET_TAX_RATE):
			problems.append(RappenError(_("Unknown VAT method {method}."), method=self.method))
		if self.method == NET_TAX_RATE and len({s.rate for s in self.supplies}) > 2:
			problems.append(RappenError(_("The net tax rate method allows at most two net tax rates.")))
		turnover_at_rates = money(sum((s.turnover for s in self.supplies), Decimal(0)))
		if turnover_at_rates != self.taxable_turnover:
			problems.append(
				RappenError(
					_(
						"The taxable turnover (box 299: {taxable}) must equal the turnover at the tax rates "
						"({at_rates}). Assign the difference to exports, supplies abroad, exempt supplies or "
						"deductions."
					),
					taxable=self.taxable_turnover,
					at_rates=turnover_at_rates,
				)
			)
		if self.various_deduction and not self.various_deduction_description.strip():
			problems.append(RappenError(_("Various deductions (box 280) need a description.")))
		return problems

	def validate(self) -> "VatReturn":
		problems = self.problems()
		if problems:
			raise problems[0]
		return self

	def to_xml(self) -> bytes:
		self.validate()
		ET.register_namespace("eCH-0217", NAMESPACE)
		ET.register_namespace("eCH-0058", NAMESPACE_0058)
		root = ET.Element(_q("VATDeclaration"))
		info = _sub(root, "generalInformation")
		_add(info, "uid", validate_uid(self.uid))
		_add(info, "organisationName", self.organisation_name[:255])
		_add(info, "generationTime", self.generated.replace(microsecond=0).isoformat())
		_add(info, "reportingPeriodFrom", self.period_from.isoformat())
		_add(info, "reportingPeriodTill", self.period_till.isoformat())
		_add(info, "typeOfSubmission", str(self.submission))
		_add(info, "formOfReporting", str(self.reporting))
		_add(info, "businessReferenceId", self.business_reference[:50])
		application = _sub(info, "sendingApplication")
		for tag, value in (
			("manufacturer", "Drehpunkt"),
			("product", "Rappen"),
			("productVersion", self.product_version),
		):
			ET.SubElement(application, f"{{{NAMESPACE_0058}}}{tag}").text = value[
				: 30 if tag != "productVersion" else 10
			]

		turnover = _sub(root, "turnoverComputation")
		_add(turnover, "totalConsideration", _amount(self.total_consideration))
		for tag, value in (
			("suppliesToForeignCountries", self.supplies_to_foreign_countries),
			("suppliesAbroad", self.supplies_abroad),
			("transferNotificationProcedure", self.transfer_notification_procedure),
			("suppliesExemptFromTax", self.supplies_exempt_from_tax),
			("reductionOfConsideration", self.reduction_of_consideration),
		):
			if value:
				_add(turnover, tag, _amount(value))
		if self.various_deduction:
			various = _sub(turnover, "variousDeduction")
			_add(various, "amountVariousDeduction", _amount(self.various_deduction))
			_add(various, "descriptionVariousDeduction", self.various_deduction_description.strip())

		if self.method == EFFECTIVE:
			method = _sub(root, "effectiveReportingMethod")
			_add(method, "grossOrNet", "1")  # 1 = net amounts (recommended)
			if self.opted:
				_add(method, "opted", _amount(self.opted))
		else:
			method = _sub(root, "netTaxRateMethod")
		for tag, items in (("suppliesPerTaxRate", self.supplies), ("acquisitionTax", self.acquisition_tax)):
			for item in items:
				element = _sub(method, tag)
				_add(element, "taxRate", f"{item.rate:.2f}")
				_add(element, "turnover", _amount(item.turnover))
		if self.method == EFFECTIVE:
			for tag, value in (
				("inputTaxMaterialAndServices", self.input_tax_material_and_services),
				("inputTaxInvestments", self.input_tax_investments),
				("subsequentInputTaxDeduction", self.subsequent_input_tax_deduction),
				("inputTaxCorrections", self.input_tax_corrections),
				("inputTaxReductions", self.input_tax_reductions),
			):
				if value:
					_add(method, tag, _amount(value))

		_add(root, "payableTax", _amount(self.payable_tax))
		if self.subsidies or self.donations:
			other = _sub(root, "otherFlowsOfFunds")
			if self.subsidies:
				_add(other, "subsidies", _amount(self.subsidies))
			if self.donations:
				_add(other, "donations", _amount(self.donations))

		ET.indent(root, space="  ")
		body = ET.tostring(root, encoding="unicode")
		return ('<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n").encode("utf-8")


def _q(tag: str) -> str:
	return f"{{{NAMESPACE}}}{tag}"


def _sub(parent: ET.Element, tag: str) -> ET.Element:
	return ET.SubElement(parent, _q(tag))


def _add(parent: ET.Element, tag: str, text: str) -> ET.Element:
	element = _sub(parent, tag)
	element.text = text
	return element


def _amount(value) -> str:
	return f"{money(value):.2f}"
