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
	add_fields: ["length", "width", "shape", "across_ups", "round_ups", "teeth"],

	get_indicator(doc) {
		const L = flt(doc.length);
		const across = cint(doc.across_ups);
		const round_ = cint(doc.round_ups);
		const teeth = flt(doc.teeth);
		const repeat = teeth * 3.175;

		if (teeth > 0 && round_ > 0 && round_ * L > repeat + 0.05) {
			return [__("Check cylinder"), "red", "teeth,>,0"];
		}
		if (!across || !round_ || !teeth) {
			return [__("Incomplete"), "orange", "teeth,=,0"];
		}
		if ((doc.shape || "").toUpperCase() === "IRREGULAR") {
			return [__("Special cut"), "purple", "shape,=,IRREGULAR"];
		}
		return [__("Ready"), "green"];
	},
};
