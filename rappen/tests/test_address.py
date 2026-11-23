import frappe
from frappe.tests import IntegrationTestCase


def address(**fields):
	return frappe.get_doc(
		{
			"doctype": "Address",
			"address_title": "Muster AG",
			"address_type": "Billing",
			"address_line1": "Musterstrasse 12a",
			"pincode": "8000",
			"city": "Zürich",
			"country": "Switzerland",
			**fields,
		}
	)


def warnings():
	return " ".join(str(message.get("message", "")) for message in frappe.get_message_log())


class TestAddress(IntegrationTestCase):
	def setUp(self):
		frappe.clear_messages()

	def test_payment_address_on_load(self):
		doc = address().insert()
		doc.run_method("onload")
		self.assertEqual(
			doc.get_onload().rappen_payment_address,
			{
				"street": "Musterstrasse",
				"building_number": "12a",
				"postal_code": "8000",
				"town": "Zürich",
				"country": "CH",
				"problems": [],
			},
		)

	def test_no_warning_for_a_complete_address(self):
		address().insert()
		self.assertEqual(warnings(), "")

	def test_warns_about_address_line_2(self):
		address(address_line2="c/o Buchhaltung").insert()
		self.assertIn("c/o Buchhaltung", warnings())

	def test_warns_about_swiss_postal_code(self):
		address(pincode="80000").insert()
		self.assertIn("80000", warnings())
