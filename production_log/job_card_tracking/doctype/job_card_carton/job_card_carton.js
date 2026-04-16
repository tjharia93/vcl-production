// Job Card Carton - Client Script
// Implements spec auto-populate + serial calculation pipeline with anti-race protection

let _pipeline_running = false;
let _pipeline_queued = false;

// Original field properties stored for SFK restore
let _sfk_original_props = {};

// --- Board Visualization Colors & Config ---
const VCL_COLORS = {
	primary: "#2B3990", fold: "#FF6B35", glue: "#4CAF50",
	stitch: "#D32F2F", cut: "#333333", face: "#C5CAE9",
	side: "#9FA8DA", top: "#7986CB", base: "#B39DDB", trayWall: "#81C784",
};

const VCL_JOINT_CONFIG = {
	"Gluing - Manual":  { tabWidth: 30, label: "Glue Tab",   color: "#4CAF5040", markerType: "glue" },
	"Gluing - Machine": { tabWidth: 30, label: "Glue Tab",   color: "#4CAF5040", markerType: "glue" },
	"Stitched":         { tabWidth: 40, label: "Stitch Flap", color: "#D32F2F30", markerType: "stitch" },
};

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
	product_type(frm) { vcl_run_calc_pipeline(frm); },
	joint_type(frm) { vcl_run_calc_pipeline(frm); },

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
		() => vcl_render_board_visualization(frm),
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

// ═══════════════════════════════════════════════════════════
// Step 6: Board Visualization — SVG die-cut rendering
// ═══════════════════════════════════════════════════════════

function vcl_render_board_visualization(frm) {
	const $wrapper = frm.fields_dict["html_board_visualization"]
		? frm.fields_dict["html_board_visualization"].$wrapper
		: null;
	if (!$wrapper) return;

	// Hide for SFK
	if (frm.doc.ply === "SFK") {
		$wrapper.html("");
		return;
	}

	const L = frm.doc.ctn_length_mm || 0;
	const W = frm.doc.ctn_width_mm || 0;
	const H = frm.doc.ctn_height_mm || 0;
	const flap = frm.doc.ctn_flap_mm || 0;
	const jointType = frm.doc.joint_type || "Stitched";
	const productType = frm.doc.product_type || "";

	// Need at least L and W to draw anything useful
	if (L <= 0 || W <= 0) {
		$wrapper.html(
			'<div style="padding:12px 16px;color:#888;font-size:13px;font-style:italic;">'
			+ "Enter carton dimensions to see the blank layout."
			+ "</div>"
		);
		return;
	}

	let svgContent = "";
	let legendHtml = "";

	if (productType === "2 Flap RSC" || productType === "3 Flap RSC") {
		svgContent = vcl_svg_two_flap_rsc(L, W, H, flap, jointType);
		legendHtml = vcl_legend_rsc(jointType);
	} else if (productType === "1 Flap RSC") {
		svgContent = vcl_svg_one_flap_rsc(L, W, H, flap, jointType);
		legendHtml = vcl_legend_rsc(jointType);
	} else if (productType === "Tray") {
		svgContent = vcl_svg_tray(L, W, H);
		legendHtml = vcl_legend_tray();
	} else if (productType === "Die Cut") {
		$wrapper.html(
			'<div style="padding:12px 16px;background:#FFF8E1;border-left:3px solid #FFA000;border-radius:4px;font-size:13px;color:#555;margin:8px 0;">'
			+ '<b style="color:#E65100;">Die Cut</b> — Visualization not available. Custom die shapes vary per job.'
			+ "</div>"
		);
		return;
	} else {
		$wrapper.html(
			'<div style="padding:12px 16px;color:#888;font-size:13px;font-style:italic;">'
			+ "Select a product type to see the blank layout."
			+ "</div>"
		);
		return;
	}

	$wrapper.html(
		'<div style="margin:8px 0 4px;">'
		+ svgContent
		+ legendHtml
		+ "</div>"
	);
}

// --- 2-Flap RSC (also used for 3-Flap RSC) ---

function vcl_svg_two_flap_rsc(L, W, H, flap, jointType) {
	const joint = VCL_JOINT_CONFIG[jointType] || VCL_JOINT_CONFIG["Stitched"];
	const tabWidth = joint.tabWidth;
	const totalW = tabWidth + L + W + L + W;
	const totalH = flap + H + flap;

	if (totalW <= 0 || totalH <= 0) return "";

	const scale = Math.min(0.42, 580 / totalW, 380 / totalH);
	const ox = 30, oy = 40;
	const svgW = totalW * scale + 70;
	const svgH = totalH * scale + 60;

	let svg = '<svg width="' + svgW + '" height="' + svgH + '" style="background:#FAFAFA;border:1px solid #ddd;border-radius:4px;">';

	// Panels — main body row
	const panels = [
		{ label: joint.label, x: 0, y: flap, w: tabWidth, h: H, color: joint.color },
		{ label: "Side (" + W + "mm)", x: tabWidth, y: flap, w: L, h: H, color: VCL_COLORS.side + "60" },
		{ label: "Front (" + L + "mm)", x: tabWidth + L, y: flap, w: W, h: H, color: VCL_COLORS.face + "80" },
		{ label: "Side (" + W + "mm)", x: tabWidth + L + W, y: flap, w: L, h: H, color: VCL_COLORS.side + "60" },
		{ label: "Back (" + L + "mm)", x: tabWidth + L + W + L, y: flap, w: W, h: H, color: VCL_COLORS.face + "80" },
	];

	// Flap sets — top and bottom for each body panel (not tab)
	const xPositions = [tabWidth, tabWidth + L, tabWidth + L + W, tabWidth + L + W + L];
	const widths = [L, W, L, W];
	const flapColors = [VCL_COLORS.top + "35", VCL_COLORS.top + "50", VCL_COLORS.top + "35", VCL_COLORS.top + "50"];
	const flapSets = [];
	for (let i = 0; i < xPositions.length; i++) {
		flapSets.push({ x: xPositions[i], y: 0, w: widths[i], h: flap, color: flapColors[i], label: "Top flap" });
		flapSets.push({ x: xPositions[i], y: flap + H, w: widths[i], h: flap, color: flapColors[i], label: "Btm flap" });
	}

	var allPanels = panels.concat(flapSets);

	// Draw panels
	for (let i = 0; i < allPanels.length; i++) {
		var p = allPanels[i];
		svg += '<rect x="' + (ox + p.x * scale) + '" y="' + (oy + p.y * scale)
			+ '" width="' + (p.w * scale) + '" height="' + (p.h * scale)
			+ '" fill="' + p.color + '" stroke="' + VCL_COLORS.cut + '" stroke-width="1.5"/>';
		if (p.w * scale > 36) {
			var fontSize = Math.min(11, p.w * scale * 0.13);
			svg += '<text x="' + (ox + (p.x + p.w / 2) * scale)
				+ '" y="' + (oy + (p.y + p.h / 2) * scale)
				+ '" text-anchor="middle" dominant-baseline="middle" font-size="' + fontSize
				+ '" fill="#333" font-weight="500">' + p.label + "</text>";
		}
	}

	// Vertical fold lines
	var foldXPositions = [tabWidth, tabWidth + L, tabWidth + L + W, tabWidth + L + W + L];
	for (let i = 0; i < foldXPositions.length; i++) {
		var fx = foldXPositions[i];
		svg += '<line x1="' + (ox + fx * scale) + '" y1="' + oy
			+ '" x2="' + (ox + fx * scale) + '" y2="' + (oy + totalH * scale)
			+ '" stroke="' + VCL_COLORS.fold + '" stroke-width="1.5" stroke-dasharray="6,4"/>';
	}

	// Horizontal fold lines (top of body, bottom of body)
	var hFoldYs = [flap, flap + H];
	for (let i = 0; i < hFoldYs.length; i++) {
		var fy = hFoldYs[i];
		svg += '<line x1="' + (ox + tabWidth * scale) + '" y1="' + (oy + fy * scale)
			+ '" x2="' + (ox + totalW * scale) + '" y2="' + (oy + fy * scale)
			+ '" stroke="' + VCL_COLORS.fold + '" stroke-width="1" stroke-dasharray="4,3"/>';
	}

	// Joint markers
	if (joint.markerType === "stitch") {
		var spacing = 25;
		var count = Math.floor(H / spacing);
		var startY = flap + (H - count * spacing) / 2;
		for (let i = 0; i <= count; i++) {
			var cy = oy + (startY + i * spacing) * scale;
			var cx = ox + (tabWidth * 0.6) * scale;
			svg += '<line x1="' + (cx - 3) + '" y1="' + (cy - 3) + '" x2="' + (cx + 3) + '" y2="' + (cy + 3)
				+ '" stroke="' + VCL_COLORS.stitch + '" stroke-width="1.5"/>';
			svg += '<line x1="' + (cx + 3) + '" y1="' + (cy - 3) + '" x2="' + (cx - 3) + '" y2="' + (cy + 3)
				+ '" stroke="' + VCL_COLORS.stitch + '" stroke-width="1.5"/>';
		}
	} else if (joint.markerType === "glue") {
		var fracs = [0.25, 0.5, 0.75];
		for (let i = 0; i < fracs.length; i++) {
			var gy = oy + (flap + H * fracs[i]) * scale;
			svg += '<line x1="' + (ox + (tabWidth * 0.2) * scale)
				+ '" y1="' + gy + '" x2="' + (ox + (tabWidth * 0.8) * scale)
				+ '" y2="' + gy
				+ '" stroke="' + VCL_COLORS.glue + '" stroke-width="2" stroke-dasharray="3,2" opacity="0.6"/>';
		}
	}

	// Dimension labels
	svg += '<text x="' + (ox + (tabWidth + L / 2) * scale) + '" y="' + (oy + totalH * scale + 14)
		+ '" text-anchor="middle" font-size="10" fill="#666">' + L + "mm</text>";
	svg += '<text x="' + (ox + (tabWidth + L + W / 2) * scale) + '" y="' + (oy + totalH * scale + 14)
		+ '" text-anchor="middle" font-size="10" fill="#666">' + W + "mm</text>";
	svg += '<text x="' + (ox + totalW * scale + 6) + '" y="' + (oy + (flap + H / 2) * scale)
		+ '" text-anchor="start" dominant-baseline="middle" font-size="10" fill="#666">' + H + "mm</text>";
	svg += '<text x="' + (ox + totalW * scale + 6) + '" y="' + (oy + (flap / 2) * scale)
		+ '" text-anchor="start" dominant-baseline="middle" font-size="10" fill="#666">' + flap + "mm</text>";
	svg += '<text x="' + (ox + (tabWidth / 2) * scale) + '" y="' + (oy - 8)
		+ '" text-anchor="middle" font-size="9" fill="#888">' + tabWidth + "mm</text>";

	// Bottom summary line
	svg += '<line x1="' + ox + '" y1="' + (oy + totalH * scale + 24)
		+ '" x2="' + (ox + totalW * scale) + '" y2="' + (oy + totalH * scale + 24)
		+ '" stroke="#999" stroke-width="0.5"/>';
	svg += '<text x="' + (ox + (totalW / 2) * scale) + '" y="' + (oy + totalH * scale + 38)
		+ '" text-anchor="middle" font-size="11" fill="' + VCL_COLORS.primary
		+ '" font-weight="600">Blank: ' + totalW + "mm x " + totalH + "mm</text>";

	svg += "</svg>";
	return svg;
}

// --- 1-Flap RSC ---

function vcl_svg_one_flap_rsc(L, W, H, flap, jointType) {
	const joint = VCL_JOINT_CONFIG[jointType] || VCL_JOINT_CONFIG["Stitched"];
	const tabWidth = joint.tabWidth;
	const totalW = tabWidth + L + W + L + W;
	const totalH = H + flap;

	if (totalW <= 0 || totalH <= 0) return "";

	const scale = Math.min(0.42, 580 / totalW, 380 / totalH);
	const ox = 30, oy = 40;
	const svgW = totalW * scale + 70;
	const svgH = totalH * scale + 60;

	let svg = '<svg width="' + svgW + '" height="' + svgH + '" style="background:#FAFAFA;border:1px solid #ddd;border-radius:4px;">';

	// Panels — main body row (no top flap offset — body starts at y=0)
	const panels = [
		{ label: joint.label, x: 0, y: 0, w: tabWidth, h: H, color: joint.color },
		{ label: "Side (" + W + "mm)", x: tabWidth, y: 0, w: L, h: H, color: VCL_COLORS.side + "60" },
		{ label: "Front (" + L + "mm)", x: tabWidth + L, y: 0, w: W, h: H, color: VCL_COLORS.face + "80" },
		{ label: "Side (" + W + "mm)", x: tabWidth + L + W, y: 0, w: L, h: H, color: VCL_COLORS.side + "60" },
		{ label: "Back (" + L + "mm)", x: tabWidth + L + W + L, y: 0, w: W, h: H, color: VCL_COLORS.face + "80" },
	];

	// Only bottom flaps (below body)
	const xPositions = [tabWidth, tabWidth + L, tabWidth + L + W, tabWidth + L + W + L];
	const widths = [L, W, L, W];
	const flapColors = [VCL_COLORS.top + "35", VCL_COLORS.top + "50", VCL_COLORS.top + "35", VCL_COLORS.top + "50"];
	const flapSets = [];
	for (let i = 0; i < xPositions.length; i++) {
		flapSets.push({ x: xPositions[i], y: H, w: widths[i], h: flap, color: flapColors[i], label: "Flap" });
	}

	var allPanels = panels.concat(flapSets);

	// Draw panels
	for (let i = 0; i < allPanels.length; i++) {
		var p = allPanels[i];
		svg += '<rect x="' + (ox + p.x * scale) + '" y="' + (oy + p.y * scale)
			+ '" width="' + (p.w * scale) + '" height="' + (p.h * scale)
			+ '" fill="' + p.color + '" stroke="' + VCL_COLORS.cut + '" stroke-width="1.5"/>';
		if (p.w * scale > 36) {
			var fontSize = Math.min(11, p.w * scale * 0.13);
			svg += '<text x="' + (ox + (p.x + p.w / 2) * scale)
				+ '" y="' + (oy + (p.y + p.h / 2) * scale)
				+ '" text-anchor="middle" dominant-baseline="middle" font-size="' + fontSize
				+ '" fill="#333" font-weight="500">' + p.label + "</text>";
		}
	}

	// Vertical fold lines
	var foldXPositions = [tabWidth, tabWidth + L, tabWidth + L + W, tabWidth + L + W + L];
	for (let i = 0; i < foldXPositions.length; i++) {
		var fx = foldXPositions[i];
		svg += '<line x1="' + (ox + fx * scale) + '" y1="' + oy
			+ '" x2="' + (ox + fx * scale) + '" y2="' + (oy + totalH * scale)
			+ '" stroke="' + VCL_COLORS.fold + '" stroke-width="1.5" stroke-dasharray="6,4"/>';
	}

	// Horizontal fold line (body/flap boundary)
	svg += '<line x1="' + (ox + tabWidth * scale) + '" y1="' + (oy + H * scale)
		+ '" x2="' + (ox + totalW * scale) + '" y2="' + (oy + H * scale)
		+ '" stroke="' + VCL_COLORS.fold + '" stroke-width="1" stroke-dasharray="4,3"/>';

	// Open end label at top
	svg += '<text x="' + (ox + (totalW / 2) * scale) + '" y="' + (oy - 10)
		+ '" text-anchor="middle" font-size="9" fill="#999" font-style="italic">Open end (no flap)</text>';

	// Joint markers
	if (joint.markerType === "stitch") {
		var spacing = 25;
		var count = Math.floor(H / spacing);
		var startY = (H - count * spacing) / 2;
		for (let i = 0; i <= count; i++) {
			var cy = oy + (startY + i * spacing) * scale;
			var cx = ox + (tabWidth * 0.6) * scale;
			svg += '<line x1="' + (cx - 3) + '" y1="' + (cy - 3) + '" x2="' + (cx + 3) + '" y2="' + (cy + 3)
				+ '" stroke="' + VCL_COLORS.stitch + '" stroke-width="1.5"/>';
			svg += '<line x1="' + (cx + 3) + '" y1="' + (cy - 3) + '" x2="' + (cx - 3) + '" y2="' + (cy + 3)
				+ '" stroke="' + VCL_COLORS.stitch + '" stroke-width="1.5"/>';
		}
	} else if (joint.markerType === "glue") {
		var fracs = [0.25, 0.5, 0.75];
		for (let i = 0; i < fracs.length; i++) {
			var gy = oy + (H * fracs[i]) * scale;
			svg += '<line x1="' + (ox + (tabWidth * 0.2) * scale)
				+ '" y1="' + gy + '" x2="' + (ox + (tabWidth * 0.8) * scale)
				+ '" y2="' + gy
				+ '" stroke="' + VCL_COLORS.glue + '" stroke-width="2" stroke-dasharray="3,2" opacity="0.6"/>';
		}
	}

	// Dimension labels
	svg += '<text x="' + (ox + (tabWidth + L / 2) * scale) + '" y="' + (oy + totalH * scale + 14)
		+ '" text-anchor="middle" font-size="10" fill="#666">' + L + "mm</text>";
	svg += '<text x="' + (ox + (tabWidth + L + W / 2) * scale) + '" y="' + (oy + totalH * scale + 14)
		+ '" text-anchor="middle" font-size="10" fill="#666">' + W + "mm</text>";
	svg += '<text x="' + (ox + totalW * scale + 6) + '" y="' + (oy + (H / 2) * scale)
		+ '" text-anchor="start" dominant-baseline="middle" font-size="10" fill="#666">' + H + "mm</text>";
	svg += '<text x="' + (ox + totalW * scale + 6) + '" y="' + (oy + (H + flap / 2) * scale)
		+ '" text-anchor="start" dominant-baseline="middle" font-size="10" fill="#666">' + flap + "mm</text>";
	svg += '<text x="' + (ox + (tabWidth / 2) * scale) + '" y="' + (oy - 8)
		+ '" text-anchor="middle" font-size="9" fill="#888">' + tabWidth + "mm</text>";

	// Bottom summary line
	svg += '<line x1="' + ox + '" y1="' + (oy + totalH * scale + 24)
		+ '" x2="' + (ox + totalW * scale) + '" y2="' + (oy + totalH * scale + 24)
		+ '" stroke="#999" stroke-width="0.5"/>';
	svg += '<text x="' + (ox + (totalW / 2) * scale) + '" y="' + (oy + totalH * scale + 38)
		+ '" text-anchor="middle" font-size="11" fill="' + VCL_COLORS.primary
		+ '" font-weight="600">Blank: ' + totalW + "mm x " + totalH + "mm</text>";

	svg += "</svg>";
	return svg;
}

// --- Tray (FTD) ---

function vcl_svg_tray(L, W, H) {
	var totalW = H + W + H;
	var totalH = H + L + H;

	if (totalW <= 0 || totalH <= 0) return "";

	var scale = Math.min(0.55, 500 / totalW, 420 / totalH);
	var ox = 30, oy = 30;
	var svgW = totalW * scale + 60;
	var svgH = totalH * scale + 60;

	var svg = '<svg width="' + svgW + '" height="' + svgH + '" style="background:#FAFAFA;border:1px solid #ddd;border-radius:4px;">';

	// Corner ear tabs (triangular)
	var ears = [
		{ x: 0, y: 0, w: H, h: H },
		{ x: H + W, y: 0, w: H, h: H },
		{ x: 0, y: H + L, w: H, h: H },
		{ x: H + W, y: H + L, w: H, h: H },
	];
	// Centroid offsets for label positioning inside each triangle
	var earLabelOffsets = [
		[0.65, 0.65], // top-left
		[0.35, 0.65], // top-right
		[0.65, 0.35], // bottom-left
		[0.35, 0.35], // bottom-right
	];
	for (let i = 0; i < ears.length; i++) {
		var e = ears[i];
		var sx = ox + e.x * scale, sy = oy + e.y * scale;
		var sw = e.w * scale, sh = e.h * scale;
		var points;
		if (i === 0) points = sx + "," + (sy + sh) + " " + (sx + sw) + "," + sy + " " + (sx + sw) + "," + (sy + sh);
		else if (i === 1) points = sx + "," + sy + " " + (sx + sw) + "," + (sy + sh) + " " + sx + "," + (sy + sh);
		else if (i === 2) points = (sx + sw) + "," + sy + " " + sx + "," + (sy + sh) + " " + (sx + sw) + "," + (sy + sh);
		else points = sx + "," + sy + " " + (sx + sw) + "," + sy + " " + sx + "," + (sy + sh);
		svg += '<polygon points="' + points + '" fill="#E0E0E0" stroke="' + VCL_COLORS.cut + '" stroke-width="1" stroke-dasharray="3,3"/>';
		// Corner tab dimension label
		if (sw > 20 && sh > 20) {
			var lx = sx + sw * earLabelOffsets[i][0];
			var ly = sy + sh * earLabelOffsets[i][1];
			svg += '<text x="' + lx + '" y="' + ly + '" text-anchor="middle" dominant-baseline="middle" font-size="7" fill="#888" font-weight="500">' + H + "x" + H + "</text>";
		}
	}

	// Main panels: base + 4 walls (labels show both dimensions)
	var allPanels = [
		{ x: H, y: H, w: W, h: L, color: VCL_COLORS.base + "50", label: "Base (" + L + " x " + W + ")" },
		{ x: H, y: 0, w: W, h: H, color: VCL_COLORS.trayWall + "50", label: "Front (" + W + "x" + H + ")" },
		{ x: H, y: H + L, w: W, h: H, color: VCL_COLORS.trayWall + "50", label: "Back (" + W + "x" + H + ")" },
		{ x: 0, y: H, w: H, h: L, color: VCL_COLORS.trayWall + "35", label: "Side (" + H + "x" + L + ")" },
		{ x: H + W, y: H, w: H, h: L, color: VCL_COLORS.trayWall + "35", label: "Side (" + H + "x" + L + ")" },
	];
	for (let i = 0; i < allPanels.length; i++) {
		var p = allPanels[i];
		svg += '<rect x="' + (ox + p.x * scale) + '" y="' + (oy + p.y * scale)
			+ '" width="' + (p.w * scale) + '" height="' + (p.h * scale)
			+ '" fill="' + p.color + '" stroke="' + VCL_COLORS.cut + '" stroke-width="1.5"/>';
		if (p.w * scale > 50 && p.h * scale > 20) {
			var fontSize = Math.min(11, Math.min(p.w, p.h) * scale * 0.15);
			svg += '<text x="' + (ox + (p.x + p.w / 2) * scale)
				+ '" y="' + (oy + (p.y + p.h / 2) * scale)
				+ '" text-anchor="middle" dominant-baseline="middle" font-size="' + fontSize
				+ '" fill="#333" font-weight="500">' + p.label + "</text>";
		}
	}

	// Fold lines around base (4 lines forming a cross)
	svg += '<line x1="' + (ox + H * scale) + '" y1="' + oy + '" x2="' + (ox + H * scale) + '" y2="' + (oy + totalH * scale)
		+ '" stroke="' + VCL_COLORS.fold + '" stroke-width="1.5" stroke-dasharray="6,4"/>';
	svg += '<line x1="' + (ox + (H + W) * scale) + '" y1="' + oy + '" x2="' + (ox + (H + W) * scale) + '" y2="' + (oy + totalH * scale)
		+ '" stroke="' + VCL_COLORS.fold + '" stroke-width="1.5" stroke-dasharray="6,4"/>';
	svg += '<line x1="' + ox + '" y1="' + (oy + H * scale) + '" x2="' + (ox + totalW * scale) + '" y2="' + (oy + H * scale)
		+ '" stroke="' + VCL_COLORS.fold + '" stroke-width="1.5" stroke-dasharray="6,4"/>';
	svg += '<line x1="' + ox + '" y1="' + (oy + (H + L) * scale) + '" x2="' + (ox + totalW * scale) + '" y2="' + (oy + (H + L) * scale)
		+ '" stroke="' + VCL_COLORS.fold + '" stroke-width="1.5" stroke-dasharray="6,4"/>';

	// Dimension labels
	svg += '<text x="' + (ox + (H + W / 2) * scale) + '" y="' + (oy + totalH * scale + 14)
		+ '" text-anchor="middle" font-size="10" fill="#666">' + W + "mm</text>";
	svg += '<text x="' + (ox + (H / 2) * scale) + '" y="' + (oy + totalH * scale + 14)
		+ '" text-anchor="middle" font-size="10" fill="#666">' + H + "mm</text>";
	svg += '<text x="' + (ox + totalW * scale + 6) + '" y="' + (oy + (H + L / 2) * scale)
		+ '" text-anchor="start" dominant-baseline="middle" font-size="10" fill="#666">' + L + "mm</text>";
	svg += '<text x="' + (ox + totalW * scale + 6) + '" y="' + (oy + (H / 2) * scale)
		+ '" text-anchor="start" dominant-baseline="middle" font-size="10" fill="#666">' + H + "mm</text>";

	// Bottom summary line
	svg += '<line x1="' + ox + '" y1="' + (oy + totalH * scale + 24)
		+ '" x2="' + (ox + totalW * scale) + '" y2="' + (oy + totalH * scale + 24)
		+ '" stroke="#999" stroke-width="0.5"/>';
	svg += '<text x="' + (ox + (totalW / 2) * scale) + '" y="' + (oy + totalH * scale + 38)
		+ '" text-anchor="middle" font-size="11" fill="' + VCL_COLORS.primary
		+ '" font-weight="600">Blank: ' + totalW + "mm x " + totalH + "mm</text>";

	// Left-side total height label
	svg += '<line x1="' + (ox - 10) + '" y1="' + oy + '" x2="' + (ox - 10) + '" y2="' + (oy + totalH * scale)
		+ '" stroke="#999" stroke-width="0.5"/>';
	var rotateY = oy + (totalH / 2) * scale;
	svg += '<text x="' + (ox - 14) + '" y="' + rotateY
		+ '" text-anchor="middle" dominant-baseline="middle" font-size="10" fill="' + VCL_COLORS.primary
		+ '" font-weight="600" transform="rotate(-90, ' + (ox - 14) + ", " + rotateY + ')">'
		+ totalH + "mm</text>";

	svg += "</svg>";
	return svg;
}

// --- Legends ---

function vcl_legend_rsc(jointType) {
	var isStitch = (jointType === "Stitched");
	return '<div style="margin-top:8px;display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:#666;">'
		+ '<span><span style="display:inline-block;width:20px;border-top:2px dashed ' + VCL_COLORS.fold + ';margin-right:4px;vertical-align:middle;"></span> Fold line</span>'
		+ '<span><span style="display:inline-block;width:14px;height:14px;background:' + VCL_COLORS.face + '80;border:1px solid #999;margin-right:4px;vertical-align:middle;"></span> Front/Back</span>'
		+ '<span><span style="display:inline-block;width:14px;height:14px;background:' + VCL_COLORS.side + '60;border:1px solid #999;margin-right:4px;vertical-align:middle;"></span> Side</span>'
		+ '<span><span style="display:inline-block;width:14px;height:14px;background:' + VCL_COLORS.top + '50;border:1px solid #999;margin-right:4px;vertical-align:middle;"></span> Flaps</span>'
		+ (isStitch
			? '<span><span style="color:' + VCL_COLORS.stitch + ';font-weight:700;margin-right:4px;">X</span> Stitch marks</span>'
			: '<span><span style="display:inline-block;width:20px;border-top:2px dashed ' + VCL_COLORS.glue + ';margin-right:4px;vertical-align:middle;"></span> Glue lines</span>')
		+ "</div>";
}

function vcl_legend_tray() {
	return '<div style="margin-top:8px;display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:#666;">'
		+ '<span><span style="display:inline-block;width:20px;border-top:2px dashed ' + VCL_COLORS.fold + ';margin-right:4px;vertical-align:middle;"></span> Fold line</span>'
		+ '<span><span style="display:inline-block;width:14px;height:14px;background:' + VCL_COLORS.base + '50;border:1px solid #999;margin-right:4px;vertical-align:middle;"></span> Base</span>'
		+ '<span><span style="display:inline-block;width:14px;height:14px;background:' + VCL_COLORS.trayWall + '50;border:1px solid #999;margin-right:4px;vertical-align:middle;"></span> Walls</span>'
		+ '<span><span style="display:inline-block;width:14px;height:14px;background:#E0E0E0;border:1px solid #999;margin-right:4px;vertical-align:middle;"></span> Corner tabs</span>'
		+ "</div>";
}
