frappe.ui.form.on("Production Station", {
	refresh(frm) {
		if (!frm.doc.__islocal) {
			frm.add_custom_button(__("View Production Logs"), function () {
				frappe.set_route("List", "Daily Production Log", {
					production_station: frm.doc.name,
				});
			});
		}
	},

	max_reels(frm) {
		const val = frm.doc.max_reels;
		if (val < 1 || val > 4) {
			frappe.msgprint(__("Maximum Reels must be between 1 and 4."));
			frm.set_value("max_reels", Math.min(4, Math.max(1, val)));
		}
	},
});
