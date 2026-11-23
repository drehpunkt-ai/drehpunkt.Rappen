"""VAT return from the books: turnover from sales invoices, tax rates from their tax details, input tax from
the input tax accounts (1170, 1171 in the Swiss SME chart). Everything stays editable before submitting.
"""

import frappe
from frappe.utils import flt


def calculate(doc):
	invoices = frappe.get_all(
		"Sales Invoice",
		filters={
			"company": doc.company,
			"docstatus": 1,
			"posting_date": ("between", [doc.period_from, doc.period_till]),
		},
		fields=["name", "base_net_total", "base_grand_total"],
	)
	names = [i.name for i in invoices]
	net = sum(flt(i.base_net_total) for i in invoices)
	gross = sum(flt(i.base_grand_total) for i in invoices)

	taxed: dict[float, float] = {}
	if names:
		for row in frappe.get_all(
			"Item Wise Tax Detail",
			filters={"parenttype": "Sales Invoice", "parent": ("in", names), "rate": (">", 0)},
			fields=["rate", "taxable_amount"],
		):
			taxed[flt(row.rate, 2)] = taxed.get(flt(row.rate, 2), 0) + flt(row.taxable_amount)

	doc.rates = []
	if doc.method == "Net tax rate":
		# Net tax rate method: gross turnover including VAT, taxed at the net tax rate
		doc.total_consideration = gross
		doc.untaxed_turnover = gross - sum(taxed[r] * (1 + r / 100) for r in taxed)
		doc.append(
			"rates",
			{"kind": "Taxable supply", "rate": doc.net_tax_rate, "turnover": gross - doc.untaxed_turnover},
		)
	else:
		doc.total_consideration = net
		doc.untaxed_turnover = net - sum(taxed.values())
		for rate in sorted(taxed, reverse=True):
			doc.append("rates", {"kind": "Taxable supply", "rate": rate, "turnover": taxed[rate]})
		doc.input_tax_material_and_services = _balance(doc, "1170")
		doc.input_tax_investments = _balance(doc, "1171")


def _balance(doc, number: str) -> float:
	account = frappe.db.get_value(
		"Account", {"company": doc.company, "account_number": number, "is_group": 0}, "name"
	)
	if not account:
		return 0.0
	result = frappe.db.sql(
		"""select sum(debit) - sum(credit) from `tabGL Entry`
		where account = %s and is_cancelled = 0 and posting_date between %s and %s""",
		(account, doc.period_from, doc.period_till),
	)
	return flt(result[0][0]) if result else 0.0
