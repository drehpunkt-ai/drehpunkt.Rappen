frappe.ui.form.on("Payment Proposal", {
	setup(frm) {
		frm.set_query("bank_account", () => ({
			filters: { is_company_account: 1, company: frm.doc.company, disabled: 0 },
		}));
		frm.set_query("purchase_invoice", "items", () => ({
			filters: { company: frm.doc.company, docstatus: 1, outstanding_amount: [">", 0] },
		}));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Get open purchase invoices"), () =>
				frm.call({ doc: frm.doc, method: "get_open_invoices", freeze: true }).then(() => frm.dirty() || frm.refresh())
			);
		}
		if (frm.doc.docstatus === 1 && frm.doc.payment_file) {
			frm.add_custom_button(__("Download payment file"), () => window.open(frm.doc.payment_file));
		}
	},
});
