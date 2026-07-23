// Copyright (c) 2026, VCL and contributors
// For license information, please see license.txt

const NAMING_SERIES_MAP = {
	"Computer Paper":               "CPT-SPEC-.#####",
	"Carton":                       "CTN-SPEC-.#####",
	"Label":                        "LBL-SPEC-.#####",
	"Exercise Books":               "EXB-SPEC-.#####",
	"ETR (Reel to Reel Printing)": "ETR-SPEC-.#####",
};

const INK_TYPE_DEFAULTS = {
	"Computer Paper":               "Process Offset",
	"Carton":                       "Process Offset",
	"Label":                        "Process UV",
	"ETR (Reel to Reel Printing)": "Water Based",
};

const PAPER_RULES = {
	single: { paper_type: "60 GSM Bond", gsm: 60 },
	first:  { paper_type: "CB",          gsm: 55 },
	middle: { paper_type: "CFB",         gsm: 50 },
	last:   { paper_type: "CF",          gsm: 55 },
};

const GSM_BY_PAPER_TYPE = {
	"CB":          55,
	"CFB":         50,
	"CF":          55,
	"60 GSM Bond": 60,
	"70 GSM Bond": 70,
};

const CMYK_FIELDS = ["uses_c", "uses_m", "uses_y", "uses_k"];

// --- Price approval (WBS-23) ------------------------------------------------
//
// Only an Approved CPS Price row can price a Sales Order line, and until now the
// only way to approve one was to call the endpoint by hand. These two grid
// actions call the same deployed endpoint.
//
// The role check below governs whether the buttons are *shown*. It is not the
// control: `cps_pricing.approve_cps_price` refuses a caller without the role
// regardless, which is what actually holds, since a hidden button is one console
// line away from being pressed. Self-approval is permitted and logged (DN-3) —
// blocking it would deadlock a two-person sales office.

const APPROVER_ROLE = "Sales Master Manager";
const APPROVE_METHOD = "production_log.job_card_tracking.cps_pricing.approve_cps_price";

function can_approve_prices() {
	return frappe.user.has_role(APPROVER_ROLE);
}

function selected_price_row(frm) {
	const grid = frm.fields_dict.pricing && frm.fields_dict.pricing.grid;
	if (!grid) return null;

	const selected = grid.get_selected_children();
	if (selected.length > 1) {
		frappe.msgprint(__("Tick one price row at a time — each is approved on its own merits."));
		return null;
	}
	if (!selected.length) {
		const draft_rows = (frm.doc.pricing || []).filter(
			(row) => (row.approval_status || "Draft") === "Draft"
		);
		if (draft_rows.length === 1) return draft_rows[0];
		frappe.msgprint(__("Tick one Draft price row to act on first."));
		return null;
	}
	return selected[0];
}

function decide_price(frm, action) {
	if (frm.is_new() || frm.is_dirty()) {
		// The endpoint reloads the document server-side, so an unsaved edit
		// would be silently discarded and the approval would land on the stored
		// rate rather than on the one on screen.
		frappe.msgprint(__("Save the specification before approving or rejecting a price."));
		return;
	}

	const row = selected_price_row(frm);
	if (!row) return;

	const approving = action === "approve";
	const label = approving ? __("Approve Price") : __("Reject Price");

	const d = new frappe.ui.Dialog({
		title: label,
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "summary",
				options: `<p>${__("Row effective {0} at {1} {2}.", [
					frappe.format(row.valid_from, { fieldtype: "Date" }),
					format_currency(row.rate),
					frappe.utils.escape_html(row.uom || ""),
				])}</p>
				<p style="color:#666;font-size:12px;">${
					approving
						? __("Approved rows price Sales Order lines from their effective date. Editing the rate, UOM or effective date afterwards returns the row to Draft.")
						: __("Rejected rows are invisible to pricing and may be superseded by a corrected row carrying the same effective date.")
				}</p>`,
			},
			{
				fieldtype: "Small Text",
				fieldname: "notes",
				label: __("Approval Notes"),
				reqd: approving ? 0 : 1,
				description: approving
					? __("Optional. Where the rate came from, or what it was checked against.")
					: __("Required. Why this rate was rejected."),
			},
		],
		primary_action_label: label,
		primary_action(values) {
			d.hide();
			frappe.call({
				method: APPROVE_METHOD,
				args: { cps: frm.doc.name, row: row.name, action, notes: values.notes },
				freeze: true,
				freeze_message: __("Recording the decision…"),
				callback(r) {
					if (!r.message) return;
					frappe.show_alert({
						message: __("Price row is now {0}.", [__(r.message.approval_status)]),
						indicator: approving ? "green" : "red",
					});
					// Reloaded rather than patched in place: the endpoint also
					// re-derives current_rate and current_uom on the parent, and
					// showing a stale headline rate next to a fresh approval is
					// exactly the confusion this feature exists to remove.
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
}

function add_price_approval_actions(frm) {
	if (!frm.fields_dict.pricing || !can_approve_prices()) return;

	// Main-form actions remain visible on submitted/amended specifications,
	// where Frappe may render the child grid read-only and hide grid actions.
	frm.add_custom_button(__("Approve Price"), () =>
		decide_price(frm, "approve")
	, __("Pricing"));
	frm.add_custom_button(__("Reject Price"), () =>
		decide_price(frm, "reject")
	, __("Pricing"));
}

function get_paper_rule(part_num, total_parts) {
	if (total_parts === 1)        return PAPER_RULES.single;
	if (part_num === 1)           return PAPER_RULES.first;
	if (part_num === total_parts) return PAPER_RULES.last;
	return PAPER_RULES.middle;
}

function update_paper_type_and_gsm(frm, row, part_num, total_parts) {
	const rule = get_paper_rule(part_num, total_parts);
	frappe.model.set_value(row.doctype, row.name, "paper_type", rule.paper_type);
	frappe.model.set_value(row.doctype, row.name, "gsm", rule.gsm);
}

function sync_colour_of_parts(frm) {
	const target = cint(frm.doc.number_of_parts);
	if (!target || target < 1) return;

	const parts = frm.doc.colour_of_parts || [];
	const current = parts.length;

	if (current < target) {
		for (let i = current; i < target; i++) {
			const row = frappe.model.add_child(frm.doc, "Colour of Parts", "colour_of_parts");
			row.part_number = i + 1;
		}
	} else if (current > target) {
		frm.doc.colour_of_parts = parts.slice(0, target);
	}

	(frm.doc.colour_of_parts || []).forEach((row, idx) => {
		const part_num = idx + 1;
		frappe.model.set_value(row.doctype, row.name, "part_number", part_num);
		update_paper_type_and_gsm(frm, row, part_num, target);
	});

	frm.refresh_field("colour_of_parts");
}

function renumber_parts(frm) {
	const parts = frm.doc.colour_of_parts || [];
	const total = parts.length;
	parts.forEach((row, idx) => {
		const part_num = idx + 1;
		frappe.model.set_value(row.doctype, row.name, "part_number", part_num);
		update_paper_type_and_gsm(frm, row, part_num, total);
	});
	frm.refresh_field("colour_of_parts");
}

function recalculate_number_of_colours(frm) {
	const ticks = CMYK_FIELDS.reduce((n, f) => n + (frm.doc[f] ? 1 : 0), 0);
	const spots = (frm.doc.spot_colours || []).length;
	frm.set_value("number_of_colours", ticks + spots);
}

function open_nearest_pantone_dialog(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const hex = row.hex_preview;
	if (!hex) {
		frappe.msgprint(__("Enter a hex value in this row first."));
		return;
	}
	frappe.call({
		method: "production_log.job_card_tracking.doctype.pantone_colour.pantone_colour.find_nearest",
		args:   { hex_value: hex, limit: 8 },
		callback(r) {
			const matches = r.message || [];
			if (!matches.length) {
				frappe.msgprint(__("No Pantone matches found. Make sure the Pantone Colour master has been seeded."));
				return;
			}

			const rows_html = matches.map((m) => `
				<tr data-name="${frappe.utils.escape_html(m.name)}" style="cursor:pointer">
					<td style="padding:6px 8px;">
						<span style="display:inline-block;width:26px;height:18px;border-radius:3px;border:1px solid #ccc;background:${m.hex_value || "#fff"};vertical-align:middle;"></span>
					</td>
					<td style="padding:6px 8px;"><b>${frappe.utils.escape_html(m.code)}</b></td>
					<td style="padding:6px 8px;">${frappe.utils.escape_html(m.display_name || "")}</td>
					<td style="padding:6px 8px;color:#666;">${m.hex_value || ""}</td>
					<td style="padding:6px 8px;color:#666;text-align:right;">ΔE&nbsp;${m._distance.toFixed(1)}</td>
				</tr>
			`).join("");

			const d = new frappe.ui.Dialog({
				title:  __("Nearest Pantone Matches"),
				fields: [{
					fieldtype: "HTML",
					fieldname: "matches_html",
					options: `
						<p style="color:#666;font-size:12px;margin-bottom:8px;">
							Ranked by ΔE distance in LAB colour space. Click a row to apply.
							Hex previews are approximations — always verify against physical Pantone chips.
						</p>
						<table style="width:100%;border-collapse:collapse;font-size:13px;">
							<thead>
								<tr style="background:#f5f5f5;">
									<th></th>
									<th style="text-align:left;padding:6px 8px;">Code</th>
									<th style="text-align:left;padding:6px 8px;">Name</th>
									<th style="text-align:left;padding:6px 8px;">Hex</th>
									<th style="text-align:right;padding:6px 8px;">Distance</th>
								</tr>
							</thead>
							<tbody>${rows_html}</tbody>
						</table>
					`,
				}],
			});
			d.show();

			d.$wrapper.find("tbody tr").on("click", function () {
				const pantone_name = $(this).data("name");
				frappe.model.set_value(cdt, cdn, "pantone_code", pantone_name);
				d.hide();
			});
		},
	});
}

frappe.ui.form.on("Customer Product Specification", {
	refresh(frm) {
		recalculate_number_of_colours(frm);
		add_price_approval_actions(frm);

	},

	product_type(frm) {
		const series = NAMING_SERIES_MAP[frm.doc.product_type];
		if (series) frm.set_value("naming_series", series);

		const default_ink = INK_TYPE_DEFAULTS[frm.doc.product_type];
		if (default_ink && !frm.doc.ink_type) {
			frm.set_value("ink_type", default_ink);
		}
	},

	number_of_parts(frm) {
		if (frm.doc.product_type !== "Computer Paper") return;
		sync_colour_of_parts(frm);
	},

	uses_c(frm) { recalculate_number_of_colours(frm); },
	uses_m(frm) { recalculate_number_of_colours(frm); },
	uses_y(frm) { recalculate_number_of_colours(frm); },
	uses_k(frm) { recalculate_number_of_colours(frm); },

	full_cmyk_button(frm) {
		CMYK_FIELDS.forEach((f) => frm.set_value(f, 1));
	},

	dies(frm) {
		if (frm.doc.product_type !== "Label" || !frm.doc.dies) return;
		frappe.call({
			method: "frappe.client.get",
			args: { doctype: "Dies", name: frm.doc.dies },
			callback(r) {
				if (!r.message) return;
				const d = r.message;
				frm.set_value("label_length",  d.length);
				frm.set_value("label_width",   d.width);
				frm.set_value("cylinder_teeth", d.teeth);
				frm.set_value("plate_up",      d.across_ups);
				frm.set_value("plate_round",   d.round_ups);
				frm.set_value("packing_pieces", d.qty);
			},
		});
	},
});

frappe.ui.form.on("Colour of Parts", {
	colour_of_parts_add(frm, cdt, cdn) {
		const parts = frm.doc.colour_of_parts || [];
		const row = frappe.get_doc(cdt, cdn);
		const part_num = parts.length;
		frappe.model.set_value(cdt, cdn, "part_number", part_num);
		update_paper_type_and_gsm(frm, row, part_num, parts.length);
		frm.refresh_field("colour_of_parts");
	},

	paper_type(frm, cdt, cdn) {
		const row = frappe.get_doc(cdt, cdn);
		const gsm = GSM_BY_PAPER_TYPE[row.paper_type];
		if (gsm !== undefined) {
			frappe.model.set_value(cdt, cdn, "gsm", gsm);
		}
	},

	colour_of_parts_remove(frm) {
		renumber_parts(frm);
	},
});

frappe.ui.form.on("Spot Colour", {
	spot_colours_add(frm) {
		recalculate_number_of_colours(frm);
	},
	spot_colours_remove(frm) {
		recalculate_number_of_colours(frm);
	},
	hex_preview(frm, cdt, cdn) {
		// When designer edits hex directly, offer nearest-Pantone lookup.
		const row = locals[cdt][cdn];
		if (!row.hex_preview) return;
		// Only prompt if pantone_code is not set yet — avoids nagging on every edit.
		if (row.pantone_code) return;
		open_nearest_pantone_dialog(frm, cdt, cdn);
	},
});

// Grid row button: "Find Pantone" on spot colours.
frappe.ui.form.on("Customer Product Specification", {
	onload(frm) {
		if (frm.fields_dict.spot_colours) {
			frm.fields_dict.spot_colours.grid.add_custom_button(__("Find Pantone from Hex"), () => {
				const selected = frm.fields_dict.spot_colours.grid.get_selected_children();
				const row = selected.length ? selected[0] : (frm.doc.spot_colours || [])[0];
				if (!row) {
					frappe.msgprint(__("Add a spot colour row first."));
					return;
				}
				open_nearest_pantone_dialog(frm, row.doctype, row.name);
			});
		}
	},
});

// ════════════════════════════════════════════════════════════════════
// Board Plan
// Moved here from the live Client Script "CPS — Board Plan" so the app owns the
// code. Kept as a self-contained IIFE: the file already registers several
// frappe.ui.form.on blocks, and the wrapper keeps these helpers out of the
// module scope shared with job_card_carton.js (which uses the same VCL_COLORS
// and VCL_JOINT_CONFIG names).
//
// The window guard means it is safe for the old Client Script to still exist
// while this deploys — only one copy registers. DELETE the Client Script
// "CPS — Board Plan" once this is live, or the code has two sources of truth.
// ════════════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════════════
// CPS — Board Plan
// Ports the Board Plan from Job Card Carton onto Customer Product
// Specification, and adds an assembled-box view alongside the flat blank.
//
// Source of truth for the maths:
//   production_log/job_card_tracking/doctype/job_card_carton/job_card_carton.js
//   (vcl_autofill_flap_serial / vcl_calc_board_sizes_serial /
//    vcl_calc_approx_weight_serial / vcl_render_board_visualization)
//
// TWO differences from the Job Card, both deliberate:
//   1. CPS holds the carton style in `product_type_carton`. On CPS,
//      `product_type` is the top-level Carton/Label/ETR discriminator.
//   2. Trim is fixed at 10 mm per outer edge. Knife gap, max reel width and
//      the UPS forecast stay on the Job Card — they are machine-floor calls.
//
// Submitted specs: set_value cannot write to a submitted document, so the
// numbers are always computed and always rendered into the HTML block, but
// only persisted while docstatus == 0.
// ═══════════════════════════════════════════════════════════════════════

(function () {
	if (window.__VCL_CPS_BOARD_PLAN__) return;
	window.__VCL_CPS_BOARD_PLAN__ = true;

	const VCL_COLORS = {
		primary: "#2B3990", fold: "#FF6B35", glue: "#4CAF50",
		stitch: "#D32F2F", cut: "#333333", face: "#C5CAE9",
		side: "#9FA8DA", top: "#7986CB", base: "#B39DDB", trayWall: "#81C784",
	};

	const VCL_JOINT_CONFIG = {
		"Gluing - Manual":  { tabWidth: 30, label: "Glue Tab",    color: "#4CAF5040", markerType: "glue" },
		"Gluing - Machine": { tabWidth: 30, label: "Glue Tab",    color: "#4CAF5040", markerType: "glue" },
		"Stitched":         { tabWidth: 40, label: "Stitch Flap", color: "#D32F2F30", markerType: "stitch" },
	};

	const TRIM_PER_EDGE = 10; // mm, per outer edge — 20 mm total per axis

	// ───────────────────────────────────────────────────────────────────
	// Pure computation. Mirrored verbatim in the print-format Jinja.
	// ───────────────────────────────────────────────────────────────────

	function cps_compute_board_plan(doc, flap_override) {
		const pt = doc.product_type_carton || "";
		const ply = doc.ply || "";
		const L = doc.ctn_length_mm || 0;
		const W = doc.ctn_width_mm || 0;
		const H = doc.ctn_height_mm || 0;

		const joint = VCL_JOINT_CONFIG[doc.joint_type] || VCL_JOINT_CONFIG["Stitched"];
		const tabWidth = joint.tabWidth;

		const out = {
			ok: false, reason: "", pt: pt, ply: ply,
			L: L, W: W, H: H, joint: joint, tabWidth: tabWidth,
			flap: 0, blank_width: 0, blank_length: 0,
			planned_width: 0, planned_length: 0,
			actual_width: 0, actual_length: 0,
			total_gsm: 0, weight_g: 0, trim: TRIM_PER_EDGE,
		};

		if ((doc.product_type || "") !== "Carton") { out.reason = "not-carton"; return out; }
		if (ply === "SFK") { out.reason = "sfk"; return out; }
		if (pt === "Die Cut") { out.reason = "die-cut"; return out; }
		if (!pt) { out.reason = "no-product-type"; return out; }

		// Flap = ceil((W + 5) / 2), unless manually overridden
		out.flap = (flap_override != null && flap_override > 0)
			? flap_override
			: (W > 0 ? Math.ceil((W + 5) / 2) : 0);

		const needsFlap = (pt !== "Tray");
		if (L <= 0 || W <= 0 || (needsFlap && (H <= 0 || out.flap <= 0))) {
			out.reason = "incomplete-dimensions";
			return out;
		}

		if (pt === "Tray") {
			out.blank_width = W + 2 * H;
			out.blank_length = L + 2 * H;
		} else if (pt === "1 Flap RSC") {
			out.blank_width = H + out.flap;
			out.blank_length = (2 * L) + (2 * W) + tabWidth;
		} else {
			// 2 Flap RSC, 3 Flap RSC, and default
			out.blank_width = out.flap + H + out.flap;
			out.blank_length = (2 * L) + (2 * W) + tabWidth;
		}

		out.planned_width = out.blank_width + (2 * TRIM_PER_EDGE);
		out.planned_length = out.blank_length + (2 * TRIM_PER_EDGE);
		out.actual_width = out.blank_width;
		out.actual_length = out.blank_length;

		// Total GSM — plies 1 and 2 always, ply 3 when 3 or 5, plies 4+5 when 5
		let gsm = (doc["1_ply_top_layer_gsm"] || 0) + (doc["2_ply_fluting_gsm"] || 0);
		if (ply === "3" || ply === "5") gsm += doc["3_ply_bottom_gsm"] || 0;
		if (ply === "5") gsm += (doc["4_ply_fluting_gsm"] || 0) + (doc["5_ply_fluting_gsm"] || 0);
		out.total_gsm = gsm;

		out.weight_g = ((out.planned_width * out.planned_length) / 1000000) * gsm;
		out.ok = true;
		return out;
	}

	// ───────────────────────────────────────────────────────────────────
	// Flat blank — ported from Job Card Carton
	// ───────────────────────────────────────────────────────────────────

	function cps_svg_rsc(L, W, H, flap, joint, oneFlap) {
		const tabWidth = joint.tabWidth;
		const totalW = tabWidth + L + W + L + W;
		const totalH = oneFlap ? (H + flap) : (flap + H + flap);
		if (totalW <= 0 || totalH <= 0) return "";

		const scale = Math.min(0.42, 560 / totalW, 300 / totalH);
		const ox = 32, oy = 42;
		const svgW = totalW * scale + 74;
		const svgH = totalH * scale + 90; // room for the dimension row + blank caption
		const bodyY = oneFlap ? 0 : flap;

		let svg = '<svg width="' + svgW + '" height="' + svgH + '" viewBox="0 0 ' + svgW + ' ' + svgH
			+ '" style="background:#FAFAFA;border:1px solid #ddd;border-radius:4px;max-width:100%;">';

		// Panel width L is a Front/Back face; panel width W is a Side face.
		// (Job Card Carton has these two labels transposed — see job_card_carton.js.)
		const panels = [
			{ label: joint.label, x: 0, y: bodyY, w: tabWidth, h: H, color: joint.color },
			{ label: "Front (" + L + "mm)", x: tabWidth, y: bodyY, w: L, h: H, color: VCL_COLORS.face + "80" },
			{ label: "Side (" + W + "mm)", x: tabWidth + L, y: bodyY, w: W, h: H, color: VCL_COLORS.side + "60" },
			{ label: "Back (" + L + "mm)", x: tabWidth + L + W, y: bodyY, w: L, h: H, color: VCL_COLORS.face + "80" },
			{ label: "Side (" + W + "mm)", x: tabWidth + L + W + L, y: bodyY, w: W, h: H, color: VCL_COLORS.side + "60" },
		];

		const xPositions = [tabWidth, tabWidth + L, tabWidth + L + W, tabWidth + L + W + L];
		const widths = [L, W, L, W];
		const flapColors = [VCL_COLORS.top + "35", VCL_COLORS.top + "50", VCL_COLORS.top + "35", VCL_COLORS.top + "50"];
		const allPanels = panels.slice();
		for (let i = 0; i < xPositions.length; i++) {
			if (!oneFlap) {
				allPanels.push({ x: xPositions[i], y: 0, w: widths[i], h: flap, color: flapColors[i], label: "Flap" });
			}
			allPanels.push({ x: xPositions[i], y: bodyY + H, w: widths[i], h: flap, color: flapColors[i], label: "Flap" });
		}

		for (let i = 0; i < allPanels.length; i++) {
			const p = allPanels[i];
			svg += '<rect x="' + (ox + p.x * scale) + '" y="' + (oy + p.y * scale)
				+ '" width="' + (p.w * scale) + '" height="' + (p.h * scale)
				+ '" fill="' + p.color + '" stroke="' + VCL_COLORS.cut + '" stroke-width="1.5"/>';
			if (p.w * scale > 36 && p.h * scale > 12) {
				const fontSize = Math.min(11, p.w * scale * 0.13);
				svg += '<text x="' + (ox + (p.x + p.w / 2) * scale)
					+ '" y="' + (oy + (p.y + p.h / 2) * scale)
					+ '" text-anchor="middle" dominant-baseline="middle" font-size="' + fontSize
					+ '" fill="#333" font-weight="500">' + p.label + "</text>";
			}
		}

		// Vertical fold lines
		for (let i = 0; i < xPositions.length; i++) {
			svg += '<line x1="' + (ox + xPositions[i] * scale) + '" y1="' + oy
				+ '" x2="' + (ox + xPositions[i] * scale) + '" y2="' + (oy + totalH * scale)
				+ '" stroke="' + VCL_COLORS.fold + '" stroke-width="1.5" stroke-dasharray="6,4"/>';
		}
		// Horizontal fold lines at the body boundaries
		const foldYs = oneFlap ? [H] : [flap, flap + H];
		for (let i = 0; i < foldYs.length; i++) {
			svg += '<line x1="' + (ox + tabWidth * scale) + '" y1="' + (oy + foldYs[i] * scale)
				+ '" x2="' + (ox + totalW * scale) + '" y2="' + (oy + foldYs[i] * scale)
				+ '" stroke="' + VCL_COLORS.fold + '" stroke-width="1" stroke-dasharray="4,3"/>';
		}

		if (oneFlap) {
			svg += '<text x="' + (ox + (totalW / 2) * scale) + '" y="' + (oy - 12)
				+ '" text-anchor="middle" font-size="9" fill="#999" font-style="italic">Open end (no flap)</text>';
		}

		// Joint markers on the tab
		if (joint.markerType === "stitch") {
			const spacing = 25;
			const count = Math.floor(H / spacing);
			const startY = (H - count * spacing) / 2;
			for (let i = 0; i <= count; i++) {
				const cy = oy + (bodyY + startY + i * spacing) * scale;
				const cx = ox + (tabWidth * 0.6) * scale;
				svg += '<line x1="' + (cx - 3) + '" y1="' + (cy - 3) + '" x2="' + (cx + 3) + '" y2="' + (cy + 3)
					+ '" stroke="' + VCL_COLORS.stitch + '" stroke-width="1.5"/>';
				svg += '<line x1="' + (cx + 3) + '" y1="' + (cy - 3) + '" x2="' + (cx - 3) + '" y2="' + (cy + 3)
					+ '" stroke="' + VCL_COLORS.stitch + '" stroke-width="1.5"/>';
			}
		} else {
			const fracs = [0.25, 0.5, 0.75];
			for (let i = 0; i < fracs.length; i++) {
				const gy = oy + (bodyY + H * fracs[i]) * scale;
				svg += '<line x1="' + (ox + (tabWidth * 0.2) * scale) + '" y1="' + gy
					+ '" x2="' + (ox + (tabWidth * 0.8) * scale) + '" y2="' + gy
					+ '" stroke="' + VCL_COLORS.glue + '" stroke-width="2" stroke-dasharray="3,2" opacity="0.6"/>';
			}
		}

		// Dimension callouts
		svg += '<text x="' + (ox + (tabWidth + L / 2) * scale) + '" y="' + (oy + totalH * scale + 14)
			+ '" text-anchor="middle" font-size="10" fill="#666">' + L + "mm</text>";
		svg += '<text x="' + (ox + (tabWidth + L + W / 2) * scale) + '" y="' + (oy + totalH * scale + 14)
			+ '" text-anchor="middle" font-size="10" fill="#666">' + W + "mm</text>";
		svg += '<text x="' + (ox + totalW * scale + 6) + '" y="' + (oy + (bodyY + H / 2) * scale)
			+ '" text-anchor="start" dominant-baseline="middle" font-size="10" fill="#666">' + H + "mm</text>";
		svg += '<text x="' + (ox + totalW * scale + 6) + '" y="' + (oy + (bodyY + H + flap / 2) * scale)
			+ '" text-anchor="start" dominant-baseline="middle" font-size="10" fill="#666">' + flap + "mm</text>";
		svg += '<text x="' + (ox + (tabWidth / 2) * scale) + '" y="' + (oy - 8)
			+ '" text-anchor="middle" font-size="9" fill="#888">' + tabWidth + "mm</text>";

		svg += '<line x1="' + ox + '" y1="' + (oy + totalH * scale + 24)
			+ '" x2="' + (ox + totalW * scale) + '" y2="' + (oy + totalH * scale + 24)
			+ '" stroke="#999" stroke-width="0.5"/>';
		svg += '<text x="' + (ox + (totalW / 2) * scale) + '" y="' + (oy + totalH * scale + 38)
			+ '" text-anchor="middle" font-size="11" fill="' + VCL_COLORS.primary
			+ '" font-weight="600">Blank: ' + totalH + " (W) x " + totalW + " (L) mm</text>";

		svg += "</svg>";
		return svg;
	}

	function cps_svg_tray_blank(L, W, H) {
		const totalW = H + W + H;
		const totalH = H + L + H;
		if (totalW <= 0 || totalH <= 0) return "";

		const scale = Math.min(0.55, 420 / totalW, 300 / totalH);
		const ox = 30, oy = 30;
		const svgW = totalW * scale + 60;
		const svgH = totalH * scale + 76; // room for the blank caption

		let svg = '<svg width="' + svgW + '" height="' + svgH + '" viewBox="0 0 ' + svgW + ' ' + svgH
			+ '" style="background:#FAFAFA;border:1px solid #ddd;border-radius:4px;max-width:100%;">';

		const ears = [
			{ x: 0, y: 0 }, { x: H + W, y: 0 }, { x: 0, y: H + L }, { x: H + W, y: H + L },
		];
		for (let i = 0; i < ears.length; i++) {
			const sx = ox + ears[i].x * scale, sy = oy + ears[i].y * scale;
			const sw = H * scale, sh = H * scale;
			let points;
			if (i === 0) points = sx + "," + (sy + sh) + " " + (sx + sw) + "," + sy + " " + (sx + sw) + "," + (sy + sh);
			else if (i === 1) points = sx + "," + sy + " " + (sx + sw) + "," + (sy + sh) + " " + sx + "," + (sy + sh);
			else if (i === 2) points = (sx + sw) + "," + sy + " " + sx + "," + (sy + sh) + " " + (sx + sw) + "," + (sy + sh);
			else points = sx + "," + sy + " " + (sx + sw) + "," + sy + " " + sx + "," + (sy + sh);
			svg += '<polygon points="' + points + '" fill="#E0E0E0" stroke="' + VCL_COLORS.cut
				+ '" stroke-width="1" stroke-dasharray="3,3"/>';
		}

		const panels = [
			{ x: H, y: H, w: W, h: L, color: VCL_COLORS.base + "50", label: "Base (" + L + " x " + W + ")" },
			{ x: H, y: 0, w: W, h: H, color: VCL_COLORS.trayWall + "50", label: "Front" },
			{ x: H, y: H + L, w: W, h: H, color: VCL_COLORS.trayWall + "50", label: "Back" },
			{ x: 0, y: H, w: H, h: L, color: VCL_COLORS.trayWall + "35", label: "Side" },
			{ x: H + W, y: H, w: H, h: L, color: VCL_COLORS.trayWall + "35", label: "Side" },
		];
		for (let i = 0; i < panels.length; i++) {
			const p = panels[i];
			svg += '<rect x="' + (ox + p.x * scale) + '" y="' + (oy + p.y * scale)
				+ '" width="' + (p.w * scale) + '" height="' + (p.h * scale)
				+ '" fill="' + p.color + '" stroke="' + VCL_COLORS.cut + '" stroke-width="1.5"/>';
			if (p.w * scale > 46 && p.h * scale > 18) {
				svg += '<text x="' + (ox + (p.x + p.w / 2) * scale) + '" y="' + (oy + (p.y + p.h / 2) * scale)
					+ '" text-anchor="middle" dominant-baseline="middle" font-size="10" fill="#333" font-weight="500">'
					+ p.label + "</text>";
			}
		}

		const vx = [H, H + W], hy = [H, H + L];
		for (let i = 0; i < 2; i++) {
			svg += '<line x1="' + (ox + vx[i] * scale) + '" y1="' + oy + '" x2="' + (ox + vx[i] * scale)
				+ '" y2="' + (oy + totalH * scale) + '" stroke="' + VCL_COLORS.fold
				+ '" stroke-width="1.5" stroke-dasharray="6,4"/>';
			svg += '<line x1="' + ox + '" y1="' + (oy + hy[i] * scale) + '" x2="' + (ox + totalW * scale)
				+ '" y2="' + (oy + hy[i] * scale) + '" stroke="' + VCL_COLORS.fold
				+ '" stroke-width="1.5" stroke-dasharray="6,4"/>';
		}

		svg += '<text x="' + (ox + (totalW / 2) * scale) + '" y="' + (oy + totalH * scale + 34)
			+ '" text-anchor="middle" font-size="11" fill="' + VCL_COLORS.primary
			+ '" font-weight="600">Blank: ' + totalW + " (W) x " + totalH + " (L) mm</text>";
		svg += "</svg>";
		return svg;
	}

	// ───────────────────────────────────────────────────────────────────
	// Assembled box — new. Cabinet projection, depth to the upper right.
	// openTop = true for 1 Flap RSC and Tray (no top closure).
	// ───────────────────────────────────────────────────────────────────

	function cps_svg_assembled_box(L, W, H, openTop, caption) {
		if (L <= 0 || W <= 0 || H <= 0) return "";

		const DX = 0.50, DY = 0.30; // depth foreshortening
		const raw_w = L + W * DX;
		const raw_h = H + W * DY;
		const scale = Math.min(0.42, 300 / raw_w, 250 / raw_h);

		const l = L * scale, h = H * scale;
		const dx = W * scale * DX, dy = W * scale * DY;

		// Left margin clears the "H 000mm" callout (anchored end), right margin the "W 000mm"
		const ox = 52, oy = 26 + dy;
		const svgW = l + dx + 110;
		const svgH = h + dy + 66;

		let svg = '<svg width="' + svgW + '" height="' + svgH + '" viewBox="0 0 ' + svgW + ' ' + svgH
			+ '" style="background:#FAFAFA;border:1px solid #ddd;border-radius:4px;max-width:100%;">';

		const stroke = VCL_COLORS.cut;
		// Front face corners
		const fx = ox, fy = oy;

		if (openTop) {
			// Inner cavity floor, drawn first so the walls overlap it
			const inset = Math.max(2, Math.min(l, dx) * 0.06);
			svg += '<polygon points="'
				+ (fx + inset) + "," + (fy + inset * DY / DX) + " "
				+ (fx + l - inset) + "," + (fy + inset * DY / DX) + " "
				+ (fx + l - inset + dx) + "," + (fy - dy + inset * DY / DX) + " "
				+ (fx + inset + dx) + "," + (fy - dy + inset * DY / DX)
				+ '" fill="#8E96C8" opacity="0.55" stroke="' + stroke + '" stroke-width="0.8"/>';
		} else {
			// Top face
			svg += '<polygon points="'
				+ fx + "," + fy + " " + (fx + l) + "," + fy + " "
				+ (fx + l + dx) + "," + (fy - dy) + " " + (fx + dx) + "," + (fy - dy)
				+ '" fill="' + VCL_COLORS.top + '80" stroke="' + stroke + '" stroke-width="1.6"/>';
		}

		// Right face (depth = W)
		svg += '<polygon points="'
			+ (fx + l) + "," + fy + " " + (fx + l + dx) + "," + (fy - dy) + " "
			+ (fx + l + dx) + "," + (fy - dy + h) + " " + (fx + l) + "," + (fy + h)
			+ '" fill="' + VCL_COLORS.side + '90" stroke="' + stroke + '" stroke-width="1.6"/>';

		// Front face (L x H)
		svg += '<rect x="' + fx + '" y="' + fy + '" width="' + l + '" height="' + h
			+ '" fill="' + VCL_COLORS.face + 'CC" stroke="' + stroke + '" stroke-width="1.8"/>';

		if (openTop) {
			// Rim thickness on the two visible top edges
			svg += '<line x1="' + fx + '" y1="' + fy + '" x2="' + (fx + dx) + '" y2="' + (fy - dy)
				+ '" stroke="' + stroke + '" stroke-width="1.6"/>';
			svg += '<line x1="' + (fx + dx) + '" y1="' + (fy - dy) + '" x2="' + (fx + l + dx) + '" y2="' + (fy - dy)
				+ '" stroke="' + stroke + '" stroke-width="1.6"/>';
			svg += '<text x="' + (fx + l / 2 + dx * 0.5) + '" y="' + (fy - dy - 8)
				+ '" text-anchor="middle" font-size="9" fill="#999" font-style="italic">Open top</text>';
		}

		// Face labels
		svg += '<text x="' + (fx + l / 2) + '" y="' + (fy + h / 2)
			+ '" text-anchor="middle" dominant-baseline="middle" font-size="10" fill="#333" font-weight="500">'
			+ L + " x " + H + "</text>";
		// Dimension callouts
		svg += '<text x="' + (fx + l / 2) + '" y="' + (fy + h + 16)
			+ '" text-anchor="middle" font-size="10" fill="#666">L ' + L + "mm</text>";
		svg += '<text x="' + (fx - 8) + '" y="' + (fy + h / 2)
			+ '" text-anchor="end" dominant-baseline="middle" font-size="10" fill="#666">H ' + H + "mm</text>";
		// W is the receding depth. Dimension it on the top-LEFT receding edge: that
		// edge is on the silhouette, so the callout sits outside the solid. Placed at
		// the right it landed beside the right face's vertical edge and read as the
		// height. Angle is constant — atan(DY/DX) = 31° — so it can be hardcoded.
		const nlen = Math.sqrt(dx * dx + dy * dy) || 1;
		const nx = -dy / nlen, ny = -dx / nlen;
		const k = 12;
		svg += '<line x1="' + (fx + k * nx) + '" y1="' + (fy + k * ny)
			+ '" x2="' + (fx + dx + k * nx) + '" y2="' + (fy - dy + k * ny)
			+ '" stroke="#999" stroke-width="0.7"/>';
		svg += '<line x1="' + fx + '" y1="' + fy + '" x2="' + (fx + k * nx) + '" y2="' + (fy + k * ny)
			+ '" stroke="#999" stroke-width="0.6"/>';
		svg += '<line x1="' + (fx + dx) + '" y1="' + (fy - dy) + '" x2="' + (fx + dx + k * nx)
			+ '" y2="' + (fy - dy + k * ny) + '" stroke="#999" stroke-width="0.6"/>';
		const wlx = fx + dx / 2 + (k + 9) * nx;
		const wly = fy - dy / 2 + (k + 9) * ny;
		svg += '<text x="' + wlx + '" y="' + wly + '" text-anchor="middle" dominant-baseline="middle"'
			+ ' font-size="10" fill="#666" transform="rotate(-31, ' + wlx + ', ' + wly + ')">W ' + W + "mm</text>";

		svg += '<text x="' + ((l + dx) / 2 + ox) + '" y="' + (svgH - 10)
			+ '" text-anchor="middle" font-size="11" fill="' + VCL_COLORS.primary + '" font-weight="600">'
			+ (caption || "Assembled") + "</text>";

		svg += "</svg>";
		return svg;
	}

	// ───────────────────────────────────────────────────────────────────
	// Rendering
	// ───────────────────────────────────────────────────────────────────

	function note(msg, tone) {
		const bg = tone === "warn" ? "#FFF8E1" : "#FAFAFA";
		const bar = tone === "warn" ? "#FFA000" : "#ddd";
		return '<div style="padding:12px 16px;background:' + bg + ';border-left:3px solid ' + bar
			+ ';border-radius:4px;color:#666;font-size:13px;font-style:italic;margin:8px 0;">' + msg + "</div>";
	}

	function cps_render_board_plan(frm) {
		const fd = frm.fields_dict["html_board_visualization"];
		if (!fd || !fd.$wrapper) return;
		const $w = fd.$wrapper;

		const r = cps_compute_board_plan(frm.doc, frm.__cps_flap_override ? frm.doc.ctn_flap_mm : null);

		if (!r.ok) {
			const messages = {
				"not-carton": "",
				"sfk": note("Board plan is not applicable for SFK ply — the web is run un-glued."),
				"die-cut": note('<b style="color:#E65100;">Die Cut</b> — blank layout not available. Custom die shapes vary per job.', "warn"),
				"no-product-type": note("Select a carton product type to see the blank layout."),
				"incomplete-dimensions": note("Enter carton dimensions to see the blank layout."),
			};
			$w.html(messages[r.reason] != null ? messages[r.reason] : "");
			return;
		}

		const isTray = (r.pt === "Tray");
		const oneFlap = (r.pt === "1 Flap RSC");
		const flat = isTray
			? cps_svg_tray_blank(r.L, r.W, r.H)
			: cps_svg_rsc(r.L, r.W, r.H, r.flap, r.joint, oneFlap);
		const solid = cps_svg_assembled_box(
			r.L, r.W, r.H, (isTray || oneFlap),
			isTray ? "Assembled tray" : (oneFlap ? "Assembled — top open" : "Assembled — closed")
		);

		const legend = isTray
			? '<span><span style="display:inline-block;width:20px;border-top:2px dashed ' + VCL_COLORS.fold + ';margin-right:4px;vertical-align:middle;"></span> Fold line</span>'
				+ '<span><span style="display:inline-block;width:14px;height:14px;background:' + VCL_COLORS.base + '50;border:1px solid #999;margin-right:4px;vertical-align:middle;"></span> Base</span>'
				+ '<span><span style="display:inline-block;width:14px;height:14px;background:' + VCL_COLORS.trayWall + '50;border:1px solid #999;margin-right:4px;vertical-align:middle;"></span> Walls</span>'
				+ '<span><span style="display:inline-block;width:14px;height:14px;background:#E0E0E0;border:1px solid #999;margin-right:4px;vertical-align:middle;"></span> Corner tabs</span>'
			: '<span><span style="display:inline-block;width:20px;border-top:2px dashed ' + VCL_COLORS.fold + ';margin-right:4px;vertical-align:middle;"></span> Fold line</span>'
				+ '<span><span style="display:inline-block;width:14px;height:14px;background:' + VCL_COLORS.face + '80;border:1px solid #999;margin-right:4px;vertical-align:middle;"></span> Front/Back</span>'
				+ '<span><span style="display:inline-block;width:14px;height:14px;background:' + VCL_COLORS.side + '60;border:1px solid #999;margin-right:4px;vertical-align:middle;"></span> Side</span>'
				+ '<span><span style="display:inline-block;width:14px;height:14px;background:' + VCL_COLORS.top + '50;border:1px solid #999;margin-right:4px;vertical-align:middle;"></span> Flaps</span>'
				+ (r.joint.markerType === "stitch"
					? '<span><span style="color:' + VCL_COLORS.stitch + ';font-weight:700;margin-right:4px;">X</span> Stitch marks</span>'
					: '<span><span style="display:inline-block;width:20px;border-top:2px dashed ' + VCL_COLORS.glue + ';margin-right:4px;vertical-align:middle;"></span> Glue lines</span>');

		let html = '<div style="margin:8px 0 4px;">';
		html += '<div style="display:flex;gap:18px;flex-wrap:wrap;align-items:flex-start;">'
			+ '<div>' + flat + '</div><div>' + solid + '</div></div>';
		html += '<div style="margin-top:8px;display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:#666;">'
			+ legend + "</div>";

		// Always show the computed numbers — a submitted spec cannot store them
		const stored = (frm.doc.docstatus === 0);
		html += '<table style="margin-top:12px;border-collapse:collapse;font-size:12.5px;background:#fff;border:1px solid #ddd;min-width:420px;">'
			+ '<thead style="background:' + VCL_COLORS.primary + ';color:#fff;">'
			+ '<tr><th style="padding:5px 10px;text-align:left;">Board</th>'
			+ '<th style="padding:5px 10px;text-align:right;">Blank</th>'
			+ '<th style="padding:5px 10px;text-align:right;">Planned (+' + (2 * r.trim) + 'mm trim)</th></tr></thead><tbody>'
			+ '<tr><td style="padding:5px 10px;">Width</td><td style="padding:5px 10px;text-align:right;">' + r.blank_width
			+ '</td><td style="padding:5px 10px;text-align:right;font-weight:600;">' + r.planned_width + '</td></tr>'
			+ '<tr style="background:#FAFAFA;"><td style="padding:5px 10px;">Length</td><td style="padding:5px 10px;text-align:right;">' + r.blank_length
			+ '</td><td style="padding:5px 10px;text-align:right;font-weight:600;">' + r.planned_length + '</td></tr>'
			+ '<tr><td style="padding:5px 10px;">Carton flap</td><td style="padding:5px 10px;text-align:right;">' + r.flap
			+ '</td><td style="padding:5px 10px;text-align:right;color:#999;">&mdash;</td></tr>'
			+ '<tr style="background:#FAFAFA;"><td style="padding:5px 10px;">Approx. weight</td><td style="padding:5px 10px;text-align:right;">' + r.total_gsm
			+ ' gsm</td><td style="padding:5px 10px;text-align:right;font-weight:600;">' + r.weight_g.toFixed(1) + ' g</td></tr>'
			+ "</tbody></table>";

		if (!stored) {
			html += '<div style="margin-top:6px;font-size:11px;color:#888;font-style:italic;">'
				+ "Computed at display time — this specification is submitted, so the values above are not stored on it. "
				+ "Revise the spec to persist them."
				+ "</div>";
		}
		html += "</div>";
		$w.html(html);
	}

	function cps_board_plan_pipeline(frm) {
		const r = cps_compute_board_plan(frm.doc, frm.__cps_flap_override ? frm.doc.ctn_flap_mm : null);

		if (frm.doc.docstatus === 0 && !frm.__cps_calc_in_progress) {
			frm.__cps_calc_in_progress = true;
			try {
				if (!frm.__cps_flap_override && (frm.doc.ctn_flap_mm || 0) !== r.flap) {
					frm.set_value("ctn_flap_mm", r.flap);
				}
				if ((frm.doc.board_width_planned_mm || 0) !== r.planned_width) {
					frm.set_value("board_width_planned_mm", r.planned_width);
				}
				if ((frm.doc.board_length_planned_mm || 0) !== r.planned_length) {
					frm.set_value("board_length_planned_mm", r.planned_length);
				}
				if (!frm.__cps_width_override && (frm.doc.board_width_actual_mm || 0) !== r.actual_width) {
					frm.set_value("board_width_actual_mm", r.actual_width);
				}
				if (!frm.__cps_length_override && (frm.doc.board_length_actual_mm || 0) !== r.actual_length) {
					frm.set_value("board_length_actual_mm", r.actual_length);
				}
				const wg = flt(r.weight_g, 2);
				if (flt(frm.doc.approximate_weight_grams, 2) !== wg) {
					frm.set_value("approximate_weight_grams", wg);
				}
			} finally {
				frm.__cps_calc_in_progress = false;
			}
		}

		cps_render_board_plan(frm);
	}

	const RECALC_FIELDS = [
		"product_type", "product_type_carton", "joint_type", "ply",
		"ctn_length_mm", "ctn_width_mm", "ctn_height_mm",
		"1_ply_top_layer_gsm", "2_ply_fluting_gsm", "3_ply_bottom_gsm",
		"4_ply_fluting_gsm", "5_ply_fluting_gsm",
	];

	const handlers = {
		refresh(frm) {
			if (!frm.doc.ctn_flap_mm) frm.__cps_flap_override = false;
			if (!frm.doc.board_width_actual_mm) frm.__cps_width_override = false;
			if (!frm.doc.board_length_actual_mm) frm.__cps_length_override = false;
			setTimeout(() => cps_board_plan_pipeline(frm), 60);
		},
		onload_post_render(frm) {
			setTimeout(() => cps_board_plan_pipeline(frm), 60);
		},
		ctn_flap_mm(frm) {
			if (frm.__cps_calc_in_progress) return;
			frm.__cps_flap_override = !!frm.doc.ctn_flap_mm;
			cps_board_plan_pipeline(frm);
		},
		board_width_actual_mm(frm) {
			if (frm.__cps_calc_in_progress) return;
			frm.__cps_width_override = true;
		},
		board_length_actual_mm(frm) {
			if (frm.__cps_calc_in_progress) return;
			frm.__cps_length_override = true;
		},
	};
	RECALC_FIELDS.forEach((f) => {
		handlers[f] = function (frm) {
			if (frm.__cps_calc_in_progress) return;
			setTimeout(() => cps_board_plan_pipeline(frm), 40);
		};
	});

	frappe.ui.form.on("Customer Product Specification", handlers);
})();
