// Job Card Carton - Client Script
// Implements spec auto-populate + serial calculation pipeline with anti-race protection

let _pipeline_running = false;
let _pipeline_queued = false;

// Original field properties stored for SFK restore
let _sfk_original_props = {};

frappe.ui.form.on("Job Card Carton", {
	refresh(frm) {
		frm.set_query("customer_product_spec", function () {
			return {
				query: "production_log.job_card_tracking.doctype.job_card_carton.job_card_carton.get_carton_customer_product_spec_query",
				filters: { customer: frm.doc.customer_name },
			};
		});

		// Reset manual override flags if values are 0/empty
		if (!frm.doc.ctn_flap_mm) {
			frm.__flap_manual_override = false;
		}
		if (!frm.doc.board_width_actual_mm) {
			frm.__actual_width_override = false;
		}
		if (!frm.doc.board_length_actual_mm) {
			frm.__actual_length_override = false;
		}

		vcl_run_calc_pipeline(frm);
	},

	onload(frm) {
		if (!frm.doc.date_created) {
			frm.set_value("date_created", frappe.datetime.get_today());
		}
	},

	// --- Customer & Spec auto-populate ---

	customer_name(frm) {
		frm.set_value("customer_product_spec", "");
		_clear_spec_fields(frm);
		frm.refresh_field("customer_product_spec");

		if (frm.doc.customer_name) {
			frappe.call({
				method: "production_log.job_card_tracking.doctype.job_card_carton.job_card_carton.get_carton_customer_product_spec_query",
				args: {
					doctype: "Customer Product Specification",
					txt: "", searchfield: "name", start: 0, page_len: 1,
					filters: { customer: frm.doc.customer_name },
				},
				callback(r) {
					if (r.message && r.message.length === 0) {
						frappe.msgprint({
							title: __("No Specifications Found"),
							message: __("No active Carton specifications found for this customer. Please create a Customer Product Specification with Product Type = 'Carton' and Status = 'Active' first."),
							indicator: "orange",
						});
					}
				},
			});
		}
	},

	customer_product_spec(frm) {
		if (!frm.doc.customer_product_spec) {
			_clear_spec_fields(frm);
			return;
		}
		frappe.call({
			method: "frappe.client.get",
			args: { doctype: "Customer Product Specification", name: frm.doc.customer_product_spec },
			callback(r) {
				if (r.exc || !r.message) return;
				const spec = r.message;

				// Common fields
				frm.set_value("specification_name", spec.specification_name || "");

				// Product description
				frm.set_value("ply", spec.ply || "");
				frm.set_value("flute_type", spec.flute_type || "");
				frm.set_value("printing_or_plain", spec.printing_or_plain || "");
				frm.set_value("no_of_colours", spec.no_of_colours_carton || "0");
				frm.set_value("colours_details", spec.colours_details || "");
				frm.set_value("special_instructions", spec.special_instructions_carton || "");

				// Dimensions
				frm.set_value("ctn_length_mm", spec.ctn_length_mm || 0);
				frm.set_value("ctn_width_mm", spec.ctn_width_mm || 0);
				frm.set_value("ctn_height_mm", spec.ctn_height_mm || 0);

				// GSM layers
				frm.set_value("1_ply_top_layer_gsm", spec["1_ply_top_layer_gsm"] || 0);
				frm.set_value("2_ply_fluting_gsm", spec["2_ply_fluting_gsm"] || 0);
				frm.set_value("3_ply_bottom_gsm", spec["3_ply_bottom_gsm"] || 0);
				frm.set_value("4_ply_fluting_gsm", spec["4_ply_fluting_gsm"] || 0);
				frm.set_value("5_ply_fluting_gsm", spec["5_ply_fluting_gsm"] || 0);

				// Materials
				frm.set_value("1_ply_top_layer_material", spec["1_ply_top_layer_material"] || "");
				frm.set_value("2_ply_top_layer_material", spec["2_ply_top_layer_material"] || "");
				frm.set_value("3_ply_top_layer_material", spec["3_ply_top_layer_material"] || "");
				frm.set_value("4_ply_top_layer_material", spec["4_ply_top_layer_material"] || "");
				frm.set_value("5_ply_top_layer_material", spec["5_ply_top_layer_material"] || "");

				// Box layout
				frm.set_value("joint_type", spec.joint_type || "");
				frm.set_value("idod", spec.idod || "");
				frm.set_value("product_type", spec.product_type_carton || "");

				// Reset manual overrides on spec change
				frm.__flap_manual_override = false;
				frm.__actual_width_override = false;
				frm.__actual_length_override = false;

				frm.refresh_fields();
				vcl_run_calc_pipeline(frm);
			},
		});
	},

	// --- Pipeline triggers ---

	ply(frm) { vcl_run_calc_pipeline(frm); },
	ctn_length_mm(frm) { vcl_run_calc_pipeline(frm); },
	ctn_width_mm(frm) { vcl_run_calc_pipeline(frm); },
	ctn_height_mm(frm) { vcl_run_calc_pipeline(frm); },

	ctn_flap_mm(frm) {
		// If user manually edits flap, set override flag
		if (frm.doc.ctn_flap_mm && !frm.__flap_calc_in_progress) {
			frm.__flap_manual_override = true;
		}
		// Reset override if cleared to 0
		if (!frm.doc.ctn_flap_mm) {
			frm.__flap_manual_override = false;
		}
		vcl_run_calc_pipeline(frm);
	},

	trim_allowance_width_mm(frm) { vcl_run_calc_pipeline(frm); },
	trim_allowance_length_mm(frm) { vcl_run_calc_pipeline(frm); },
	max_reel_width(frm) { vcl_run_calc_pipeline(frm); },
	knife_gap_mm(frm) { vcl_run_calc_pipeline(frm); },

	"1_ply_top_layer_gsm": function(frm) { vcl_run_calc_pipeline(frm); },
	"2_ply_fluting_gsm": function(frm) { vcl_run_calc_pipeline(frm); },
	"3_ply_bottom_gsm": function(frm) { vcl_run_calc_pipeline(frm); },
	"4_ply_fluting_gsm": function(frm) { vcl_run_calc_pipeline(frm); },
	"5_ply_fluting_gsm": function(frm) { vcl_run_calc_pipeline(frm); },

	board_width_actual_mm(frm) {
		if (frm.doc.board_width_actual_mm && !frm.__actual_calc_in_progress) {
			frm.__actual_width_override = true;
		}
		if (!frm.doc.board_width_actual_mm) {
			frm.__actual_width_override = false;
		}
	},

	board_length_actual_mm(frm) {
		if (frm.doc.board_length_actual_mm && !frm.__actual_calc_in_progress) {
			frm.__actual_length_override = true;
		}
		if (!frm.doc.board_length_actual_mm) {
			frm.__actual_length_override = false;
		}
	},
});

// --- Spec field clearing ---

function _clear_spec_fields(frm) {
	frm.set_value("specification_name", "");
	frm.set_value("ply", "");
	frm.set_value("flute_type", "");
	frm.set_value("printing_or_plain", "");
	frm.set_value("no_of_colours", "0");
	frm.set_value("colours_details", "");
	frm.set_value("special_instructions", "");
	frm.set_value("ctn_length_mm", 0);
	frm.set_value("ctn_width_mm", 0);
	frm.set_value("ctn_height_mm", 0);
	frm.set_value("ctn_flap_mm", 0);

	["1_ply_top_layer_gsm", "2_ply_fluting_gsm", "3_ply_bottom_gsm",
	 "4_ply_fluting_gsm", "5_ply_fluting_gsm"].forEach(f => frm.set_value(f, 0));

	["1_ply_top_layer_material", "2_ply_top_layer_material", "3_ply_top_layer_material",
	 "4_ply_top_layer_material", "5_ply_top_layer_material"].forEach(f => frm.set_value(f, ""));

	frm.set_value("joint_type", "");
	frm.set_value("idod", "");
	frm.set_value("product_type", "");

	frm.set_value("board_width_planned_mm", 0);
	frm.set_value("board_width_actual_mm", 0);
	frm.set_value("board_length_planned_mm", 0);
	frm.set_value("board_length_actual_mm", 0);
	frm.set_value("approximate_weight_grams", 0);

	frm.refresh_fields();
}

// --- Serial Calculation Pipeline with anti-race protection ---

function vcl_run_calc_pipeline(frm) {
	if (_pipeline_running) {
		_pipeline_queued = true;
		return;
	}
	_pipeline_running = true;
	_pipeline_queued = false;

	frappe.run_serially([
		() => vcl_apply_ply_rules_serial(frm),
		() => vcl_apply_sfk_ui_rules_serial(frm),
		() => vcl_autofill_flap_serial(frm),
		() => vcl_calc_board_sizes_serial(frm),
		() => vcl_calc_approx_weight_serial(frm),
		() => {
			_pipeline_running = false;
			if (_pipeline_queued) {
				vcl_run_calc_pipeline(frm);
			}
		},
	]);
}

// --- Step 1: Ply Rules ---
// Show/hide GSM and Material fields based on ply selection
// SFK = layers 1-2, 3-ply = layers 1-3, 5-ply = all

function vcl_apply_ply_rules_serial(frm) {
	const ply = frm.doc.ply;

	const layer_fields = {
		"1": { gsm: "1_ply_top_layer_gsm", mat: "1_ply_top_layer_material" },
		"2": { gsm: "2_ply_fluting_gsm", mat: "2_ply_top_layer_material" },
		"3": { gsm: "3_ply_bottom_gsm", mat: "3_ply_top_layer_material" },
		"4": { gsm: "4_ply_fluting_gsm", mat: "4_ply_top_layer_material" },
		"5": { gsm: "5_ply_fluting_gsm", mat: "5_ply_top_layer_material" },
	};

	let visible_layers;
	if (ply === "SFK") {
		visible_layers = ["1", "2"];
	} else if (ply === "3") {
		visible_layers = ["1", "2", "3"];
	} else if (ply === "5") {
		visible_layers = ["1", "2", "3", "4", "5"];
	} else {
		visible_layers = [];
	}

	for (const [layer, fields] of Object.entries(layer_fields)) {
		const show = visible_layers.includes(layer);
		frm.set_df_property(fields.gsm, "hidden", show ? 0 : 1);
		frm.set_df_property(fields.mat, "hidden", show ? 0 : 1);
		if (!show) {
			frm.set_value(fields.gsm, 0);
			frm.set_value(fields.mat, "");
		}
	}
}

// --- Step 2: SFK UI Rules ---
// When SFK, hide and clear non-applicable fields

function vcl_apply_sfk_ui_rules_serial(frm) {
	const is_sfk = frm.doc.ply === "SFK";

	const sfk_hide_fields = [
		"ctn_height_mm", "joint_type", "idod", "product_type",
		"board_width_planned_mm", "board_width_actual_mm",
		"board_length_planned_mm", "board_length_actual_mm",
		"approximate_weight_grams",
	];

	sfk_hide_fields.forEach(function (f) {
		if (is_sfk) {
			// Store original properties for restoration
			if (!_sfk_original_props[f]) {
				_sfk_original_props[f] = {
					hidden: frm.fields_dict[f] ? frm.fields_dict[f].df.hidden : 0,
				};
			}
			frm.set_df_property(f, "hidden", 1);
		} else {
			// Restore original properties
			if (_sfk_original_props[f]) {
				frm.set_df_property(f, "hidden", _sfk_original_props[f].hidden || 0);
			}
		}
	});

	if (is_sfk) {
		frm.set_value("ctn_height_mm", 0);
		frm.set_value("joint_type", "");
		frm.set_value("idod", "");
		frm.set_value("product_type", "");
		frm.set_value("board_width_planned_mm", 0);
		frm.set_value("board_width_actual_mm", 0);
		frm.set_value("board_length_planned_mm", 0);
		frm.set_value("board_length_actual_mm", 0);
		frm.set_value("approximate_weight_grams", 0);
	}
}

// --- Step 3: Auto-fill Flap ---
// Flap = ceil((Width + 5) / 2). Respects manual override.

function vcl_autofill_flap_serial(frm) {
	if (frm.__flap_manual_override) return;
	if (frm.doc.ply === "SFK") {
		frm.__flap_calc_in_progress = true;
		frm.set_value("ctn_flap_mm", 0);
		frm.__flap_calc_in_progress = false;
		return;
	}

	const width = frm.doc.ctn_width_mm || 0;
	if (width > 0) {
		const flap = Math.ceil((width + 5) / 2);
		frm.__flap_calc_in_progress = true;
		frm.set_value("ctn_flap_mm", flap);
		frm.__flap_calc_in_progress = false;
	}
}

// --- Step 4: Calculate Board Sizes ---
// Planned Width = Flap + Height + Flap + Trim Allowance Width
// Planned Length = 2*L + 2*W + 30mm (glue tab) + Trim Allowance Length
// Actual = blank sizes (no trim) unless manually overridden

function vcl_calc_board_sizes_serial(frm) {
	if (frm.doc.ply === "SFK") return;

	const L = frm.doc.ctn_length_mm || 0;
	const W = frm.doc.ctn_width_mm || 0;
	const H = frm.doc.ctn_height_mm || 0;
	const flap = frm.doc.ctn_flap_mm || 0;
	const trim_w = frm.doc.trim_allowance_width_mm || 0;
	const trim_l = frm.doc.trim_allowance_length_mm || 0;
	const glue_tab = 30; // default glue tab width in mm

	// Blank sizes (1-UP, no trim)
	const blank_width = flap + H + flap;
	const blank_length = (2 * L) + (2 * W) + glue_tab;

	// Planned = blank + trim (for 1-UP; UPS multiplier applied in child table rows)
	const planned_width = blank_width + trim_w;
	const planned_length = blank_length + trim_l;

	frm.set_value("board_width_planned_mm", planned_width);
	frm.set_value("board_length_planned_mm", planned_length);

	// Auto-fill actual from blank sizes (no trim) unless manually overridden
	frm.__actual_calc_in_progress = true;
	if (!frm.__actual_width_override) {
		frm.set_value("board_width_actual_mm", blank_width);
	}
	if (!frm.__actual_length_override) {
		frm.set_value("board_length_actual_mm", blank_length);
	}
	frm.__actual_calc_in_progress = false;

	// Warn if planned width exceeds max reel width
	const max_reel = frm.doc.max_reel_width || 1500;
	if (planned_width > max_reel) {
		frappe.msgprint({
			title: __("Reel Width Warning"),
			message: __("Planned Board Width ({0}mm) exceeds Max Reel Width ({1}mm). Consider adjusting dimensions or using multiple UPS.", [planned_width, max_reel]),
			indicator: "orange",
		});
	}
}

// --- Step 5: Calculate Approximate Weight ---
// Weight (g) = (Planned Width mm * Planned Length mm / 1,000,000) * Total GSM

function vcl_calc_approx_weight_serial(frm) {
	if (frm.doc.ply === "SFK") return;

	const pw = frm.doc.board_width_planned_mm || 0;
	const pl = frm.doc.board_length_planned_mm || 0;

	// Sum visible GSM layers
	let total_gsm = 0;
	total_gsm += frm.doc["1_ply_top_layer_gsm"] || 0;
	total_gsm += frm.doc["2_ply_fluting_gsm"] || 0;

	if (frm.doc.ply === "3" || frm.doc.ply === "5") {
		total_gsm += frm.doc["3_ply_bottom_gsm"] || 0;
	}
	if (frm.doc.ply === "5") {
		total_gsm += frm.doc["4_ply_fluting_gsm"] || 0;
		total_gsm += frm.doc["5_ply_fluting_gsm"] || 0;
	}

	const area_m2 = (pw * pl) / 1000000;
	const weight_g = area_m2 * total_gsm;

	frm.set_value("approximate_weight_grams", flt(weight_g, 2));
}
