"""QR-bill for Sales Invoice and Dunning: payment reference, the bill's content and the payment part."""

import re

import frappe
from frappe import _
from frappe.model.naming import getseries
from frappe.utils import flt, getdate
from markupsafe import Markup

from rappen.core import iban, qrbill, reference
from rappen.core.address import Address
from rappen.core.errors import RappenError
from rappen.utils import country_code, translate

# Digit that keeps QR references of different doctypes apart: same name digits, different reference
DOCTYPE_CODES = {"Sales Invoice": "1", "Dunning": "2"}
REFERENCE_DOCTYPES = tuple(DOCTYPE_CODES)
FALLBACK_SERIES = "RAPPEN-REF-"


# Bank account and payment reference


def company_bank_account(company: str) -> str | None:
	"""The company's default bank account, or its only one."""
	filters = {"is_company_account": 1, "company": company, "disabled": 0}
	default = frappe.db.get_value("Bank Account", {**filters, "is_default": 1}, "name")
	if default:
		return default
	accounts = frappe.get_all("Bank Account", filters=filters, pluck="name", limit=2)
	return accounts[0] if len(accounts) == 1 else None


def set_payment_reference(doc, method=None):
	"""Choose the bank account and set the payment reference (validate of Sales Invoice and Dunning).

	QR reference (QRR) if the bank account has a QR-IBAN, Creditor Reference (SCOR) if it has an IBAN only.
	The reference is derived from the document name, so it stays the same on every save.
	"""
	if not doc.get("rappen_bank_account"):
		doc.rappen_bank_account = company_bank_account(doc.company)

	account = (
		frappe.db.get_value(
			"Bank Account",
			doc.rappen_bank_account,
			["iban", "rappen_qr_iban", "rappen_qr_reference_prefix"],
			as_dict=True,
		)
		if doc.rappen_bank_account
		else None
	)
	if not account or not needs_payment_part(doc) or not (account.rappen_qr_iban or account.iban):
		doc.rappen_reference_type = reference.NON
		doc.rappen_payment_reference = ""
		return

	wanted = reference.QRR if account.rappen_qr_iban else reference.SCOR
	if doc.get("rappen_payment_reference") and doc.get("rappen_reference_type") == wanted:
		return
	doc.rappen_reference_type = wanted
	doc.rappen_payment_reference = _unique_reference(doc, wanted, account.rappen_qr_reference_prefix or "")


def _unique_reference(doc, kind: str, prefix: str) -> str:
	candidate = _reference_from_name(doc, kind, prefix)
	while not candidate or _reference_taken(doc, candidate):
		counter = getseries(FALLBACK_SERIES, 9)
		candidate = _make_reference(kind, prefix, DOCTYPE_CODES[doc.doctype] + "9" + counter)
	return candidate


def _reference_from_name(doc, kind: str, prefix: str) -> str | None:
	if kind == reference.QRR:
		digits = re.sub(r"\D", "", doc.name or "")
		room = reference.QRR_LENGTH - 1 - len(prefix) - 1
		return _make_reference(kind, prefix, DOCTYPE_CODES[doc.doctype] + digits[-room:]) if digits else None
	body = re.sub(r"[^A-Z0-9]", "", (doc.name or "").upper())
	return _make_reference(kind, prefix, body[-reference.SCOR_MAX_BODY :]) if body else None


def _make_reference(kind: str, prefix: str, body: str) -> str:
	if kind == reference.QRR:
		return reference.make_qrr(prefix + body)
	return reference.make_scor(body[-reference.SCOR_MAX_BODY :])


def _reference_taken(doc, value: str) -> bool:
	for doctype in REFERENCE_DOCTYPES:
		filters = {"rappen_payment_reference": value}
		if doctype == doc.doctype:
			filters["name"] = ("!=", doc.name)
		if frappe.db.exists(doctype, filters):
			return True
	return False


# Content of the QR-bill


def needs_payment_part(doc) -> bool:
	"""No payment part for credit notes and for currencies other than CHF and EUR."""
	if doc.doctype == "Sales Invoice" and doc.get("is_return"):
		return False
	return doc.get("currency") in qrbill.CURRENCIES


def amount_due(doc) -> float:
	"""What the customer still has to pay on this document."""
	if doc.doctype == "Dunning":
		return flt(doc.grand_total)
	if doc.docstatus == 1:
		return flt(doc.outstanding_amount)
	total = flt(doc.rounded_total) or flt(doc.grand_total)
	return total - flt(doc.get("total_advance")) - flt(doc.get("write_off_amount"))


def _address(name: str | None, address_name: str | None) -> Address | None:
	if not address_name:
		return None
	values = frappe.db.get_value(
		"Address", address_name, ["address_line1", "pincode", "city", "country"], as_dict=True
	)
	if not values:
		return None
	return Address.from_line(
		name, values.address_line1, values.pincode, values.city, country_code(values.country)
	)


def _company_address_name(doc) -> str | None:
	if doc.get("company_address"):
		return doc.company_address
	from erpnext.setup.doctype.company.company import get_default_company_address

	return get_default_company_address(doc.company)


def build_qr_bill(doc) -> qrbill.QRBill:
	"""The QR-bill of a Sales Invoice or Dunning. Raises ``RappenError`` if something is missing."""
	if not doc.get("rappen_bank_account"):
		raise RappenError(_("No company bank account with an IBAN is set for the QR-bill."))
	account = frappe.db.get_value(
		"Bank Account", doc.rappen_bank_account, ["iban", "rappen_qr_iban"], as_dict=True
	)
	account_number = (
		account.rappen_qr_iban if doc.get("rappen_reference_type") == reference.QRR else account.iban
	) or account.iban

	company_name = frappe.get_cached_value("Company", doc.company, "company_name") or doc.company
	creditor = _address(company_name, _company_address_name(doc)) or Address(name=company_name)
	debtor = _address(doc.customer_name, doc.get("customer_address"))

	if doc.doctype == "Dunning":
		message = _("Dunning {0}", context="Rappen").format(doc.name)
		billing_information = ""
	else:
		message = _("Invoice {0}", context="Rappen").format(doc.name)
		billing_information = qrbill.swico_s1(
			invoice_number=doc.name,
			invoice_date=getdate(doc.posting_date),
			customer_reference=doc.get("po_no"),
			vat_number=frappe.get_cached_value("Company", doc.company, "tax_id"),
		)
		if len(message) + len(billing_information) > qrbill.MESSAGE_MAX:
			billing_information = ""

	amount = amount_due(doc)
	return qrbill.QRBill(
		account=account_number or "",
		creditor=creditor,
		currency=doc.currency,
		amount=amount if amount > 0 else None,
		debtor=debtor,
		reference=doc.get("rappen_payment_reference") or "",
		message=message,
		billing_information=billing_information,
	)


def sender_line(doc) -> str:
	"""``Muster AG, Bahnhofstrasse 12a, 8000 Zürich`` for the sender line above the recipient."""
	company_name = frappe.get_cached_value("Company", doc.company, "company_name") or doc.company
	address = _address(company_name, _company_address_name(doc))
	return ", ".join(qrbill.address_lines(address)) if address else company_name


# Payment part


def payment_part_html(doc, page: bool = True, language: str | None = None) -> Markup:
	"""HTML of the payment part with receipt for a print format.

	``page=True`` puts it on a page of its own, at the bottom edge of the paper. ``page=False`` returns only
	the 210 x 105 mm block, to be placed by the print format. Problems are shown in the payment part instead
	of the QR code, so that a wrong QR-bill never leaves the house unnoticed.
	"""
	if not needs_payment_part(doc):
		return Markup("")
	labels = qrbill.labels(language or frappe.local.lang)
	context = {"labels": labels, "page": page, "problem_title": _("This QR-bill cannot be paid:")}
	try:
		bill = build_qr_bill(doc)
		problems = bill.problems()
		svg = bill.svg() if not problems else ""
	except RappenError as error:
		bill, problems, svg = None, [error], ""

	if problems:
		context["problems"] = [translate(problem) for problem in problems]
	else:
		additional = [line for line in (bill.message, bill.billing_information) if line]
		context.update(
			{
				"account": iban.format_iban(bill.account),
				"creditor": qrbill.address_lines(bill.creditor),
				"debtor": qrbill.address_lines(bill.debtor),
				"reference": reference.format_reference(bill.reference),
				"currency": bill.currency,
				"amount": qrbill.format_amount(bill.amount),
				"additional_information": additional,
				"alternative_procedures": [_split_alternative(a) for a in bill.alternative_procedures],
				"qr_svg": Markup(svg),
			}
		)
	return Markup(frappe.render_template("rappen/templates/includes/rappen_payment_part.html", context))


def _split_alternative(value: str) -> tuple[str, str]:
	name, _sep, rest = value.partition(":")
	return (f"{name}:", rest.strip()) if rest else ("", value)
