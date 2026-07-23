// CPS control on the Sales Order form (WBS-25, WBS-26).
//
// Two jobs, both of them advisory:
//
//   1. Narrow the Customer Product Specification list on a line to this order's
//      customer and this line's exact Item, and show it by specification name
//      rather than by CPT-SPEC document id.
//   2. On selection, preview the eligible approved price and the technical
//      shape of the specification, and put the approved rate on the line.
//
// Nothing here is a control. The server owns every one of these decisions:
// `so_spec_control.validate` re-reads the specification, re-resolves the price
// and re-stamps the snapshot from the database on save and on submit, discarding
// whatever the client put in those fields (design §7 V12). So a stale preview,
// a tampered payload or a user with the console open changes what is displayed
// and never what the order is held to. That is also why every failure below
// degrades to "clear the line and say why" instead of blocking the form.

const PREVIEW_METHOD = "production_log.job_card_tracking.cps_desk.cps_line_preview";

// The batch endpoint, not the single-card one. Raising several cards is one
// call because it has to be one *transaction*: Frappe runs a whitelisted method
// inside a transaction and rolls it back when an exception escapes, so a throw
// on the third selection un-does the first two. Called once per card instead,
// each insert commits on its own and a failure halfway leaves half a job on the
// floor with nothing recording that the rest was ever asked for.
const BATCH_JOB_CARD_METHOD = "vcl_compass.api.jobcards.job_cards_from_sales_order";

// Fields the preview drives. Kept here only as the fallback for clearing a row
// when the server has not answered; when it has, its own `display_fields` list
// is used, so the two cannot drift.
const FALLBACK_DISPLAY_FIELDS = [
	"custom_cps_rate",
	"custom_cps_uom",
	"custom_cps_valid_from",
	"custom_cps_price_row",
	"custom_spec_name",
	"custom_job_size",
	"custom_number_of_parts",
	"custom_number_of_colours",
];

function has_cps_field() {
	// The custom fields deploy in a separate step from this script (design §15).
	// On a site where they have not landed, do nothing at all rather than throw
	// on every row. Asked of the meta rather than of the grid, because `setup`
	// runs before the grid exists.
	return Boolean(frappe.meta.has_field("Sales Order Item", "custom_cps"));
}

function set_row_values(row, values) {
	Object.keys(values || {}).forEach((fieldname) => {
		frappe.model.set_value(row.doctype, row.name, fieldname, values[fieldname]);
	});
}

function clear_preview(row, fieldnames) {
	const blank = {};
	(fieldnames || FALLBACK_DISPLAY_FIELDS).forEach((fieldname) => {
		blank[fieldname] = null;
	});
	set_row_values(row, blank);
}

// --- The specification list on a line (WBS-25) ------------------------------

function cps_query(frm, cdt, cdn) {
	const row = locals[cdt][cdn];

	// A specification belongs to one customer and describes one Item. Until both
	// are known there is no correct list to show, and showing the whole book
	// invites picking another customer's agreed price. `name is not set` is
	// never true, so this matches nothing — deliberately.
	if (!frm.doc.customer || !row.item_code) {
		return { filters: { name: ["is", "not set"] } };
	}

	return {
		filters: {
			customer: frm.doc.customer,
			// Exact Item. There is no "unlinked means compatible" case: an
			// unlinked specification serves nothing (cps_rules.spec_serves_item).
			linked_item: row.item_code,
			docstatus: 1,
			status: "Active",
		},
	};
}

// --- Preview on selection (WBS-26) ------------------------------------------

function preview_line(frm, cdt, cdn) {
	const row = locals[cdt][cdn];

	if (!row.custom_cps) {
		clear_preview(row);
		return;
	}

	if (!frm.doc.customer || !row.item_code) {
		frappe.model.set_value(cdt, cdn, "custom_cps", null);
		frappe.show_alert({
			message: __("Choose the customer and the Item before the specification."),
			indicator: "orange",
		});
		return;
	}

	frappe.call({
		method: PREVIEW_METHOD,
		args: {
			cps: row.custom_cps,
			item_code: row.item_code,
			customer: frm.doc.customer,
			transaction_date: frm.doc.transaction_date,
		},
		callback(r) {
			const preview = r.message;
			if (!preview) return;

			// The row may have moved on while the call was in flight — the user
			// changed the Item, or picked a different specification. Applying a
			// stale answer would describe a line that no longer exists.
			const current = locals[cdt] && locals[cdt][cdn];
			if (!current || current.custom_cps !== preview.cps) return;

			apply_preview(frm, current, preview);
		},
	});
}

function apply_preview(frm, row, preview) {
	set_row_values(row, preview.display || {});

	if (preview.severity === "block") {
		// The specification cannot be used on this line at all, and the submit
		// will say so. Take it back off rather than leave a selection that looks
		// made.
		frappe.model.set_value(row.doctype, row.name, "custom_cps", null);
		frappe.msgprint({
			title: __("Specification Control"),
			indicator: "red",
			message: preview.message,
		});
		return;
	}

	if (preview.severity === "warning") {
		// Draft-permissive, submit-strict (design §7 V7): the order can be saved
		// while the price is still with the approver, but not submitted.
		frappe.show_alert({ message: preview.message, indicator: "orange" }, 10);
		return;
	}

	set_row_values(row, preview.apply || {});

	const rate = (preview.apply || {}).rate;
	frappe.show_alert({
		message: __("{0} at {1}", [
			(preview.display || {}).custom_spec_name || preview.cps,
			format_currency(rate, frm.doc.currency),
		]),
		indicator: "green",
	});
}

// --- The technical preview, on demand ---------------------------------------
//
// The values a printer needs — parts, papers, colours, packing — are on the
// specification rather than on the order line, and a rep checking that they
// have picked the right one should not have to open the CPS in another tab.

function spec_preview_html(preview) {
	const rows = (preview.technical || [])
		.map(
			(row) => `
			<tr>
				<td style="padding:4px 8px;color:#666;white-space:nowrap;">${frappe.utils.escape_html(row.label)}</td>
				<td style="padding:4px 8px;"><b>${frappe.utils.escape_html(String(row.value))}</b></td>
			</tr>`
		)
		.join("");

	const parts = (preview.parts || [])
		.map(
			(part) => `
			<tr>
				<td style="padding:4px 8px;">${frappe.utils.escape_html(String(part.part_number ?? ""))}</td>
				<td style="padding:4px 8px;">${frappe.utils.escape_html(part.paper_type || "")}</td>
				<td style="padding:4px 8px;">${frappe.utils.escape_html(String(part.gsm ?? ""))}</td>
				<td style="padding:4px 8px;">${frappe.utils.escape_html(part.colour || "")}</td>
				<td style="padding:4px 8px;color:#666;">${frappe.utils.escape_html(part.purpose || "")}</td>
			</tr>`
		)
		.join("");

	const parts_block = parts
		? `<h5 style="margin-top:14px;">${__("Parts")}</h5>
			<table style="width:100%;border-collapse:collapse;font-size:13px;">
				<thead><tr style="background:#f5f5f5;">
					<th style="text-align:left;padding:4px 8px;">${__("Part")}</th>
					<th style="text-align:left;padding:4px 8px;">${__("Paper")}</th>
					<th style="text-align:left;padding:4px 8px;">${__("GSM")}</th>
					<th style="text-align:left;padding:4px 8px;">${__("Colour")}</th>
					<th style="text-align:left;padding:4px 8px;">${__("Purpose")}</th>
				</tr></thead>
				<tbody>${parts}</tbody>
			</table>`
		: "";

	// Stated plainly rather than implied: what is on screen is a read of the
	// specification as it stands now, and the order is held to the snapshot the
	// server takes at submit.
	const footer = `<p style="margin-top:14px;color:#888;font-size:12px;">
		${__("Preview only. The values the order is held to are taken server-side when it is submitted.")}
	</p>`;

	return `<table style="width:100%;border-collapse:collapse;font-size:13px;">${rows}</table>${parts_block}${footer}`;
}

function show_spec_preview(frm) {
	const selected = frm.fields_dict.items.grid.get_selected_children();
	const row = selected.length ? selected[0] : null;

	if (!row) {
		frappe.msgprint(__("Tick a row first to preview its specification."));
		return;
	}
	if (!row.custom_cps) {
		frappe.msgprint(__("Row {0} has no specification selected.", [row.idx]));
		return;
	}

	frappe.call({
		method: PREVIEW_METHOD,
		args: {
			cps: row.custom_cps,
			item_code: row.item_code,
			customer: frm.doc.customer,
			transaction_date: frm.doc.transaction_date,
		},
		callback(r) {
			if (!r.message) return;
			new frappe.ui.Dialog({
				title: __("Specification {0}", [r.message.cps]),
				fields: [
					{
						fieldtype: "HTML",
						fieldname: "preview",
						options: spec_preview_html(r.message),
					},
				],
			}).show();
		},
	});
}

// --- Sales Order -> Job Cards -----------------------------------------------
//
// One dialog for every kind of card a line can become. The kind is decided by
// the product type the *order froze*, never by what the operator picks and
// never by reading the specification as it stands now — a specification retyped
// since the order must not reroute a job that has already been sold.
//
// Everything product-specific below is a property of a registry entry rather
// than a branch, so adding Label or ETR later is a line of data. The two that
// differ today:
//
//   * Computer Paper carries a plate. Carton has no plate fields at all; its
//     analogue is `repeat` (Old / New job), which Computer Paper does not have.
//   * The customer field differs between the two cards, but that is the
//     server's problem, not this dialog's — nothing identifying is sent.
//
// Nothing identifying, pricing or specifying is passed from here. The only
// operator inputs are quantity, due date, and the per-kind production detail.
// Everything else the card carries is taken server-side from the frozen line.
//
// The whole selection goes over in one call, and it is all or nothing. The
// dialog can therefore offer to raise several cards without offering to raise
// some of them: either every selected line is carded or the order is left
// exactly as it was found. What it cannot offer is a batch spanning two kinds —
// the production details below are asked once and mean one thing, so a mixed
// selection is refused before the call rather than half executed after it.

const JOB_CARD_KINDS = {
	"Computer Paper": { kind: "computer_paper", plate: true, repeat: false },
	Carton: { kind: "carton", plate: false, repeat: true },
};

function snapshot_product_type(row) {
	try {
		return JSON.parse(row.custom_spec_snapshot || "{}").product_type || null;
	} catch (error) {
		return null;
	}
}

function job_card_candidates(frm) {
	return (frm.doc.items || []).filter((row) => row.custom_cps).map((row) => {
		const remaining = Math.max(0, flt(row.qty) - flt(row.custom_jc_qty));
		const product_type = snapshot_product_type(row);
		const spec = JOB_CARD_KINDS[product_type];
		let blocked_reason = null;
		if (!row.custom_spec_snapshot) {
			blocked_reason = __("Missing the frozen specification snapshot.");
		} else if (!spec) {
			blocked_reason = __("No Job Card type raises {0} lines yet.", [
				product_type || __("untyped"),
			]);
		} else if (remaining <= 0) {
			blocked_reason = __("The full ordered quantity is already on Job Cards.");
		}
		return { row, remaining, product_type, spec, blocked_reason };
	});
}

function job_card_line_html(candidate) {
	const row = candidate.row;
	const status = candidate.blocked_reason
		? `<span class="indicator-pill red">${frappe.utils.escape_html(candidate.blocked_reason)}</span>`
		: `<span class="indicator-pill green">${__("Ready — {0}", [candidate.product_type])}</span>`;
	return `<div style="margin:6px 0 2px;padding:8px 10px;background:var(--subtle-fg);border-radius:6px;">
		<b>${__("Line {0}: {1}", [row.idx, frappe.utils.escape_html(row.item_code)])}</b>
		<div class="text-muted small">${frappe.utils.escape_html(row.custom_spec_name || row.custom_cps)} · ${__(
			"Ordered {0}, already carded {1}, remaining {2}",
			[format_number(row.qty), format_number(row.custom_jc_qty || 0), format_number(candidate.remaining)]
		)}</div>${status}</div>`;
}

// A dialog-level `depends_on` that is true while any line of this kind is
// ticked. Built from the actual indices rather than from a count, so unticking
// the last Carton line hides the Carton-only inputs immediately.
function any_selected_expression(candidates, predicate) {
	const clauses = candidates
		.map((candidate, index) => ({ candidate, index }))
		.filter(({ candidate }) => !candidate.blocked_reason && predicate(candidate))
		.map(({ index }) => `doc.select_${index}`);
	return clauses.length ? `eval:${clauses.join("||")}` : null;
}

function show_job_card_dialog(frm) {
	const candidates = job_card_candidates(frm);
	if (!candidates.length) {
		frappe.msgprint(__("No Sales Order items have a Customer Product Specification."));
		return;
	}

	const needs_plate = any_selected_expression(candidates, (c) => c.spec && c.spec.plate);
	const needs_repeat = any_selected_expression(candidates, (c) => c.spec && c.spec.repeat);

	const fields = [{
		fieldtype: "HTML",
		fieldname: "instructions",
		options: `<p>${__("Confirm which Sales Order items need Job Cards. Each selected line creates one Draft Job Card of the kind its frozen snapshot says it is — Computer Paper lines become Computer Paper cards, Carton lines become Carton cards.")}</p>`,
	}];

	candidates.forEach((candidate, index) => {
		fields.push(
			{ fieldtype: "HTML", fieldname: `line_${index}`, options: job_card_line_html(candidate) },
			{
				fieldtype: "Check",
				fieldname: `select_${index}`,
				label: __("Create Job Card for line {0}", [candidate.row.idx]),
				default: candidate.blocked_reason ? 0 : 1,
				read_only: candidate.blocked_reason ? 1 : 0,
			},
			{
				fieldtype: "Float",
				fieldname: `qty_${index}`,
				label: __("Job Card Quantity"),
				default: candidate.remaining,
				read_only: candidate.blocked_reason ? 1 : 0,
				depends_on: `eval:doc.select_${index}`,
			}
		);
	});

	fields.push({ fieldtype: "Section Break", label: __("Production details") });

	if (needs_plate) {
		// Shown, and required, only while a Computer Paper line is selected.
		// Asking for a plate on a Carton-only batch would be asking for a value
		// the Carton card has nowhere to put.
		fields.push(
			{
				fieldtype: "Select",
				fieldname: "plate_status",
				label: __("Plate Status (Computer Paper)"),
				options: "New\nOld",
				default: "New",
				depends_on: needs_plate,
				mandatory_depends_on: needs_plate,
			},
			{
				fieldtype: "Data",
				fieldname: "plate_code",
				label: __("Plate Code"),
				depends_on: `eval:(${needs_plate.slice(5)})&&doc.plate_status=='Old'`,
				mandatory_depends_on: `eval:(${needs_plate.slice(5)})&&doc.plate_status=='Old'`,
			}
		);
	}

	if (needs_repeat) {
		fields.push({
			fieldtype: "Select",
			fieldname: "repeat_job",
			label: __("Old Job / New Job (Carton)"),
			options: "New\nOld",
			default: "New",
			depends_on: needs_repeat,
			mandatory_depends_on: needs_repeat,
		});
	}

	fields.push(
		{ fieldtype: "Column Break" },
		{ fieldtype: "Date", fieldname: "due_date", label: __("Due Date"), default: frm.doc.delivery_date }
	);

	const dialog = new frappe.ui.Dialog({
		title: __("Create Job Cards"),
		fields,
		primary_action_label: __("Create selected Job Cards"),
		async primary_action(values) {
			const selected = candidates.map((candidate, index) => ({ candidate, index }))
				.filter(({ candidate, index }) => !candidate.blocked_reason && values[`select_${index}`]);
			if (!selected.length) {
				frappe.msgprint(__("Select at least one eligible Sales Order item."));
				return;
			}

			// One batch raises one kind of card. The server refuses a mixed
			// selection by name before it inserts anything, so nothing is at
			// risk either way — but the operator is better told which lines
			// clash, here, than told after asking that the batch was rejected.
			const kinds = [...new Set(selected.map(({ candidate }) => candidate.spec.kind))];
			if (kinds.length > 1) {
				frappe.msgprint({
					title: __("One Kind Of Job Card Per Batch"),
					indicator: "orange",
					message: __(
						"The production details differ by kind — a plate belongs to a Computer Paper card and a repeat to a Carton one — so one batch raises one kind. Card each kind in its own pass. Selected: {0}.",
						[selected_kind_summary(selected)]
					),
				});
				return;
			}

			dialog.disable_primary_action();
			try {
				// One call, one transaction. Frappe runs a whitelisted method
				// inside a transaction and rolls it back when an exception
				// escapes, so a throw on the third selection un-does the first
				// two. Deliberately not wrapped in a try/catch: the throw must
				// surface as itself, naming which selection failed, rather than
				// being softened into a partial success nobody asked for.
				const result = await frappe.xcall(BATCH_JOB_CARD_METHOD, {
					sales_order: frm.doc.name,
					selections: selected.map(({ candidate, index }) => ({
						so_item: candidate.row.name,
						qty: values[`qty_${index}`],
						due_date: values.due_date,
						...job_card_kind_inputs(candidate, values),
					})),
				});
				dialog.hide();
				show_batch_result(result, selected.length);
				frm.reload_doc();
			} finally {
				dialog.enable_primary_action();
			}
		},
	});
	dialog.show();
}

// "2 × Computer Paper, 1 × Carton" — the product types as the operator sees them
// on the lines, not the server's internal kind slugs.
function selected_kind_summary(selected) {
	const counts = new Map();
	selected.forEach(({ candidate }) => {
		const label = candidate.product_type;
		counts.set(label, (counts.get(label) || 0) + 1);
	});
	return [...counts].map(([label, count]) => `${count} × ${label}`).join(", ");
}

// What the batch endpoint answered. It returns every card it raised — the whole
// batch or, because a failure rolls the transaction back, none of it — so there
// is no partial case to render and no per-card success to tally.
//
// `expected` is what was asked for. It should always equal the count returned,
// and saying so when it does not is cheaper than discovering later that a
// selection went missing between the dialog and the insert.
function show_batch_result(result, expected) {
	const created = (result && result.created) || [];

	if (!created.length) {
		frappe.msgprint({
			title: __("No Job Cards created"),
			indicator: "orange",
			message: __("The server raised no Job Cards for this selection."),
		});
		return;
	}

	const links = created.map((card) => {
		const url = `/app/${frappe.router.slug(card.doctype)}/${encodeURIComponent(card.job_card)}`;
		return `<div><a href="${url}">${frappe.utils.escape_html(card.job_card)}</a>
			<span class="text-muted small"> · ${__("qty {0}", [format_number(card.qty)])}</span></div>`;
	});

	// Only when the two disagree. A count line on every success is noise; a
	// count line here is the one thing worth reading.
	const shortfall = created.length === expected
		? ""
		: `<p class="text-muted small">${__("{0} selected, {1} created.", [expected, created.length])}</p>`;

	frappe.msgprint({
		title: __("{0} Draft Job Cards created", [created.length]),
		indicator: "green",
		message: links.join("") + shortfall,
	});
}

// The per-kind half of the payload. A Carton call carries no plate keys at all
// rather than carrying them as nulls: the server should be able to tell "this
// kind has no plate" from "this operator left the plate blank".
function job_card_kind_inputs(candidate, values) {
	const spec = candidate.spec || {};
	const inputs = {};
	if (spec.plate) {
		inputs.plate_status = values.plate_status;
		inputs.plate_code = values.plate_code;
	}
	if (spec.repeat) {
		inputs.repeat = values.repeat_job;
	}
	return inputs;
}

// --- Resets -----------------------------------------------------------------
//
// A specification is only ever valid for one customer, one Item and one order
// date. Change any of the three and what is on the line is no longer an answer
// to the question being asked, so it goes — rather than being left to fail at
// submit, hours later, in someone else's hands.

function clear_all_lines(frm, reason, drop_cps) {
	let cleared = 0;

	(frm.doc.items || []).forEach((row) => {
		if (!row.custom_cps) return;
		if (drop_cps) frappe.model.set_value(row.doctype, row.name, "custom_cps", null);
		clear_preview(row);
		cleared += 1;
	});

	if (cleared) {
		frm.refresh_field("items");
		frappe.show_alert({ message: reason, indicator: "orange" }, 7);
	}
}

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || !has_cps_field()) return;
		frm.add_custom_button(
			__("Job Cards"),
			() => show_job_card_dialog(frm),
			__("Create")
		);
	},

	setup(frm) {
		if (!has_cps_field()) return;
		frm.set_query("custom_cps", "items", (doc, cdt, cdn) => cps_query(frm, cdt, cdn));
	},

	onload(frm) {
		if (!has_cps_field() || !frm.fields_dict.items) return;
		frm.fields_dict.items.grid.add_custom_button(__("Specification Preview"), () =>
			show_spec_preview(frm)
		);
	},

	customer(frm) {
		if (!has_cps_field()) return;
		// A different customer means a different agreed specification and a
		// different agreed price. Nothing selected under the old one survives.
		clear_all_lines(
			frm,
			__("Customer changed — specifications cleared. Reselect them for the new customer."),
			true
		);
	},

	transaction_date(frm) {
		if (!has_cps_field()) return;
		// The specification still applies; its price may not. Eligibility is
		// resolved against the order date (design §5.2), so the preview is
		// re-taken rather than the selection dropped.
		(frm.doc.items || []).forEach((row) => {
			if (row.custom_cps) preview_line(frm, row.doctype, row.name);
		});
	},
});

frappe.ui.form.on("Sales Order Item", {
	custom_cps(frm, cdt, cdn) {
		if (!has_cps_field()) return;
		preview_line(frm, cdt, cdn);
	},

	item_code(frm, cdt, cdn) {
		if (!has_cps_field()) return;
		const row = locals[cdt][cdn];
		if (!row.custom_cps) return;

		// A specification describes exactly one Item, so changing the Item
		// invalidates it outright — there is no version of this that is still
		// partly right.
		frappe.model.set_value(cdt, cdn, "custom_cps", null);
		clear_preview(row);
		frappe.show_alert({
			message: __("Item changed — specification cleared on row {0}.", [row.idx]),
			indicator: "orange",
		});
	},
});
