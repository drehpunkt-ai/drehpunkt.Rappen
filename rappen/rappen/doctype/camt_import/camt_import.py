import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.file_manager import get_file

from rappen.banking import Importer
from rappen.core import camt
from rappen.core.errors import RappenError
from rappen.utils import translate


class CAMTImport(Document):
	def validate(self):
		if (
			self.bank_account
			and frappe.db.get_value("Bank Account", self.bank_account, "company") != self.company
		):
			frappe.throw(
				_("Bank Account {0} does not belong to company {1}.").format(self.bank_account, self.company)
			)

	@frappe.whitelist()
	def run_import(self):
		"""Read the attached camt file and create the Bank Transactions."""
		self.check_permission("write")
		if self.status != "Draft":
			frappe.throw(_("This file has been imported already."))
		content = get_file(self.file)[1]
		if isinstance(content, str):
			content = content.encode()
		try:
			statements = camt.parse(content)
			if not statements:
				raise RappenError(_("The file contains no statement."))
		except RappenError as error:
			self.status = "Failed"
			self.error_log = translate(error)
			self.save()
			return
		Importer(self).run(statements)
		self.save()
