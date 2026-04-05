// Copyright (c) 2026, VCL and contributors
// For license information, please see license.txt

const NAMING_SERIES_MAP = {
	"Computer Paper": "CPT-SPEC-.#####",
	"Carton": "CTN-SPEC-.#####",
	"Label": "LBL-SPEC-.#####",
	"Exercise Books": "EXB-SPEC-.#####",
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

function get_paper_rule(part_num, total_parts) {
	if (total_parts === 1) return PAPER_RULES.single;
	if (part_num === 1)            return PAPER_RULES.first;
	if (part_num === total_parts)  return PAPER_RULES.last;
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

	// Re-number and set paper type/GSM for all rows
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

frappe.ui.form.on("Customer Product Specification", {
	product_type(frm) {
		const series = NAMING_SERIES_MAP[frm.doc.product_type];
		if (series) {
			frm.set_value("naming_series", series);
		}
	},

	number_of_parts(frm) {
		if (frm.doc.product_type !== "Computer Paper") return;
		sync_colour_of_parts(frm);
	},

	dies(frm) {
		if (frm.doc.product_type !== "Label" || !frm.doc.dies) return;
		
		// Fetch the dies document and auto-populate fields
		frappe.call({
			method: "frappe.client.get",
			args: {
				doctype: "Dies",
				name: frm.doc.dies
			},
			callback: function(r) {
				if (r.message) {
					const dies_doc = r.message;
					
					// Auto-populate fields from Dies
					frm.set_value("label_length", dies_doc.length);
					frm.set_value("label_width", dies_doc.width);
					frm.set_value("cylinder_teeth", dies_doc.teeth);
					frm.set_value("plate_up", dies_doc.across_ups);
					frm.set_value("plate_round", dies_doc.round_ups);
					frm.set_value("packing_pieces", dies_doc.qty);
					
					// material_type must be selected manually as Dies.material doesn't map to Label finish types
				}
			}
		});
	},
});

frappe.ui.form.on("Colour of Parts", {
	colour_of_parts_add(frm, cdt, cdn) {
		const parts = frm.doc.colour_of_parts || [];
		const row = frappe.get_doc(cdt, cdn);
		const part_num = parts.length;
		const total = parts.length;
		frappe.model.set_value(cdt, cdn, "part_number", part_num);
		update_paper_type_and_gsm(frm, row, part_num, total);
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
