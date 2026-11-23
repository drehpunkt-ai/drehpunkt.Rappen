frappe.ui.form.on("Rappen Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Complete Swiss chart of accounts"), () => {
			frappe.prompt(
				{ fieldname: "company", fieldtype: "Link", options: "Company", label: __("Company"), reqd: 1,
					default: frappe.defaults.get_user_default("Company") },
				(values) =>
					frappe
						.call({ method: "rappen.accounts.complete_chart", args: { company: values.company }, freeze: true })
						.then((r) => {
							const changed = r.message.changed.concat(r.message.skipped);
							frappe.msgprint({
								title: __("Complete Swiss chart of accounts"),
								message: changed.length
									? changed.map((line) => frappe.utils.escape_html(line)).join("<br>")
									: __("Nothing to complete, the chart of accounts is set up already."),
							});
						}),
				__("Complete Swiss chart of accounts"),
				__("Complete", null, "Rappen")
			);
		});
		frm.add_custom_button(__("Create Swiss dunning levels"), () => {
			const dialog = new frappe.ui.Dialog({
				title: __("Create Swiss dunning levels"),
				fields: [
					{ fieldname: "company", fieldtype: "Link", options: "Company", label: __("Company"), reqd: 1,
						default: frappe.defaults.get_user_default("Company") },
					{ fieldname: "fee_reminder", fieldtype: "Currency", label: __("Fee for the payment reminder"), default: 0 },
					{ fieldname: "fee_first", fieldtype: "Currency", label: __("Fee for the first dunning"), default: 20 },
					{ fieldname: "fee_final", fieldtype: "Currency", label: __("Fee for the final dunning"), default: 30 },
					{ fieldname: "interest", fieldtype: "Float", label: __("Default interest in percent per year"), default: 0 },
					{ fieldtype: "HTML", options: `<p class="text-muted small">${__(
						"Fees and default interest may only be charged if your customers agreed to them, e.g. in your general terms and conditions."
					)}</p>` },
				],
				primary_action_label: __("Create"),
				primary_action(values) {
					frappe
						.call({
							method: "rappen.dunning.create_dunning_types",
							args: {
								company: values.company,
								fees: [values.fee_reminder, values.fee_first, values.fee_final],
								interest: values.interest,
							},
							freeze: true,
						})
						.then(() => dialog.hide());
				},
			});
			dialog.show();
		});
	},
});
