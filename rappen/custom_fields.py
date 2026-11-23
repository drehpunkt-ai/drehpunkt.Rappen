"""Fields that Rappen adds to doctypes of Frappe and ERPNext.

Created on install and on every migrate, removed on uninstall (``rappen.install``). All field names start with
``rappen_`` so they never collide with fields of ERPNext or other apps.
"""


def get_custom_fields() -> dict[str, list[dict]]:
	return {
		"Bank Account": [
			{
				"fieldname": "rappen_qr_iban",
				"label": "QR-IBAN",
				"fieldtype": "Data",
				"options": "IBAN",
				"insert_after": "iban",
				"depends_on": "eval:doc.is_company_account",
				"description": "Only for QR-bills with a QR reference. Your bank assigns it in addition to the IBAN.",
			},
			{
				"fieldname": "rappen_qr_reference_prefix",
				"label": "QR reference prefix (BESR-ID)",
				"fieldtype": "Data",
				"length": 10,
				"insert_after": "rappen_qr_iban",
				"depends_on": "eval:doc.is_company_account && doc.rappen_qr_iban",
				"description": "Some banks require every QR reference to start with a number they assign. Leave empty if yours does not.",
			},
		],
		"Address": [
			{
				"fieldname": "rappen_payment_address",
				"label": "Address on payments",
				"fieldtype": "HTML",
				"insert_after": "pincode",
			},
		],
	}
