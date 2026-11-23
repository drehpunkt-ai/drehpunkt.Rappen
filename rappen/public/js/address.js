// Shows how the address appears on QR-bills and in payment files (filled by rappen.events.address.onload)
frappe.ui.form.on("Address", {
	refresh(frm) {
		const field = frm.get_field("rappen_payment_address");
		const data = frm.doc.__onload && frm.doc.__onload.rappen_payment_address;
		if (!field || !data || frm.is_new()) {
			field && field.$wrapper.empty();
			return;
		}
		const esc = frappe.utils.escape_html;
		const rows = [
			[__("Street", null, "Rappen"), data.street],
			[__("Building number", null, "Rappen"), data.building_number],
			[__("Postal code", null, "Rappen"), data.postal_code],
			[__("Town", null, "Rappen"), data.town],
			[__("Country", null, "Rappen"), data.country],
		]
			.map(([label, value]) => `<tr><td class="text-muted">${esc(label)}</td><td>${esc(value || "")}</td></tr>`)
			.join("");
		const problems = (data.problems || [])
			.map((problem) => `<div class="text-warning">${esc(problem)}</div>`)
			.join("");
		field.$wrapper.html(`
			<div class="form-group">
				<div class="clearfix"><label class="control-label">${esc(__("Address on payments"))}</label></div>
				<table class="table table-sm table-borderless mb-1">${rows}</table>
				${problems}
				<p class="help-box small text-muted">${esc(
					__("This is how the address appears on QR-bills and in payment files.")
				)}</p>
			</div>
		`);
	},
});
