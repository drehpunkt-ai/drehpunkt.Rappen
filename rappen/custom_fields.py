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
		"Bank Transaction": [
			{
				"fieldname": "rappen_document_type",
				"label": "Document type",
				"fieldtype": "Link",
				"options": "DocType",
				"insert_after": "reference_number",
				"read_only": 1,
				"hidden": 1,
			},
			{
				"fieldname": "rappen_document",
				"label": "Matching document",
				"fieldtype": "Dynamic Link",
				"options": "rappen_document_type",
				"insert_after": "rappen_document_type",
				"read_only": 1,
				"description": "Invoice or dunning with the payment reference of this transaction.",
			},
			{
				"fieldname": "rappen_entry_reference",
				"label": "Bank entry reference",
				"fieldtype": "Data",
				"insert_after": "transaction_id",
				"read_only": 1,
				"search_index": 1,
			},
			{
				"fieldname": "rappen_camt_import",
				"label": "CAMT Import",
				"fieldtype": "Link",
				"options": "CAMT Import",
				"insert_after": "rappen_entry_reference",
				"read_only": 1,
			},
		],
		"Purchase Invoice": [
			{
				"fieldname": "rappen_payment_section",
				"label": "Payment details",
				"fieldtype": "Section Break",
				"insert_after": "bill_date",
			},
			{
				"fieldname": "rappen_qr_code",
				"label": "QR-bill of the supplier",
				"fieldtype": "Small Text",
				"insert_after": "rappen_payment_section",
				"no_copy": 1,
				"description": "Scan the QR code of the supplier's QR-bill into this field with a hand scanner, or paste its content.",
			},
			{
				"fieldname": "rappen_payment_column",
				"fieldtype": "Column Break",
				"insert_after": "rappen_qr_code",
			},
			{
				"fieldname": "rappen_creditor_iban",
				"label": "IBAN of the supplier",
				"fieldtype": "Data",
				"insert_after": "rappen_payment_column",
				"no_copy": 1,
				"description": "From the QR-bill. Empty: the supplier's bank account.",
			},
			{
				"fieldname": "rappen_payment_reference",
				"label": "Payment reference",
				"fieldtype": "Data",
				"insert_after": "rappen_creditor_iban",
				"no_copy": 1,
				"search_index": 1,
			},
		],
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
