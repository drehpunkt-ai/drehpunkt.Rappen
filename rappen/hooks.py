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

# Forms
# -----

doctype_js = {
	"Address": "public/js/address.js",
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
}
