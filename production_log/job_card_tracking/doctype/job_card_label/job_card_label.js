const PRINT_COLOUR_FIELDS = ["ink_type", "uses_c", "uses_m", "uses_y", "uses_k", "number_of_colours", "colour_notes"];
const SPOT_COLOUR_FIELDS  = ["pantone_code", "pantone_name", "hex_preview", "cmyk_c", "cmyk_m", "cmyk_y", "cmyk_k", "notes"];

frappe.ui.form.on("Job Card Label", {
	refresh(frm) {
		frm.set_query("customer_product_spec", function () {
			return {
				query: "production_log.job_card_tracking.doctype.job_card_label.job_card_label.get_label_customer_product_spec_query",
				filters: { customer: frm.doc.customer },
			};
		});
		_label_add_job_status_buttons(frm);
	},

	onload(frm) {
		if (!frm.doc.order_date) {
			frm.set_value("order_date", frappe.datetime.get_today());
		}
	},

	customer(frm) {
		frm.set_value("customer_product_spec", "");
		_clear_label_spec_fields(frm);
		frm.refresh_field("customer_product_spec");

		if (frm.doc.customer) {
			frappe.call({
				method: "production_log.job_card_tracking.doctype.job_card_label.job_card_label.get_label_customer_product_spec_query",
				args: {
					doctype: "Customer Product Specification",
					txt: "", searchfield: "name", start: 0, page_len: 1,
					filters: { customer: frm.doc.customer },
				},
				callback(r) {
					if (r.message && r.message.length === 0) {
						frappe.msgprint({
							title: __("No Specifications Found"),
							message: __("No active Label specifications found for this customer. Please create a Customer Product Specification with Product Type = 'Label' and Status = 'Active' first."),
							indicator: "orange",
						});
					}
				},
			});
		}
	},

	customer_product_spec(frm) {
		if (!frm.doc.customer_product_spec) {
			_clear_label_spec_fields(frm);
			return;
		}
		frappe.call({
			method: "frappe.client.get",
			args: { doctype: "Customer Product Specification", name: frm.doc.customer_product_spec },
			callback(r) {
				if (r.exc || !r.message) return;
				const spec = r.message;
				frm.set_value("specification_name", spec.specification_name || "");
				frm.set_value("job_size", spec.job_size || "");
				frm.set_value("dies", spec.dies || "");
				frm.set_value("label_length", spec.label_length || 0);
				frm.set_value("label_width", spec.label_width || 0);
				frm.set_value("cylinder_teeth", spec.cylinder_teeth || 0);
				frm.set_value("plate_up", spec.plate_up || 0);
				frm.set_value("plate_round", spec.plate_round || 0);
				frm.set_value("packing_up", spec.packing_up || 0);
				frm.set_value("material_type", spec.material_type || "");
				frm.set_value("packing_pieces", spec.packing_pieces || 0);
				frm.set_value("gap_between", spec.gap_between || 0);
				frm.set_value("side_trim", spec.side_trim || 0);
				frm.set_value("numbering_required", spec.numbering_required || 0);
				frm.set_value("standard_packing", spec.standard_packing || "");
				frm.set_value("weight_per_carton", spec.standard_weight_per_carton || 0);

				PRINT_COLOUR_FIELDS.forEach((f) =>
					frm.set_value(f, spec[f] || (f === "ink_type" || f === "colour_notes" ? "" : 0))
				);

				frm.clear_table("spot_colours");
				(spec.spot_colours || []).forEach((sc) => {
					const row = frm.add_child("spot_colours");
					SPOT_COLOUR_FIELDS.forEach((f) => { row[f] = sc[f]; });
				});

				frm.refresh_fields();
			},
		});
	},
});

function _label_add_job_status_buttons(frm) {
	if (frm.doc.docstatus !== 1) return;
	const status = frm.doc.job_status || "Open";
	const closed = status === "Closed" || status === "Completed";

	if (closed) {
		frm.add_custom_button(__("Reopen Job"), () => _label_set_job_status(frm, "Open"));
	} else {
		frm.add_custom_button(__("Close Job"), () => _label_set_job_status(frm, "Closed"));
		if (status === "Open") {
			frm.add_custom_button(__("Mark In Progress"), () => _label_set_job_status(frm, "In Progress"));
		}
		if (status !== "Completed") {
			frm.add_custom_button(__("Mark Completed"), () => _label_set_job_status(frm, "Completed"));
		}
	}
}

function _label_set_job_status(frm, status) {
	const messages = {
		"Closed":      __("Close this job card? It will no longer appear on the Production Planner."),
		"Completed":   __("Mark this job as Completed? It will no longer appear on the Production Planner."),
		"In Progress": __("Mark this job as In Progress?"),
		"Open":        __("Reopen this job card? It will appear on the Production Planner again."),
	};
	frappe.confirm(messages[status], () => {
		frappe.call({
			method: "production_log.job_card_tracking.utils.set_job_status",
			args: { doctype: frm.doctype, name: frm.doc.name, status: status },
			freeze: true,
			callback: () => frm.reload_doc(),
		});
	});
}

function _clear_label_spec_fields(frm) {
	["specification_name", "job_size", "dies", "material_type", "standard_packing",
	 "ink_type", "colour_notes"].forEach(f => frm.set_value(f, null));
	["label_length", "label_width", "cylinder_teeth", "plate_up",
	 "plate_round", "packing_up", "packing_pieces", "gap_between", "side_trim",
	 "numbering_required", "weight_per_carton",
	 "number_of_colours", "uses_c", "uses_m", "uses_y", "uses_k"].forEach(f => frm.set_value(f, null));
	frm.clear_table("spot_colours");
	frm.refresh_field("spot_colours");
}
