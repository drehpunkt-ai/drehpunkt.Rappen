// Book an incoming payment against the invoice or dunning that its reference points to
frappe.ui.form.on("Bank Transaction", {
	refresh(frm) {
		const doc = frm.doc;
		if (doc.docstatus !== 1 || !doc.rappen_document || !(doc.deposit > 0) || !(doc.unallocated_amount > 0)) {
			return;
		}
		frm.add_custom_button(__("Book payment against {0}", [doc.rappen_document]), () =>
			frappe
				.call({
					method: "rappen.banking.book_against_document",
					args: { bank_transaction: doc.name },
					freeze: true,
				})
				.then((r) => {
					frappe.show_alert({ message: __("Payment Entry {0} created", [r.message]), indicator: "green" });
					frm.reload_doc();
				})
		);
	},
});
