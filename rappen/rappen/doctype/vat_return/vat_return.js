frappe.ui.form.on("VAT Return", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Calculate from the books"), () =>
				frm.call({ doc: frm.doc, method: "calculate", freeze: true }).then(() => frm.dirty() || frm.refresh())
			);
		}
		if (frm.doc.docstatus === 1 && frm.doc.vat_file) {
			frm.add_custom_button(__("Download eCH-0217 file"), () => window.open(frm.doc.vat_file));
		}
	},
});
