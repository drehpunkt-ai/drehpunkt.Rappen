import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, nowdate

from rappen import payments


class PaymentProposal(Document):
	def validate(self):
		if not self.execution_date:
			self.execution_date = add_days(nowdate(), 1)
		if self.bank_account:
			account = frappe.db.get_value(
				"Bank Account", self.bank_account, ["company", "is_company_account"], as_dict=True
			)
			if not account.is_company_account or account.company != self.company:
				frappe.throw(
					_("Bank Account {0} is not an account of company {1}.").format(
						self.bank_account, self.company
					)
				)
		seen = set()
		for row in self.items:
			if row.purchase_invoice in seen:
				frappe.throw(_("Purchase Invoice {0} is in the list twice.").format(row.purchase_invoice))
			seen.add(row.purchase_invoice)
			row.outstanding_amount = frappe.db.get_value(
				"Purchase Invoice", row.purchase_invoice, "outstanding_amount"
			)
		payments.update_items(self)

	def before_submit(self):
		if getdate(self.execution_date) < getdate(nowdate()):
			frappe.throw(_("The execution date lies in the past."))
		if not self.items:
			frappe.throw(_("The payment proposal contains no payments."))
		payments.check(self)

	def on_submit(self):
		self.db_set("payment_file", payments.create_file(self))
		payments.create_payment_entries(self)

	def on_cancel(self):
		payments.cancel_payment_entries(self)

	@frappe.whitelist()
	def get_open_invoices(self):
		"""Add the open purchase invoices that are due until «Invoices due until»."""
		for row in payments.open_invoices(self):
			self.append("items", row)
		payments.update_items(self)
		return len(self.items)
