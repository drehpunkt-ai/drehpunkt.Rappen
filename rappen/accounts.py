"""Complete a Swiss chart of accounts (KMU numbering) so that ERPNext can post invoices and payments.

The chart «Schulkontenrahmen VEB» that ERPNext ships for Switzerland only marks cash (1000) and bank (1020).
Without account types for receivables, payables, revenue and VAT, ERPNext sets no default accounts for the
company, and the first sales invoice fails. ``complete_chart`` adds the missing types by account number and
fills empty company defaults. It never changes an account type or a default that is set already.
"""

import frappe
from frappe import _

# Account number in the Swiss SME chart (KMU-Kontenrahmen) and the ERPNext account type
ACCOUNT_TYPES = {
	"1100": "Receivable",
	"1170": "Tax",
	"1171": "Tax",
	"2000": "Payable",
	"2200": "Tax",
	"3000": "Income Account",
	"3200": "Income Account",
	"3400": "Income Account",
	"3600": "Income Account",
	"4200": "Cost of Goods Sold",
	"4400": "Expense Account",
}

# Company default and the account number it points to
COMPANY_DEFAULTS = {
	"default_receivable_account": "1100",
	"default_payable_account": "2000",
	"default_income_account": "3400",
	"default_expense_account": "4200",
	"round_off_account": "6900",
	"exchange_gain_loss_account": "6900",
}


def _account(company: str, number: str) -> str | None:
	return frappe.db.get_value(
		"Account", {"company": company, "account_number": number, "is_group": 0}, "name"
	)


@frappe.whitelist()
def complete_chart(company: str) -> dict[str, list[str]]:
	"""Add missing account types and company defaults. Returns what was changed and what was skipped."""
	frappe.has_permission("Company", "write", company, throw=True)
	changed, skipped = [], []

	for number, account_type in ACCOUNT_TYPES.items():
		name = _account(company, number)
		if not name or frappe.db.get_value("Account", name, "account_type"):
			continue
		try:
			account = frappe.get_doc("Account", name)
			account.account_type = account_type
			account.save()
			changed.append(_("{0}: account type {1}").format(name, _(account_type)))
		except frappe.ValidationError as error:
			frappe.clear_last_message()
			skipped.append(f"{name}: {error}")

	values = {}
	doc = frappe.get_doc("Company", company)
	for fieldname, number in COMPANY_DEFAULTS.items():
		name = _account(company, number)
		if name and not doc.get(fieldname):
			values[fieldname] = name
	if not doc.round_off_cost_center and doc.cost_center:
		values["round_off_cost_center"] = doc.cost_center
	if values:
		doc.update(values)
		doc.save()
		label = {f.fieldname: _(f.label) for f in doc.meta.fields}
		changed += [f"{label.get(field, field)}: {value}" for field, value in values.items()]
	return {"changed": changed, "skipped": skipped}


def uses_swiss_chart(company: str) -> bool:
	"""True if the company's accounts follow the Swiss SME numbering (receivables on 1100, revenue on 3400)."""
	return bool(_account(company, "1100") and _account(company, "2000") and _account(company, "3400"))


def after_setup_wizard(args=None):
	"""Complete the chart right after the setup wizard for companies in Switzerland."""
	for company in frappe.get_all(
		"Company", filters={"country": ("in", ["Switzerland", "Liechtenstein"])}, pluck="name"
	):
		if uses_swiss_chart(company):
			complete_chart(company)
