// CPS control and specification navigation on the Item form (WBS-27, WBS-28).
//
// `Item.custom_requires_cps` is derived and read-only: it is set from the Item's
// own CPS Control mode when that is Require or Exempt, and inherited from the
// Item Group tree otherwise. A read-only checkbox with no stated reason is a
// value the user can neither change nor understand, so the reason is fetched
// live and shown next to it — live rather than from the stored copy, because the
// stored copy was written the last time the Item was saved and the Item Group
// may have been reconfigured since.

const EXPLAIN_METHOD = "production_log.job_card_tracking.cps_desk.item_control_explanation";
const LINKED_SPECS_METHOD = "production_log.job_card_tracking.cps_desk.item_linked_specs";

const CPS_DOCTYPE = "Customer Product Specification";

function has_control_fields() {
	return Boolean(frappe.meta.has_field("Item", "custom_requires_cps"));
}

// --- Why is this Item controlled? (WBS-27) ----------------------------------

function show_control_explanation(frm) {
	frappe.call({
		method: EXPLAIN_METHOD,
		args: { item_code: frm.doc.name },
		callback(r) {
			const info = r.message;
			if (!info) return;

			// Cleared first: `refresh` fires more than once per visit, and two
			// copies of the same explanation reads as two different findings.
			frm.dashboard.clear_comment();
			frm.dashboard.add_comment(
				info.control_enabled
					? info.explanation
					: __("{0} (CPS control is currently switched off site-wide.)", [info.explanation]),
				info.requires_cps ? "blue" : "gray",
				true
			);

			// The stored flag is a denormalisation the Sales Order reads per
			// line. If it has fallen behind the rules — a group reconfigured
			// while a background re-derivation failed, say — that is worth
			// saying out loud rather than leaving to be discovered at submit.
			if (info.stored_flag !== info.requires_cps) {
				frm.dashboard.add_comment(
					__(
						"Requires CPS is stored as {0} but the rules currently say {1}. Save this Item to re-derive it.",
						[
							info.stored_flag ? __("Yes") : __("No"),
							info.requires_cps ? __("Yes") : __("No"),
						]
					),
					"orange",
					true
				);
			}
		},
	});
}

// --- Specifications for this Item (WBS-28) ----------------------------------

function linked_specs_html(payload) {
	const rows = (payload.rows || [])
		.map((row) => {
			const indicator = row.is_orderable ? "green" : "gray";
			const link = `/app/${frappe.router.slug(CPS_DOCTYPE)}/${encodeURIComponent(row.name)}`;
			const rate =
				row.current_rate == null
					? `<span style="color:#c0392b;">${__("No approved price")}</span>`
					: `${format_currency(row.current_rate)}${row.current_uom ? " / " + frappe.utils.escape_html(row.current_uom) : ""}`;

			return `
				<tr>
					<td style="padding:6px 8px;">
						<span class="indicator ${indicator}"></span>
						<a href="${link}">${frappe.utils.escape_html(row.specification_name || row.name)}</a>
						<div style="color:#888;font-size:11px;">${frappe.utils.escape_html(row.name)}</div>
					</td>
					<td style="padding:6px 8px;">${frappe.utils.escape_html(row.customer || "")}</td>
					<td style="padding:6px 8px;">${frappe.utils.escape_html(row.status || "")}
						<div style="color:#888;font-size:11px;">${frappe.utils.escape_html(row.docstatus_label || "")}</div>
					</td>
					<td style="padding:6px 8px;color:#666;">${frappe.utils.escape_html(row.revision || "")}</td>
					<td style="padding:6px 8px;text-align:right;">${rate}</td>
				</tr>`;
		})
		.join("");

	if (!rows) {
		return `<p style="color:#666;">${__(
			"No Customer Product Specification is linked to this Item yet."
		)}</p>`;
	}

	const notes = (payload.notes || [])
		.map((note) => `<li>${frappe.utils.escape_html(note)}</li>`)
		.join("");

	return `
		<p style="color:#666;font-size:12px;margin-bottom:8px;">
			${__("{0} specification(s), {1} orderable today across {2} customer(s). Green means submitted and Active.", [
				payload.summary.total,
				payload.summary.orderable,
				payload.summary.customers,
			])}
		</p>
		<table style="width:100%;border-collapse:collapse;font-size:13px;">
			<thead><tr style="background:#f5f5f5;">
				<th style="text-align:left;padding:6px 8px;">${__("Specification")}</th>
				<th style="text-align:left;padding:6px 8px;">${__("Customer")}</th>
				<th style="text-align:left;padding:6px 8px;">${__("Status")}</th>
				<th style="text-align:left;padding:6px 8px;">${__("Revision")}</th>
				<th style="text-align:right;padding:6px 8px;">${__("Current Rate")}</th>
			</tr></thead>
			<tbody>${rows}</tbody>
		</table>
		${notes ? `<ul style="color:#888;font-size:11px;margin-top:10px;">${notes}</ul>` : ""}`;
}

function show_linked_specs(frm) {
	frappe.call({
		method: LINKED_SPECS_METHOD,
		args: { item_code: frm.doc.name },
		callback(r) {
			if (!r.message) return;

			const d = new frappe.ui.Dialog({
				title: __("Specifications for {0}", [frm.doc.name]),
				size: "large",
				fields: [
					{ fieldtype: "HTML", fieldname: "specs", options: linked_specs_html(r.message) },
				],
				primary_action_label: __("Open Full List"),
				primary_action() {
					frappe.set_route("List", CPS_DOCTYPE, { linked_item: frm.doc.name });
					d.hide();
				},
			});
			d.show();
		},
	});
}

frappe.ui.form.on("Item", {
	refresh(frm) {
		if (frm.is_new() || !has_control_fields()) return;

		show_control_explanation(frm);

		frm.add_custom_button(
			__("Customer Product Specifications"),
			() => show_linked_specs(frm),
			__("View")
		);
	},

	custom_cps_control_mode(frm) {
		if (frm.is_new()) return;
		// The derived flag is recomputed server-side on validate, so the honest
		// thing to show before that is that the current value is now stale.
		frm.dashboard.clear_comment();
		frm.dashboard.add_comment(
			__("Save the Item to apply the new CPS Control setting."),
			"orange",
			true
		);
	},
});
