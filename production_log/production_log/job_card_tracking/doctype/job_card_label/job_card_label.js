frappe.ui.form.on("Job Card Label", {
	refresh(frm) {
		frm.set_query("customer_product_spec", function () {
			return {
				query: "production_log.job_card_tracking.doctype.job_card_label.job_card_label.get_label_customer_product_spec_query",
				filters: { customer: frm.doc.customer },
			};
		});
	},

	onload(frm) {
		if (!frm.doc.order_date) {
			frm.set_value("order_date", frappe.datetime.get_today());
		}
	},

	customer(frm) {
		frm.set_value("customer_product_spec", "");
		clear_label_spec_fields(frm);
		frm.refresh_field("customer_product_spec");

		if (frm.doc.customer) {
			frappe.call({
				method: "production_log.job_card_tracking.doctype.job_card_label.job_card_label.get_label_customer_product_spec_query",
				args: {
					doctype: "Customer Product Specification",
					txt: "",
					searchfield: "name",
					start: 0,
					page_len: 1,
					filters: { customer: frm.doc.customer },
				},
				callback(r) {
					if (r.message && r.message.length === 0) {
						frappe.msgprint({
							title: __("No Specifications Found"),
							message: __(
								"No active Label specifications found for this customer. "
								+ "Please create a <strong>Customer Product Specification</strong> "
								+ "with Product Type = 'Label' and Status = 'Active' first."
							),
							indicator: "orange",
						});
					}
				},
			});
		}
	},

	customer_product_spec(frm) {
		if (!frm.doc.customer_product_spec) {
			clear_label_spec_fields(frm);
			return;
		}

		frappe.call({
			method: "frappe.client.get",
			args: {
				doctype: "Customer Product Specification",
				name: frm.doc.customer_product_spec,
			},
			callback(r) {
				if (r.exc || !r.message) {
					frappe.msgprint({
						title: __("Error"),
						message: __("Could not load the selected specification. Please try again."),
						indicator: "red",
					});
					return;
				}

				const spec = r.message;

				frm.set_value("specification_name", spec.specification_name || "");
				frm.set_value("job_size", spec.job_size || "");
				frm.set_value("dies", spec.dies || "");
				frm.set_value("label_length", spec.label_length || 0);
				frm.set_value("label_width", spec.label_width || 0);
				frm.set_value("label_number_of_colours", spec.label_number_of_colours || 0);
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

				frm.refresh_fields();
			},
		});
	},
});

function clear_label_spec_fields(frm) {
	const fields = [
		"specification_name", "job_size", "dies", "label_length", "label_width",
		"label_number_of_colours", "cylinder_teeth", "plate_up", "plate_round",
		"packing_up", "material_type", "packing_pieces", "gap_between", "side_trim",
		"numbering_required", "standard_packing", "weight_per_carton",
	];

	fields.forEach(function (field) {
		frm.set_value(field, null);
	});
}
