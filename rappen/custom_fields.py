"""Fields that Rappen adds to doctypes of Frappe and ERPNext.

Created on install and on every migrate, removed on uninstall (``rappen.install``). All field names start with
``rappen_`` so they never collide with fields of ERPNext or other apps.
"""


def _qr_fields(insert_after: str) -> list[dict]:
	"""Bank account and payment reference of a document that carries a QR-bill."""
	return [
		{
			"fieldname": "rappen_qr_section",
			"label": "QR-bill",
			"fieldtype": "Section Break",
			"insert_after": insert_after,
			"collapsible": 1,
		},
		{
			"fieldname": "rappen_bank_account",
			"label": "Bank account for the QR-bill",
			"fieldtype": "Link",
			"options": "Bank Account",
			"insert_after": "rappen_qr_section",
			"print_hide": 1,
			"description": "Empty: the company's default bank account.",
		},
		{
			"fieldname": "rappen_qr_column",
			"fieldtype": "Column Break",
			"insert_after": "rappen_bank_account",
		},
		{
			"fieldname": "rappen_reference_type",
			"label": "Reference type",
			"fieldtype": "Select",
			"options": "\nQRR\nSCOR\nNON",
			"insert_after": "rappen_qr_column",
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
		},
		{
			"fieldname": "rappen_payment_reference",
			"label": "Payment reference",
			"fieldtype": "Data",
			"insert_after": "rappen_reference_type",
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
			"search_index": 1,
			"in_standard_filter": 1,
		},
	]


def get_custom_fields() -> dict[str, list[dict]]:
	return {
		"Sales Invoice": _qr_fields(insert_after="account_for_change_amount"),
		"Dunning": _qr_fields(insert_after="grand_total"),
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
