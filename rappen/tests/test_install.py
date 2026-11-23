import frappe
from frappe.tests import IntegrationTestCase

from rappen.custom_fields import get_custom_fields


class TestInstall(IntegrationTestCase):
	def test_custom_fields_exist(self):
		for doctype, fields in get_custom_fields().items():
			meta = frappe.get_meta(doctype)
			for field in fields:
				with self.subTest(doctype=doctype, fieldname=field["fieldname"]):
					self.assertIsNotNone(meta.get_field(field["fieldname"]))
