frappe.ui.form.on("Department Daily Plan", {
	refresh(frm) {
		if (frm.doc.status === "Draft") {
			frm.add_custom_button(__("Open"), function () {
				frm.set_value("status", "Open");
				frm.save();
			}, __("Status"));
		}
		if (frm.doc.status === "Open") {
			frm.add_custom_button(__("Close"), function () {
				frm.set_value("status", "Closed");
				frm.save();
			}, __("Status"));
		}
		if (frm.doc.status === "Draft" || frm.doc.status === "Open") {
			frm.add_custom_button(__("Cancel Plan"), function () {
				frappe.confirm(__("Are you sure you want to cancel this plan?"), function () {
					frm.set_value("status", "Cancelled");
					frm.save();
				});
			}, __("Status"));
		}

		_apply_closed_lock(frm);

		frm.fields_dict["plan_lines"].grid.get_field("computer_paper_job_card").get_query = function () {
			return { filters: { docstatus: 1 } };
		};
		frm.fields_dict["plan_lines"].grid.get_field("label_job_card").get_query = function () {
			return { filters: { docstatus: 1 } };
		};
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.planner) {
			frm.set_value("planner", frappe.session.user);
		}
	},
});

frappe.ui.form.on("Department Daily Plan Line", {
	computer_paper_job_card(frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		if (row.computer_paper_job_card) {
			_fetch_jc(frm, cdt, cdn, "Computer Paper", row.computer_paper_job_card);
		}
	},

	label_job_card(frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		if (row.label_job_card) {
			_fetch_jc(frm, cdt, cdn, "Label", row.label_job_card);
		}
	},

	entry_type(frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		if (row.entry_type === "Manual") {
			frappe.model.set_value(cdt, cdn, "job_card_type", "");
			frappe.model.set_value(cdt, cdn, "computer_paper_job_card", "");
			frappe.model.set_value(cdt, cdn, "label_job_card", "");
			frappe.model.set_value(cdt, cdn, "customer_name", "");
			frappe.model.set_value(cdt, cdn, "job_name", "");
			frappe.model.set_value(cdt, cdn, "ordered_qty", 0);
			frappe.model.set_value(cdt, cdn, "completed_qty_snapshot", 0);
			frappe.model.set_value(cdt, cdn, "pending_qty_snapshot", 0);
		} else if (row.entry_type === "Job Card") {
			frappe.model.set_value(cdt, cdn, "manual_job_type", "");
			frappe.model.set_value(cdt, cdn, "manual_customer_name", "");
			frappe.model.set_value(cdt, cdn, "manual_job_name", "");
			frappe.model.set_value(cdt, cdn, "manual_ordered_qty", 0);
			frappe.model.set_value(cdt, cdn, "manual_completed_qty", 0);
			frappe.model.set_value(cdt, cdn, "manual_pending_qty", 0);
		}
	},

	job_card_type(frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		if (row.job_card_type === "Computer Paper") {
			frappe.model.set_value(cdt, cdn, "label_job_card", "");
		} else if (row.job_card_type === "Label") {
			frappe.model.set_value(cdt, cdn, "computer_paper_job_card", "");
		}
		frappe.model.set_value(cdt, cdn, "customer_name", "");
		frappe.model.set_value(cdt, cdn, "job_name", "");
		frappe.model.set_value(cdt, cdn, "ordered_qty", 0);
		frappe.model.set_value(cdt, cdn, "completed_qty_snapshot", 0);
		frappe.model.set_value(cdt, cdn, "pending_qty_snapshot", 0);
	},

	manual_ordered_qty(frm, cdt, cdn) { _recalc_manual(cdt, cdn); },
	manual_completed_qty(frm, cdt, cdn) { _recalc_manual(cdt, cdn); },
});

function _fetch_jc(frm, cdt, cdn, jc_type, jc_name) {
	frappe.call({
		method: "production_log.job_card_tracking.doctype.department_daily_plan.department_daily_plan.fetch_job_card_details",
		args: { job_card_type: jc_type, job_card_name: jc_name },
		callback(r) {
			if (r.message) {
				var d = r.message;
				frappe.model.set_value(cdt, cdn, "customer_name", d.customer_name || "");
				frappe.model.set_value(cdt, cdn, "job_name", d.job_name || "");
				frappe.model.set_value(cdt, cdn, "ordered_qty", d.ordered_qty || 0);
				frappe.model.set_value(cdt, cdn, "completed_qty_snapshot", d.completed_qty_snapshot || 0);
				frappe.model.set_value(cdt, cdn, "pending_qty_snapshot", d.pending_qty_snapshot || 0);
			}
		},
	});
}

function _recalc_manual(cdt, cdn) {
	var row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "manual_pending_qty",
		(row.manual_ordered_qty || 0) - (row.manual_completed_qty || 0));
}

function _apply_closed_lock(frm) {
	if (frm.doc.status === "Closed" || frm.doc.status === "Cancelled") {
		if (!frappe.user_roles.includes("System Manager") && !frappe.user_roles.includes("Production Manager")) {
			frm.disable_save();
			frm.set_read_only();
		}
	}
}
