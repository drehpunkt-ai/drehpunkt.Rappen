import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from rappen.custom_fields import get_custom_fields


def after_install():
	create_custom_fields(get_custom_fields())


def after_migrate():
	create_custom_fields(get_custom_fields())


def before_uninstall():
	for doctype, fields in get_custom_fields().items():
		for field in fields:
			name = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": field["fieldname"]})
			if name:
				frappe.delete_doc("Custom Field", name, ignore_missing=True, force=True)
		frappe.clear_cache(doctype=doctype)
