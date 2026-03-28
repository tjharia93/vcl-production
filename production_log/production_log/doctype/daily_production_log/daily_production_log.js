frappe.ui.form.on("Daily Production Log", {
	onload(frm) {
		if (frm.is_new()) {
			frm.set_value("production_date", frappe.datetime.get_today());
			frm.set_value("production_manager", frappe.session.user);
		}

		// Filter production_manager to show only users with Production Manager role
		frm.set_query("production_manager", () => {
			return {
				query: "frappe.core.doctype.user.user.get_users_with_role",
				filters: { role: "Production Manager" },
			};
		});
	},

	refresh(frm) {
		_update_entry_counter(frm);

		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Amend"), function () {
				frappe.set_route("Form", "Daily Production Log", frm.doc.name);
				frm.amend_doc();
			}, __("Actions"));
		}
	},

	production_date(frm) {
		_check_duplicate_async(frm);
	},

	shift(frm) {
		_check_duplicate_async(frm);
	},
});

// Child table events
frappe.ui.form.on("Production Entry", {
	production_entries_add(frm) {
		_update_entry_counter(frm);
		_recalculate_summary(frm);
	},

	production_entries_remove(frm) {
		_update_entry_counter(frm);
		_recalculate_summary(frm);
	},

	number_of_reels(frm) {
		_recalculate_summary(frm);
	},

	r1_full_reams(frm) { _recalculate_summary(frm); },
	r2_full_reams(frm) { _recalculate_summary(frm); },
	r3_full_reams(frm) { _recalculate_summary(frm); },
	r4_full_reams(frm) { _recalculate_summary(frm); },

	r1_incomplete_reel(frm) { _recalculate_summary(frm); },
	r2_incomplete_reel(frm) { _recalculate_summary(frm); },
	r3_incomplete_reel(frm) { _recalculate_summary(frm); },
	r4_incomplete_reel(frm) { _recalculate_summary(frm); },
});

// ----------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------

function _update_entry_counter(frm) {
	const count = (frm.doc.production_entries || []).length;
	frm.set_value("total_entries", count);
	frm.dashboard.set_headline(__("Entries: {0}", [count]));
}

function _recalculate_summary(frm) {
	const entries = frm.doc.production_entries || [];
	let totalReels = 0;
	let totalReams = 0;
	let totalIncomplete = 0;

	entries.forEach((entry) => {
		const numReels = parseInt(entry.number_of_reels) || 1;
		totalReels += numReels;

		for (let i = 1; i <= numReels; i++) {
			totalReams += parseInt(entry[`r${i}_full_reams`]) || 0;
			totalIncomplete += entry[`r${i}_incomplete_reel`] ? 1 : 0;
		}
	});

	frm.set_value("total_reels_processed", totalReels);
	frm.set_value("total_full_reams", totalReams);
	frm.set_value("total_incomplete_reels", totalIncomplete);
}

function _check_duplicate_async(frm) {
	if (!frm.doc.production_date || !frm.doc.shift) return;

	frappe.db.get_value(
		"Daily Production Log",
		{
			production_date: frm.doc.production_date,
			shift: frm.doc.shift,
			docstatus: ["!=", 2],
			name: ["!=", frm.doc.name || ""],
		},
		"name",
		(r) => {
			if (r && r.name) {
				frappe.msgprint(
					__(
						"Warning: A production log already exists for {0} - {1} shift: {2}",
						[frm.doc.production_date, frm.doc.shift, r.name]
					)
				);
			}
		}
	);
}
