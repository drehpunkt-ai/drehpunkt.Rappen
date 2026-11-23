// Only bank accounts of the document's company can carry its QR-bill
frappe.ui.form.on("Sales Invoice", {
	setup(frm) {
		frm.set_query("rappen_bank_account", () => ({
			filters: { is_company_account: 1, company: frm.doc.company, disabled: 0 },
		}));
	},
});
