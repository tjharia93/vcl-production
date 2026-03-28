frappe.ui.form.on("Production Entry", {
	station(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.station) return;

		frappe.db.get_value("Production Station", row.station, "max_reels", (r) => {
			if (!r || !r.max_reels) return;
			const maxReels = r.max_reels;
			const current = parseInt(row.number_of_reels) || 1;

			if (current > maxReels) {
				frappe.msgprint(
					__(
						"Station {0} supports a maximum of {1} reel(s). Resetting to {1}.",
						[row.station, maxReels]
					)
				);
				frappe.model.set_value(cdt, cdn, "number_of_reels", String(maxReels));
			}
		});
	},

	number_of_reels(frm, cdt, cdn) {
		// Frappe re-evaluates depends_on automatically on refresh.
		// Trigger a refresh to ensure conditional sections update.
		frm.refresh_field("production_entries");
	},

	start_time(frm, cdt, cdn) {
		_recalculate_duration(frm, cdt, cdn);
	},

	end_time(frm, cdt, cdn) {
		_recalculate_duration(frm, cdt, cdn);
	},

	// Reel 1 weight real-time validation
	r1_end_weight(frm, cdt, cdn) {
		_validate_weight(cdt, cdn, "r1");
	},
	r2_end_weight(frm, cdt, cdn) {
		_validate_weight(cdt, cdn, "r2");
	},
	r3_end_weight(frm, cdt, cdn) {
		_validate_weight(cdt, cdn, "r3");
	},
	r4_end_weight(frm, cdt, cdn) {
		_validate_weight(cdt, cdn, "r4");
	},
});

function _recalculate_duration(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.start_time || !row.end_time) return;

	const toSeconds = (t) => {
		const parts = String(t).split(":");
		return parseInt(parts[0]) * 3600 + parseInt(parts[1]) * 60 + (parseInt(parts[2]) || 0);
	};

	let startSec = toSeconds(row.start_time);
	let endSec = toSeconds(row.end_time);
	let diffSec;

	if (endSec <= startSec) {
		// Overnight shift
		diffSec = 86400 - startSec + endSec;
	} else {
		diffSec = endSec - startSec;
	}

	const hours = Math.round((diffSec / 3600) * 100) / 100;
	frappe.model.set_value(cdt, cdn, "duration_hours", hours);
}

function _validate_weight(cdt, cdn, prefix) {
	const row = locals[cdt][cdn];
	const startW = row[`${prefix}_start_weight`];
	const endW = row[`${prefix}_end_weight`];
	const reelNum = prefix.replace("r", "");

	if (startW && endW !== undefined && endW !== null && endW !== "") {
		if (parseFloat(endW) >= parseFloat(startW)) {
			frappe.msgprint(
				__("Reel {0}: End weight must be less than start weight.", [reelNum]),
				__("Weight Validation")
			);
		}
	}
}
