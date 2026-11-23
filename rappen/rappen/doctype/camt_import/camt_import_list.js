frappe.listview_settings["CAMT Import"] = {
	get_indicator(doc) {
		const colors = { Draft: "gray", Imported: "green", "Imported with errors": "orange", Failed: "red" };
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
