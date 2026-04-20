// Copyright (c) 2026, VCL and contributors
// For license information, please see license.txt

const NAMING_SERIES_MAP = {
	"Computer Paper": "CPT-SPEC-.#####",
	"Carton":         "CTN-SPEC-.#####",
	"Label":          "LBL-SPEC-.#####",
	"Exercise Books": "EXB-SPEC-.#####",
};

const INK_TYPE_DEFAULTS = {
	"Computer Paper": "Process Offset",
	"Carton":         "Process Offset",
	"Label":          "Process UV",
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

// Grid row button: "Find Pantone" — always available on each spot colour row.
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
