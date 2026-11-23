app_name = "rappen"
app_title = "Rappen"
app_publisher = "Drehpunkt"
app_description = "Swiss localization, built for ERPNext: QR-bill, camt, pain.001, VAT return and dunning"
app_email = "marco@drehpunkt.ai"
app_license = "MIT"

required_apps = ["erpnext"]

# Installation
# ------------
# Custom fields are created on install and kept up to date on every migrate

after_install = "rappen.install.after_install"
after_migrate = "rappen.install.after_migrate"
before_uninstall = "rappen.install.before_uninstall"

# Swiss companies get the account types and defaults that ERPNext's Swiss chart lacks
setup_wizard_complete = "rappen.accounts.after_setup_wizard"

# Forms
# -----

doctype_js = {
	"Address": "public/js/address.js",
	"Bank Transaction": "public/js/bank_transaction.js",
	"Dunning": "public/js/dunning.js",
	"Sales Invoice": "public/js/sales_invoice.js",
}

# Print formats
# -------------
# Functions available in Jinja: rappen_payment_part(doc), rappen_sender_line(doc)

jinja = {
	"methods": ["rappen.jinja"],
}

# Document events
# ---------------

doc_events = {
	"Address": {
		"onload": "rappen.events.address.onload",
		"validate": "rappen.events.address.validate",
	},
	"Bank Account": {
		"validate": "rappen.events.bank_account.validate",
	},
	"Dunning": {
		"validate": "rappen.qr.set_payment_reference",
	},
	"Purchase Invoice": {
		"validate": "rappen.payments.read_supplier_qr_bill",
	},
	"Sales Invoice": {
		"validate": "rappen.qr.set_payment_reference",
	},
}
