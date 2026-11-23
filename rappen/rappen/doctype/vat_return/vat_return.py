from decimal import Decimal

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, now_datetime

import rappen
from rappen.core import schemas, vat
from rappen.core.errors import RappenError
from rappen.utils import translate

SCHEMA = "ech/eCH-0217/2/eCH-0217-2-0-0.xsd"
SUBMISSIONS = {
	"First submission": vat.FIRST,
	"Correction": vat.CORRECTION,
	"Annual reconciliation": vat.ANNUAL,
}
AMOUNT_FIELDS = (
	"total_consideration",
	"opted",
	"supplies_to_foreign_countries",
	"supplies_abroad",
	"transfer_notification_procedure",
	"supplies_exempt_from_tax",
	"reduction_of_consideration",
	"various_deduction",
	"input_tax_material_and_services",
	"input_tax_investments",
	"subsequent_input_tax_deduction",
	"input_tax_corrections",
	"input_tax_reductions",
	"subsidies",
	"donations",
)


class VATReturn(Document):
	def validate(self):
		if not self.uid:
			self.uid = frappe.get_cached_value("Company", self.company, "tax_id")
		if self.period_till and self.period_from and getdate(self.period_till) < getdate(self.period_from):
			frappe.throw(_("The period ends before it starts."))
		if self.method == "Net tax rate" and not self.rates and self.net_tax_rate:
			self.append("rates", {"kind": "Taxable supply", "rate": self.net_tax_rate})
		self.update_totals()

	def update_totals(self):
		declaration = self.declaration()
		for row, item in zip(
			[r for r in self.rates if r.kind == "Taxable supply"]
			+ [r for r in self.rates if r.kind != "Taxable supply"],
			declaration.supplies + declaration.acquisition_tax,
			strict=True,
		):
			row.tax = float(item.tax)
		self.deductions = float(declaration.deductions)
		self.taxable_turnover = float(declaration.taxable_turnover)
		self.output_tax = float(declaration.output_tax)
		self.input_tax = float(declaration.input_tax)
		self.payable_tax = float(declaration.payable_tax)

	def declaration(self) -> vat.VatReturn:
		amounts = {field: Decimal(str(flt(self.get(field)))) for field in AMOUNT_FIELDS}
		return vat.VatReturn(
			uid=self.uid or "",
			organisation_name=frappe.get_cached_value("Company", self.company, "company_name")
			or self.company,
			period_from=getdate(self.period_from),
			period_till=getdate(self.period_till),
			generated=now_datetime(),
			business_reference=self.name or "",
			method=vat.NET_TAX_RATE if self.method == "Net tax rate" else vat.EFFECTIVE,
			submission=SUBMISSIONS.get(self.submission, vat.FIRST),
			product_version=rappen.__version__[:10],
			various_deduction_description=self.various_deduction_description or "",
			supplies=tuple(
				vat.RateTurnover(Decimal(str(flt(r.rate))), Decimal(str(flt(r.turnover))))
				for r in self.rates
				if r.kind == "Taxable supply"
			),
			acquisition_tax=tuple(
				vat.RateTurnover(Decimal(str(flt(r.rate))), Decimal(str(flt(r.turnover))))
				for r in self.rates
				if r.kind != "Taxable supply"
			),
			**amounts,
		)

	def before_submit(self):
		problems = self.declaration().problems()
		if problems:
			frappe.throw(
				"<br>".join(frappe.utils.escape_html(translate(p)) for p in problems),
				title=_("VAT return not complete"),
			)

	def on_submit(self):
		xml = self.declaration().to_xml()
		try:
			schemas.validate(xml, SCHEMA)
		except RappenError as error:
			frappe.throw(translate(error))
		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"{self.name}.xml",
				"content": xml,
				"is_private": 1,
				"attached_to_doctype": self.doctype,
				"attached_to_name": self.name,
				"attached_to_field": "vat_file",
			}
		).insert()
		self.db_set("vat_file", file.file_url)

	@frappe.whitelist()
	def calculate(self):
		"""Fill turnover, tax rates and input tax from the ledger of the period."""
		from rappen.vat import calculate

		calculate(self)
		self.update_totals()
