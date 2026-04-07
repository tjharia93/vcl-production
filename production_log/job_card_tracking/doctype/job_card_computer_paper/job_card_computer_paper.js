frappe.ui.form.on("Job Card Computer Paper", {
	refresh(frm) {
		frm.set_query("customer_product_spec", function () {
			return {
				query: "production_log.job_card_tracking.doctype.job_card_computer_paper.job_card_computer_paper.get_customer_product_spec_query",
				filters: { customer: frm.doc.customer },
			};
		});
	},

	order_date(frm) {
		if (!frm.doc.order_date) {
			frm.set_value("order_date", frappe.datetime.get_today());
		}
	},

	onload(frm) {
		if (!frm.doc.order_date) {
			frm.set_value("order_date", frappe.datetime.get_today());
		}
	},

	customer(frm) {
		// Clear spec and all auto-filled fields
		frm.set_value("customer_product_spec", "");
		clear_spec_fields(frm);
		frm.refresh_field("customer_product_spec");

		// Warn if customer has no active Computer Paper specs
		if (frm.doc.customer) {
			frappe.call({
				method: "production_log.job_card_tracking.doctype.job_card_computer_paper.job_card_computer_paper.get_customer_product_spec_query",
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
								"No active Computer Paper specifications found for this customer. "
								+ "Please create a <strong>Customer Product Specification</strong> "
								+ "with Product Type = 'Computer Paper' and Status = 'Active' first."
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
			clear_spec_fields(frm);
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
				frm.set_value("pay_slip_size", spec.pay_slip_size || "");
				frm.set_value("number_of_colours", spec.number_of_colours || 0);
				frm.set_value("number_of_parts", spec.number_of_parts || 0);
				frm.set_value("numbering_required", spec.numbering_required || 0);
				frm.set_value("packing", spec.standard_packing || "");
				frm.set_value("weight_per_carton", spec.standard_weight_per_carton || 0);

				// Rebuild colour_of_parts table
				frm.clear_table("colour_of_parts");
				if (spec.colour_of_parts && spec.colour_of_parts.length) {
					spec.colour_of_parts.forEach(function (part) {
						const row = frm.add_child("colour_of_parts");
						row.part_number = part.part_number;
						row.paper_type = part.paper_type;
						row.gsm = part.gsm;
						row.colour = part.colour;
						row.purpose = part.purpose;
					});
				}

				frm.refresh_fields([
					"specification_name",
					"job_size",
					"pay_slip_size",
					"number_of_colours",
					"number_of_parts",
					"numbering_required",
					"packing",
					"weight_per_carton",
					"colour_of_parts",
				]);
			},
		});
	},
});

function clear_spec_fields(frm) {
	frm.set_value("specification_name", "");
	frm.set_value("job_size", "");
	frm.set_value("pay_slip_size", "");
	frm.set_value("number_of_colours", 0);
	frm.set_value("number_of_parts", 0);
	frm.set_value("numbering_required", 0);
	frm.set_value("packing", "");
	frm.set_value("weight_per_carton", 0);
	frm.clear_table("colour_of_parts");
	frm.refresh_field("colour_of_parts");
}
