// Dies — List View settings
// One status per die, worst condition first. Nothing is stored: every state is
// recomputed from the dimensions, the ups and the teeth, so it can never go
// stale against the record it describes.
//
//   Check cylinder — round ups × length overruns the cylinder repeat
//                    (teeth × 3.175 mm). One of the three is wrong.
//   Incomplete     — ups or teeth not recorded, so the die cannot be planned.
//   Special cut    — irregular profile: the box is an envelope, see the dieline.
//   Ready          — complete, and the layout fits the cylinder.

window.__VCL_DIES_LIST__ = "bundled";

frappe.listview_settings["Dies"] = {
	add_fields: ["length", "width", "shape", "across_ups", "round_ups", "teeth", "custom_setup_status"],

	get_indicator(doc) {
		// Prefer the stored status — clicking the pill then filters the list.
		// Fall back to computing it, so a die saved before the field existed
		// still reads correctly.
		let status = doc.custom_setup_status;
		if (!status) {
			const L = flt(doc.length);
			const round_ = cint(doc.round_ups);
			const teeth = flt(doc.teeth);
			if (teeth > 0 && round_ > 0 && round_ * L > teeth * 3.175 + 0.05) status = "Check Cylinder";
			else if (!cint(doc.across_ups) || !round_ || !teeth) status = "Incomplete";
			else status = "Ready";
		}

		if (status === "Check Cylinder") {
			return [__("Check cylinder"), "red", "custom_setup_status,=,Check Cylinder"];
		}
		if (status === "Incomplete") {
			return [__("Incomplete"), "orange", "custom_setup_status,=,Incomplete"];
		}
		// A special cut is not a problem, it is a profile — but it is worth
		// spotting in the list, and Shape is what you filter on.
		if ((doc.shape || "").toUpperCase() === "IRREGULAR") {
			return [__("Special cut"), "purple", "shape,=,IRREGULAR"];
		}
		return [__("Ready"), "green", "custom_setup_status,=,Ready"];
	},
};
