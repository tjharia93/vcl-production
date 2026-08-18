// Dies — Form Script
// Three read-only aids on the die master, all derived from fields already on
// the doc — nothing new is stored except the Die Name:
//   1. Die Name        — "L:70 W:45", kept in step with length/width.
//   2. Die Preview     — the single die shape, dimensioned, beside Basic Details.
//   3. Die Layout      — the full across × round layout on the cylinder repeat.
//
// Convention (read off the Label traveller, not invented): WIDTH runs across
// the web — approx reel width = label_width × plate_up — and LENGTH runs
// around the cylinder, so round ups stack down-web.

window.__VCL_DIES_VIZ__ = "bundled";

const VCL_DIE = {
	primary: "#2B3990",
	deep: "#00395D",
	face: "#E8EAF6",
	faceLine: "#5C6BC0",
	cut: "#333333",
	gap: "#FF6B35",
	muted: "#8A8F98",
	ok: "#2E7D32",
	err: "#C62828",
	// Gear tooth pitch: 1/8" = 3.175 mm. Repeat = teeth × pitch.
	pitch: 3.175,
};

frappe.ui.form.on("Dies", {
	refresh(frm) {
		vcl_die_sync_name(frm);
		vcl_render_die_preview(frm);
		vcl_render_die_layout(frm);
	},
	length(frm)     { vcl_die_redraw(frm); },
	width(frm)      { vcl_die_redraw(frm); },
	shape(frm)      { vcl_die_redraw(frm); },
	across_ups(frm) { vcl_die_sync_name(frm); vcl_render_die_layout(frm); },
	round_ups(frm)  { vcl_die_sync_name(frm); vcl_render_die_layout(frm); },
	teeth(frm)      { vcl_die_sync_name(frm); vcl_render_die_layout(frm); },
});

function vcl_die_redraw(frm) {
	vcl_die_sync_name(frm);
	vcl_render_die_preview(frm);
	vcl_render_die_layout(frm);
}

// ═══════════════════════════════════════════════════════════
// Die Name — derived label, "L:70 W:45"
// Assigned straight onto frm.doc so reading a die never dirties the form;
// the value still travels on the next save, and dies.py validate() is what
// makes it authoritative.
// ═══════════════════════════════════════════════════════════

function vcl_die_name(doc) {
	const L = flt(doc.length), W = flt(doc.width);
	const across = cint(doc.across_ups), round_ = cint(doc.round_ups);
	const teeth = flt(doc.teeth);
	const fmt = (v) => (Math.round(v * 100) / 100).toString();

	// Size alone does not identify a die — nine of them are 60 × 20, five are
	// 66 × 66. Ups and teeth are what tell two apart, so they belong in the
	// name. Parts that are not set drop out rather than reading "0".
	const parts = [];
	if (L > 0 || W > 0) parts.push("L" + fmt(L) + " W" + fmt(W));
	if (across > 0 && round_ > 0) parts.push(across + "×" + round_ + " up");
	else if (across > 0) parts.push(across + " up");
	else if (round_ > 0) parts.push(round_ + " round");
	if (teeth > 0) parts.push(fmt(teeth) + "T");
	return parts.join(" · ");
}

function vcl_die_sync_name(frm) {
	if (!frm.fields_dict.custom_die_name) return;
	const derived = vcl_die_name(frm.doc);
	if (frm.doc.custom_die_name === derived) return;
	if (frm.is_new() || frm.is_dirty()) {
		frm.set_value("custom_die_name", derived);
	} else {
		frm.doc.custom_die_name = derived;
		frm.refresh_field("custom_die_name");
	}
}

// ═══════════════════════════════════════════════════════════
// Shared drawing helpers
// ═══════════════════════════════════════════════════════════

function vcl_die_wrapper(frm, fieldname) {
	return frm.fields_dict[fieldname] ? frm.fields_dict[fieldname].$wrapper : null;
}

function vcl_die_hint(text) {
	return '<div style="padding:10px 2px;color:#888;font-size:12.5px;font-style:italic;">' + text + "</div>";
}

function vcl_die_note(text) {
	return '<div style="padding:10px 14px;background:#FFF8E1;border-left:3px solid #FFA000;'
		+ 'border-radius:3px;font-size:12.5px;color:#555;margin:6px 0;">' + text + "</div>";
}

function vcl_die_mm(v) {
	return (Math.round(v * 10) / 10).toFixed(1);
}

// One die outline, drawn to fill the box x,y,w,h. Shape-aware: what the
// operator sees should match what the die actually cuts.
function vcl_die_shape_svg(shape, x, y, w, h, strokeWidth) {
	const s = (shape || "").toUpperCase();
	const sw = strokeWidth || 1;
	const style = 'fill="' + VCL_DIE.face + '" stroke="' + VCL_DIE.faceLine + '" stroke-width="' + sw + '"';

	if (s === "CIRCLE" || s === "ROUND") {
		const r = Math.min(w, h) / 2;
		return '<circle cx="' + (x + w / 2) + '" cy="' + (y + h / 2) + '" r="' + r + '" ' + style + "/>";
	}
	if (s === "OVAL") {
		return '<ellipse cx="' + (x + w / 2) + '" cy="' + (y + h / 2) + '" rx="' + (w / 2)
			+ '" ry="' + (h / 2) + '" ' + style + "/>";
	}
	if (s === "SEMI CIRCLE") {
		return '<path d="M ' + x + " " + (y + h) + " A " + (w / 2) + " " + h + " 0 0 1 "
			+ (x + w) + " " + (y + h) + ' Z" ' + style + "/>";
	}
	if (s === "IRREGULAR") {
		// Shape unknown — a dashed envelope is honest; the real profile is on the artwork.
		return '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h
			+ '" rx="' + Math.min(6, w / 6) + '" fill="' + VCL_DIE.face + '" stroke="' + VCL_DIE.faceLine
			+ '" stroke-width="' + sw + '" stroke-dasharray="4,3"/>';
	}
	// SQUARE / RECTANGLE / anything else
	return '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h
		+ '" rx="1.5" ' + style + "/>";
}

// Horizontal dimension line with end ticks and a centred label below it.
function vcl_die_dim_h(x1, x2, y, label) {
	let s = "";
	s += '<line x1="' + x1 + '" y1="' + y + '" x2="' + x2 + '" y2="' + y
		+ '" stroke="' + VCL_DIE.deep + '" stroke-width="1"/>';
	[x1, x2].forEach(function (x) {
		s += '<line x1="' + x + '" y1="' + (y - 4) + '" x2="' + x + '" y2="' + (y + 4)
			+ '" stroke="' + VCL_DIE.deep + '" stroke-width="1"/>';
	});
	s += '<text x="' + ((x1 + x2) / 2) + '" y="' + (y + 15) + '" text-anchor="middle" font-size="11" '
		+ 'fill="' + VCL_DIE.deep + '" font-weight="600">' + label + "</text>";
	return s;
}

// Vertical dimension line with end ticks and a rotated label to its left.
function vcl_die_dim_v(x, y1, y2, label) {
	let s = "";
	s += '<line x1="' + x + '" y1="' + y1 + '" x2="' + x + '" y2="' + y2
		+ '" stroke="' + VCL_DIE.deep + '" stroke-width="1"/>';
	[y1, y2].forEach(function (y) {
		s += '<line x1="' + (x - 4) + '" y1="' + y + '" x2="' + (x + 4) + '" y2="' + y
			+ '" stroke="' + VCL_DIE.deep + '" stroke-width="1"/>';
	});
	const my = (y1 + y2) / 2;
	s += '<text x="' + (x - 8) + '" y="' + my + '" text-anchor="middle" font-size="11" '
		+ 'fill="' + VCL_DIE.deep + '" font-weight="600" transform="rotate(-90 ' + (x - 8) + " " + my + ')">'
		+ label + "</text>";
	return s;
}

// ═══════════════════════════════════════════════════════════
// 2. Die Preview — one die, dimensioned
// ═══════════════════════════════════════════════════════════

function vcl_render_die_preview(frm) {
	const $w = vcl_die_wrapper(frm, "custom_die_preview");
	if (!$w) return;

	const L = flt(frm.doc.length);
	const W = flt(frm.doc.width);
	if (!(L > 0) || !(W > 0)) {
		$w.html(vcl_die_hint("Enter Length and Width to see the die shape."));
		return;
	}

	const BOX = 190;                      // longest side, px
	const PAD_L = 40, PAD_R = 16, PAD_T = 14, PAD_B = 34;
	const scale = BOX / Math.max(L, W);
	const w = W * scale, h = L * scale;
	const ox = PAD_L, oy = PAD_T;
	const svgW = w + PAD_L + PAD_R, svgH = h + PAD_T + PAD_B;

	let svg = '<svg width="' + svgW + '" height="' + svgH + '" viewBox="0 0 ' + svgW + " " + svgH
		+ '" style="max-width:100%;height:auto;background:#FCFCFD;border:1px solid #E3E5E8;border-radius:4px;">';
	svg += vcl_die_shape_svg(frm.doc.shape, ox, oy, w, h, 1.4);
	svg += vcl_die_dim_h(ox, ox + w, oy + h + 14, "W " + vcl_die_mm(W) + " mm");
	svg += vcl_die_dim_v(ox - 14, oy, oy + h, "L " + vcl_die_mm(L) + " mm");
	svg += "</svg>";

	const shape = frm.doc.shape || "—";
	const entered = frm.doc.die_size || "";
	let meta = '<div style="font-size:11.5px;color:#666;margin-top:6px;line-height:1.5;">';
	meta += "<b>" + vcl_die_name(frm.doc) + "</b> &middot; " + shape;
	meta += '<br><span style="color:#8A8F98;">Length runs around the cylinder, width across the web.</span>';
	if (entered) {
		meta += '<br><span style="color:#8A8F98;">Die Size as entered: ' + frappe.utils.escape_html(entered) + "</span>";
	}
	meta += "</div>";

	$w.html('<div style="margin:2px 0 4px;">' + svg + meta + "</div>");
}

// ═══════════════════════════════════════════════════════════
// 3. Die Layout — the full cylinder repeat
//   across ups → lanes across the web (width each)
//   round ups  → rows around the cylinder (length each)
//   repeat     = teeth × 3.175 mm; the down-web gap is what is left over
// ═══════════════════════════════════════════════════════════

function vcl_render_die_layout(frm) {
	const $w = vcl_die_wrapper(frm, "custom_die_layout");
	if (!$w) return;

	const L = flt(frm.doc.length);
	const W = flt(frm.doc.width);
	const across = cint(frm.doc.across_ups);
	const round_ = cint(frm.doc.round_ups);
	const teeth = flt(frm.doc.teeth);

	if (!(L > 0) || !(W > 0)) {
		$w.html(vcl_die_hint("Enter the die Length and Width in Basic Details to see the layout."));
		return;
	}
	if (!(across > 0) || !(round_ > 0)) {
		$w.html(vcl_die_hint("Set Across Ups and Round Ups to see the full die layout."));
		return;
	}
	if (across * round_ > 1200) {
		$w.html(vcl_die_note("<b>" + (across * round_) + " ups</b> — too many to draw. Check Across Ups and Round Ups."));
		return;
	}

	const repeat = teeth > 0 ? teeth * VCL_DIE.pitch : 0;
	const contentW = across * W;
	const stackL = round_ * L;
	const pitchL = repeat > 0 ? repeat / round_ : L;
	const gapL = repeat > 0 ? pitchL - L : 0;
	const overflow = repeat > 0 && gapL < 0;
	// When the layout does not fit the repeat, draw it butted and say so —
	// a drawing that silently rescales would hide the problem.
	const drawPitch = overflow || repeat <= 0 ? L : pitchL;
	const totalL = overflow || repeat <= 0 ? stackL : repeat;

	const PAD_L = 46, PAD_R = 20, PAD_T = 20, PAD_B = 38;
	const scale = Math.min(820 / contentW, 460 / totalL, 8);
	const ox = PAD_L, oy = PAD_T;
	const bw = contentW * scale, bh = totalL * scale;
	const svgW = bw + PAD_L + PAD_R, svgH = bh + PAD_T + PAD_B;

	let svg = '<svg width="' + svgW + '" height="' + svgH + '" viewBox="0 0 ' + svgW + " " + svgH
		+ '" style="max-width:100%;height:auto;background:#FCFCFD;border:1px solid #E3E5E8;border-radius:4px;">';

	// Web envelope (side trim excluded — trim is set per job, not on the die).
	svg += '<rect x="' + ox + '" y="' + oy + '" width="' + bw + '" height="' + bh
		+ '" fill="#FFFFFF" stroke="' + VCL_DIE.muted + '" stroke-width="1" stroke-dasharray="4,3"/>';

	// Down-web gap bands between rows.
	if (gapL > 0.01 && !overflow) {
		for (let r = 0; r < round_; r++) {
			const gy = oy + (r * pitchL + L) * scale;
			svg += '<rect x="' + ox + '" y="' + gy + '" width="' + bw + '" height="' + (gapL * scale)
				+ '" fill="' + VCL_DIE.gap + '" opacity="0.14"/>';
		}
	}

	// The dies themselves.
	const cellW = W * scale, cellH = L * scale;
	const labelFirst = cellW >= 40 && cellH >= 18;
	for (let r = 0; r < round_; r++) {
		for (let c = 0; c < across; c++) {
			const cx = ox + c * cellW;
			const cy = oy + r * drawPitch * scale;
			svg += vcl_die_shape_svg(frm.doc.shape, cx, cy, cellW, cellH, 1);
			if (labelFirst && r === 0 && c === 0) {
				svg += '<text x="' + (cx + cellW / 2) + '" y="' + (cy + cellH / 2)
					+ '" text-anchor="middle" dominant-baseline="middle" font-size="8.5" fill="#6B70A0">'
					+ vcl_die_mm(W) + "&times;" + vcl_die_mm(L) + "</text>";
			}
		}
	}

	// Lane knife lines.
	for (let c = 1; c < across; c++) {
		const kx = ox + c * cellW;
		svg += '<line x1="' + kx + '" y1="' + oy + '" x2="' + kx + '" y2="' + (oy + bh)
			+ '" stroke="' + VCL_DIE.cut + '" stroke-width="0.8" stroke-dasharray="2,2"/>';
	}

	// Dimensions + machine direction.
	svg += vcl_die_dim_h(ox, ox + bw, oy + bh + 14, across + " × " + vcl_die_mm(W) + " = " + vcl_die_mm(contentW) + " mm across");
	const vLabel = overflow || repeat <= 0
		? round_ + " × " + vcl_die_mm(L) + " = " + vcl_die_mm(stackL) + " mm"
		: "repeat " + vcl_die_mm(repeat) + " mm";
	svg += vcl_die_dim_v(ox - 16, oy, oy + bh, vLabel);
	svg += '<text x="' + (ox + 4) + '" y="' + (oy - 7) + '" font-size="10.5" fill="' + VCL_DIE.muted + '">'
		+ "web direction ↓" + "</text>";
	svg += "</svg>";

	// Summary table.
	const rows = [
		["Across ups (lanes)", across + " lane" + (across === 1 ? "" : "s") + " × " + vcl_die_mm(W) + " mm"],
		["Round ups (per repeat)", round_ + " row" + (round_ === 1 ? "" : "s") + " × " + vcl_die_mm(L) + " mm"],
		["Total ups per repeat", "<b>" + (across * round_) + "</b>"],
		["Die content width across web", "<b>" + vcl_die_mm(contentW) + " mm</b> <span style='color:#8A8F98;'>(side trim excluded)</span>"],
	];
	if (repeat > 0) {
		rows.push(["Cylinder", vcl_die_mm(teeth) + " teeth → repeat <b>" + vcl_die_mm(repeat) + " mm</b>"]);
		if (!overflow) {
			rows.push(["Down-web pitch per row", vcl_die_mm(pitchL) + " mm"]);
			rows.push(["Gap between rows", "<b>" + vcl_die_mm(gapL) + " mm</b>"]);
		}
	}

	let table = '<table style="width:100%;max-width:620px;border-collapse:collapse;font-size:12.5px;'
		+ 'background:#fff;border:1px solid #E3E5E8;margin-top:10px;">';
	rows.forEach(function (r, i) {
		table += '<tr style="background:' + (i % 2 ? "#FFFFFF" : "#FAFAFB") + ';border-top:1px solid #EEF0F2;">'
			+ '<td style="padding:5px 10px;color:#555;width:44%;">' + r[0] + "</td>"
			+ '<td style="padding:5px 10px;">' + r[1] + "</td></tr>";
	});
	table += "</table>";

	// Flags.
	let flag = "";
	if (repeat <= 0) {
		flag = vcl_die_note("<b>Teeth not set</b> — the cylinder repeat is unknown, so the rows are drawn butted "
			+ "and the down-web gap cannot be shown. Enter Teeth to complete the layout.");
	} else if (overflow) {
		const fitsRotated = round_ * W <= repeat;
		flag = '<div style="padding:10px 14px;background:#FDECEC;border-left:3px solid ' + VCL_DIE.err
			+ ';border-radius:3px;font-size:12.5px;color:#555;margin:6px 0;">'
			+ '<b style="color:' + VCL_DIE.err + ';">Does not fit the cylinder.</b> '
			+ round_ + " round ups × " + vcl_die_mm(L) + " mm = <b>" + vcl_die_mm(stackL)
			+ " mm</b>, against a repeat of " + vcl_die_mm(repeat) + " mm (" + vcl_die_mm(teeth) + " teeth). "
			+ "Check Teeth, Round Ups, and which dimension runs around the cylinder."
			+ (fitsRotated
				? " It would fit if the die runs rotated (" + vcl_die_mm(W) + " mm around the cylinder = "
					+ vcl_die_mm(round_ * W) + " mm)."
				: "")
			+ "</div>";
	}

	const foot = '<div style="margin-top:6px;font-size:11px;color:#8A8F98;font-style:italic;">'
		+ "repeat = teeth × 3.175 mm (⅛″ gear pitch) &nbsp;·&nbsp; "
		+ "length runs around the cylinder, width across the web &nbsp;·&nbsp; "
		+ "side trim and the gap across the web are set per job on the Job Card."
		+ "</div>";

	$w.html('<div style="margin:6px 0 4px;">' + flag + svg + table + foot + "</div>");
}
