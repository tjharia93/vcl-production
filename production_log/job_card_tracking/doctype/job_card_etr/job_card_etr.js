// Copyright (c) 2026, VCL and contributors
// For license information, please see license.txt

const ETR_CMYK_FIELDS = ["uses_c", "uses_m", "uses_y", "uses_k"];

const ETR_SNAPSHOT_FIELDS = [
	["specification_name",       "specification_name"],
	["etr_substrate",            "substrate"],
	["etr_substrate_other",      "substrate_other"],
	["etr_gsm",                  "gsm"],
	["etr_core_id",              "core_id"],
	["etr_jumbo_width",          "jumbo_width"],
	["etr_output_type",          "output_type"],
	["etr_finished_width",       "finished_width"],
	["etr_finished_diameter",    "finished_diameter"],
	["etr_finished_reel_length", "finished_reel_length"],
	["etr_print_type",           "print_type"],
	["ink_type",                 "ink_type"],
	["uses_c",                   "uses_c"],
	["uses_m",                   "uses_m"],
	["uses_y",                   "uses_y"],
	["uses_k",                   "uses_k"],
	["number_of_colours",        "number_of_colours"],
	["colour_notes",             "colour_notes"],
];

const ETR_SPOT_COLOUR_FIELDS = [
	"pantone_code", "pantone_name", "hex_preview",
	"cmyk_c", "cmyk_m", "cmyk_y", "cmyk_k", "notes",
];

function recalculate_etr_number_of_colours(frm) {
	if (!frm.doc.printing_required) {
		frm.set_value("number_of_colours", 0);
		return;
	}
	const ticks = ETR_CMYK_FIELDS.reduce((n, f) => n + (frm.doc[f] ? 1 : 0), 0);
	const spots = (frm.doc.spot_colours || []).length;
	frm.set_value("number_of_colours", ticks + spots);
}

function recalculate_etr_print_totals(frm) {
	if (!frm.doc.printing_required) {
		frm.set_value("print_total_metres_out", 0);
		frm.set_value("print_total_reels_out", 0);
		return;
	}
	const rows = frm.doc.print_reel_output || [];
	const total_metres = rows.reduce((n, r) => n + (r.metres_printed || 0), 0);
	frm.set_value("print_total_metres_out", total_metres);
	frm.set_value("print_total_reels_out", rows.length);
}

function clear_etr_spec_fields(frm) {
	ETR_SNAPSHOT_FIELDS.forEach(([, jc_field]) => {
		const fld = frm.fields_dict[jc_field];
		if (!fld) return;
		const ft = fld.df.fieldtype;
		const blank = (ft === "Check" || ft === "Int" || ft === "Float") ? 0 : "";
		frm.set_value(jc_field, blank);
	});
	frm.clear_table("spot_colours");
	frm.refresh_field("spot_colours");
}

frappe.ui.form.on("Job Card ETR", {
	onload(frm) {
		if (!frm.doc.job_date) {
			frm.set_value("job_date", frappe.datetime.get_today());
		}
	},

	refresh(frm) {
		frm.set_query("customer_product_spec", function () {
			return {
				query: "production_log.job_card_tracking.doctype.job_card_etr.job_card_etr.get_etr_customer_product_spec_query",
				filters: { customer: frm.doc.customer },
			};
		});
		recalculate_etr_number_of_colours(frm);
		recalculate_etr_print_totals(frm);
	},

	customer(frm) {
		frm.set_value("customer_product_spec", "");
		clear_etr_spec_fields(frm);
	},

	customer_product_spec(frm) {
		if (!frm.doc.customer_product_spec) {
			clear_etr_spec_fields(frm);
			return;
		}
		frappe.call({
			method: "frappe.client.get",
			args: {
				doctype: "Customer Product Specification",
				name: frm.doc.customer_product_spec,
			},
			callback(r) {
				if (r.exc || !r.message) return;
				const spec = r.message;

				ETR_SNAPSHOT_FIELDS.forEach(([spec_field, jc_field]) => {
					const value = spec[spec_field];
					if (value !== undefined && value !== null && value !== "") {
						frm.set_value(jc_field, value);
					}
				});

				frm.clear_table("spot_colours");
				(spec.spot_colours || []).forEach((src) => {
					const row = frm.add_child("spot_colours");
					ETR_SPOT_COLOUR_FIELDS.forEach((f) => { row[f] = src[f]; });
				});

				// Auto-set operation flags from output type so users get sensible defaults.
				if (spec.etr_output_type === "ETR Plain Rolls") {
					frm.set_value("printing_required", 0);
					frm.set_value("slitting_required", 1);
				} else if (spec.etr_output_type === "ETR Printed Rolls") {
					frm.set_value("printing_required", 1);
					frm.set_value("slitting_required", 1);
				} else if (spec.etr_output_type === "Printed Reel") {
					frm.set_value("printing_required", 1);
					frm.set_value("slitting_required", 0);
				}

				frm.refresh_fields();
				recalculate_etr_number_of_colours(frm);
			},
		});
	},

	printing_required(frm) {
		recalculate_etr_number_of_colours(frm);
		recalculate_etr_print_totals(frm);
	},

	uses_c(frm) { recalculate_etr_number_of_colours(frm); },
	uses_m(frm) { recalculate_etr_number_of_colours(frm); },
	uses_y(frm) { recalculate_etr_number_of_colours(frm); },
	uses_k(frm) { recalculate_etr_number_of_colours(frm); },
});

frappe.ui.form.on("Spot Colour", {
	spot_colours_add(frm)    { recalculate_etr_number_of_colours(frm); },
	spot_colours_remove(frm) { recalculate_etr_number_of_colours(frm); },
});

frappe.ui.form.on("ETR Print Reel Output", {
	metres_printed(frm)            { recalculate_etr_print_totals(frm); },
	print_reel_output_add(frm)     { recalculate_etr_print_totals(frm); },
	print_reel_output_remove(frm)  { recalculate_etr_print_totals(frm); },
});
