frappe.ui.form.on("Job Card Monobox", {
	setup(frm) {
		// Only Active Monobox specs belonging to this customer. Without the
		// filter the link offers every spec of every product type, and picking
		// a Carton one only fails server-side at save.
		frm.set_query("customer_product_spec", () => ({
			query:
				"production_log.job_card_tracking.doctype.job_card_monobox.job_card_monobox." +
				"get_monobox_customer_product_spec_query",
			filters: { customer: frm.doc.customer },
		}));

		frm.set_query("cutting_die", () => ({
			filters: { status: ["!=", "Retired"] },
		}));
	},

	refresh(frm) {
		frm.trigger("show_route_summary");
	},

	customer(frm) {
		if (frm.doc.customer_product_spec) {
			frm.set_value("customer_product_spec", null);
		}
	},

	show_route_summary(frm) {
		const stages = [
			["applies_printing", "Board Prep & Printing"],
			["applies_coating", "Coating"],
			["applies_diecut", "Die-cutting & Stripping"],
			["applies_window_patch", "Window Patching"],
			["applies_gluing", "Folding & Gluing"],
			["applies_bundling", "Bundling & Packing"],
		];

		const on = stages.filter(([f]) => frm.doc[f]).map(([, label]) => label);
		const off = stages.filter(([f]) => !frm.doc[f]).map(([, label]) => label);

		if (!on.length) {
			return;
		}

		// Stated on the form as well as the traveller: a stage that is off is a
		// decision, and it should be visible without opening the print preview.
		frm.dashboard.clear_headline();
		frm.dashboard.set_headline(
			`<b>Route:</b> ${on.join(" → ")}` +
				(off.length ? `<br><span class="text-muted">Not run: ${off.join(", ")}</span>` : "")
		);
	},
});
