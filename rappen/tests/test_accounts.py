import frappe
from frappe.tests import IntegrationTestCase

from rappen.accounts import complete_chart, uses_swiss_chart
from rappen.tests import utils


class TestSwissChart(IntegrationTestCase):
	def test_company_defaults_after_setup_wizard(self):
		company = utils.swiss_company()
		self.assertTrue(uses_swiss_chart(company))
		values = frappe.db.get_value(
			"Company",
			company,
			[
				"default_receivable_account",
				"default_payable_account",
				"default_income_account",
				"round_off_account",
			],
			as_dict=True,
		)
		self.assertTrue(values.default_receivable_account.startswith("1100"))
		self.assertTrue(values.default_payable_account.startswith("2000"))
		self.assertTrue(values.default_income_account.startswith("3400"))
		self.assertTrue(values.round_off_account.startswith("6900"))
		self.assertEqual(
			frappe.db.get_value("Account", values.default_receivable_account, "account_type"), "Receivable"
		)

	def test_second_run_changes_nothing(self):
		company = utils.swiss_company()
		self.assertEqual(complete_chart(company), {"changed": [], "skipped": []})
