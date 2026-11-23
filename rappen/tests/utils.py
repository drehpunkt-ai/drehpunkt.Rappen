"""Test data for integration tests: a Swiss company with bank accounts, a customer and an item.

The site needs a company in Switzerland with CHF, as created by the setup wizard (see the CI workflow). All
names and numbers are made up; IBANs are the samples of SIX.
"""

import frappe
from frappe.utils import add_days, today

IBAN = "CH9300762011623852957"
QR_IBAN = "CH4431999123000889012"
BANK = "Rappen Testbank"
CUSTOMER = "Anna Beispiel"
ITEM = "RAPPEN-TEST"


def swiss_company() -> str:
	company = frappe.db.get_value("Company", {"country": "Switzerland", "default_currency": "CHF"}, "name")
	if not company:
		raise unittest_skip("No company in Switzerland with CHF; run the setup wizard as in the CI workflow.")
	return company


def unittest_skip(message: str):
	import unittest

	return unittest.SkipTest(message)


def company_address(company: str) -> str:
	name = frappe.db.get_value(
		"Dynamic Link",
		{"link_doctype": "Company", "link_name": company, "parenttype": "Address"},
		"parent",
	)
	if name:
		return name
	address = frappe.get_doc(
		{
			"doctype": "Address",
			"address_title": company,
			"address_type": "Billing",
			"address_line1": "Bahnhofstrasse 12a",
			"pincode": "8000",
			"city": "Zürich",
			"country": "Switzerland",
			"is_your_company_address": 1,
			"is_primary_address": 1,
			"links": [{"link_doctype": "Company", "link_name": company}],
		}
	).insert()
	return address.name


def ledger_bank_account(company: str) -> str:
	account = frappe.db.get_value(
		"Account", {"company": company, "account_type": "Bank", "is_group": 0}, "name"
	)
	if account:
		return account
	parent = frappe.db.get_value(
		"Account",
		{"company": company, "root_type": "Asset", "is_group": 1, "parent_account": ("is", "set")},
		"name",
	)
	return (
		frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": BANK,
				"parent_account": parent,
				"company": company,
				"account_type": "Bank",
				"account_currency": "CHF",
			}
		)
		.insert()
		.name
	)


def bank_account(
	company: str, name: str, iban: str = IBAN, qr_iban: str | None = None, default: bool = False
) -> str:
	if not frappe.db.exists("Bank", BANK):
		frappe.get_doc({"doctype": "Bank", "bank_name": BANK}).insert()
	existing = frappe.db.get_value("Bank Account", {"account_name": name, "bank": BANK}, "name")
	if existing:
		return existing
	return (
		frappe.get_doc(
			{
				"doctype": "Bank Account",
				"account_name": name,
				"bank": BANK,
				"is_company_account": 1,
				"company": company,
				"account": ledger_bank_account(company),
				"iban": iban,
				"rappen_qr_iban": qr_iban,
				"is_default": int(default),
			}
		)
		.insert()
		.name
	)


def customer() -> str:
	if not frappe.db.exists("Customer", CUSTOMER):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": CUSTOMER,
				"customer_type": "Individual",
				"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
				"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
			}
		).insert()
	if not frappe.db.get_value(
		"Dynamic Link", {"link_doctype": "Customer", "link_name": CUSTOMER, "parenttype": "Address"}, "parent"
	):
		frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": CUSTOMER,
				"address_type": "Billing",
				"address_line1": "Route de Genève 7bis",
				"pincode": "1260",
				"city": "Nyon",
				"country": "Switzerland",
				"is_primary_address": 1,
				"links": [{"link_doctype": "Customer", "link_name": CUSTOMER}],
			}
		).insert()
	return CUSTOMER


def customer_address() -> str:
	return frappe.db.get_value(
		"Dynamic Link",
		{"link_doctype": "Customer", "link_name": customer(), "parenttype": "Address"},
		"parent",
	)


def item() -> str:
	if not frappe.db.exists("Item", ITEM):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": ITEM,
				"item_name": "Beratung",
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
				"stock_uom": frappe.db.get_value("UOM", {"name": ("in", ["Nos", "Unit", "Hour"])}, "name")
				or "Nos",
				"is_stock_item": 0,
			}
		).insert()
	return ITEM


def sales_invoice(company: str, rate: float = 1949.75, submit: bool = True, **fields):
	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": company,
			"customer": customer(),
			"customer_address": customer_address(),
			"company_address": company_address(company),
			"posting_date": today(),
			"due_date": add_days(today(), 30),
			"currency": "CHF",
			"items": [{"item_code": item(), "qty": 1, "rate": rate}],
			**fields,
		}
	)
	invoice.set_missing_values()
	invoice.insert()
	if submit:
		invoice.submit()
	return invoice
