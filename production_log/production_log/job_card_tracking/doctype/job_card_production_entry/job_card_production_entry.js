frappe.ui.form.on("Job Card Production Entry", {
	refresh: function (frm) {
		frm.fields_dict["planning_lines"].grid.get_field("job_card").get_query = function () {
			return {
				filters: { docstatus: 1 }
			};
		};
		frm.fields_dict["actual_lines"].grid.get_field("job_card").get_query = function () {
			return {
				filters: { docstatus: 1 }
			};
		};
	}
});

frappe.ui.form.on("Production Planning Line", {
	job_card: function (frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		if (row.job_card) {
			frappe.db.get_value("Job Card Computer Paper", row.job_card,
				["quantity_ordered", "total_actual_good_qty", "balance_qty"],
				function (r) {
					if (r) {
						frappe.model.set_value(cdt, cdn, "order_qty", r.quantity_ordered || 0);
						frappe.model.set_value(cdt, cdn, "produced_qty", r.total_actual_good_qty || 0);
						frappe.model.set_value(cdt, cdn, "balance_qty", r.balance_qty || 0);
					}
				}
			);
		}
	}
});

frappe.ui.form.on("Production Actual Line", {
	job_card: function (frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		if (row.job_card) {
			frappe.db.get_value("Job Card Computer Paper", row.job_card,
				["quantity_ordered", "total_actual_good_qty", "balance_qty"],
				function (r) {
					if (r) {
						frappe.model.set_value(cdt, cdn, "order_qty", r.quantity_ordered || 0);
						frappe.model.set_value(cdt, cdn, "produced_qty", r.total_actual_good_qty || 0);
						frappe.model.set_value(cdt, cdn, "balance_qty", r.balance_qty || 0);
						// Recalculate running balance
						var good = row.good_qty || 0;
						frappe.model.set_value(cdt, cdn, "running_balance", (r.balance_qty || 0) - good);
					}
				}
			);
		}
	},

	good_qty: function (frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "running_balance", (row.balance_qty || 0) - (row.good_qty || 0));
		recalculate_totals(frm);
	},

	waste_qty: function (frm) {
		recalculate_totals(frm);
	}
});

function recalculate_totals(frm) {
	var total_good = 0;
	var total_waste = 0;
	(frm.doc.actual_lines || []).forEach(function (row) {
		total_good += row.good_qty || 0;
		total_waste += row.waste_qty || 0;
	});
	frm.set_value("total_good_qty", total_good);
	frm.set_value("total_waste_qty", total_waste);
}
