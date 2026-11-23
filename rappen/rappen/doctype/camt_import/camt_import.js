frappe.ui.form.on("CAMT Import", {
	setup(frm) {
		frm.set_query("bank_account", () => ({
			filters: { is_company_account: 1, company: frm.doc.company, disabled: 0 },
		}));
	},
	refresh(frm) {
		if (!frm.is_new() && frm.doc.status === "Draft" && frm.doc.file) {
			frm.add_custom_button(__("Import"), () =>
				frm.call({ doc: frm.doc, method: "run_import", freeze: true }).then(() => frm.reload_doc())
			).addClass("btn-primary");
		}
	},
});
