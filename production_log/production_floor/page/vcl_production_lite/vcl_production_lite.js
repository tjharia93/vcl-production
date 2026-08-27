/**
 * VCL Production Lite — the production floor screen.
 *
 * Built for a 360px Android phone held in one hand next to a running machine.
 * Everything is one tap from the day's board: add a job, change its status,
 * type an actual quantity. The desk forms behind this page still exist and
 * still work, but nobody on the floor should ever need to open one.
 */

frappe.pages["vcl-production-lite"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("VCL Production"),
		single_column: true,
	});
	wrapper.vcl_board = new VclProductionBoard(page);
};

frappe.pages["vcl-production-lite"].on_page_show = function (wrapper) {
	if (wrapper.vcl_board) {
		wrapper.vcl_board.refresh();
	}
};

const VCL_STATUSES = [
	"Not Started",
	"Running",
	"Paused",
	"Completed",
	"Carried Forward",
];

const VCL_STATUS_CLASS = {
	"Planned": "vcl-badge-planned",
	"Not Started": "vcl-badge-not-started",
	"Running": "vcl-badge-running",
	"Paused": "vcl-badge-paused",
	"Completed": "vcl-badge-completed",
	"Carried Forward": "vcl-badge-carried",
};

class VclProductionBoard {
	constructor(page) {
		this.page = page;
		this.date = frappe.datetime.get_today();
		this.tab = "today";
		this.board = null;
		this.setup_actions();
		this.make_shell();
		this.refresh();
	}

	// ------------------------------------------------------------------
	// shell
	// ------------------------------------------------------------------

	setup_actions() {
		this.$add_job_btn = this.page.set_primary_action(
			__("+ Add Job"),
			() => this.add_job_dialog(),
			"add"
		);
		this.page.set_secondary_action(__("Refresh"), () => this.refresh(), "refresh");
		this.page.add_menu_item(__("Remembered Jobs"), () =>
			frappe.set_route("List", "VCL Production Job")
		);
		this.page.add_menu_item(__("Machines & Processes"), () =>
			frappe.set_route("List", "VCL Production Machine")
		);
		this.page.add_menu_item(__("Open This Day as a Form"), () => {
			if (this.board && this.board.day) {
				frappe.set_route("Form", "VCL Daily Production", this.board.day.name);
			}
		});
	}

	make_shell() {
		this.$container = $(`
			<div class="vcl-board">
				<div class="vcl-topbar">
					<div class="vcl-datebar">
						<button class="vcl-nav" data-step="-1" aria-label="${__("Previous day")}">‹</button>
						<input type="date" class="vcl-date-input" />
						<button class="vcl-nav" data-step="1" aria-label="${__("Next day")}">›</button>
						<button class="vcl-today-btn">${__("Today")}</button>
					</div>
					<div class="vcl-tabs">
						<button class="vcl-tab" data-tab="today">${__("Today")}</button>
						<button class="vcl-tab" data-tab="report">${__("Report")}</button>
						<button class="vcl-tab" data-tab="history">${__("History")}</button>
					</div>
				</div>
				<div class="vcl-body"></div>
			</div>
		`).appendTo(this.page.main);

		this.$body = this.$container.find(".vcl-body");
		this.$date_input = this.$container.find(".vcl-date-input");

		this.$date_input.on("change", () => {
			const value = this.$date_input.val();
			if (value) {
				this.date = value;
				this.refresh();
			}
		});

		this.$container.on("click", ".vcl-nav", (event) => {
			const step = parseInt($(event.currentTarget).data("step"), 10);
			this.date = frappe.datetime.add_days(this.date, step);
			this.refresh();
		});

		this.$container.on("click", ".vcl-today-btn", () => {
			this.date = frappe.datetime.get_today();
			this.refresh();
		});

		this.$container.on("click", ".vcl-tab", (event) => {
			this.tab = $(event.currentTarget).data("tab");
			this.render();
		});

		this.$container.on("click", ".vcl-card", (event) => {
			const row = $(event.currentTarget).data("row");
			this.quick_update_dialog(row);
		});
	}

	// ------------------------------------------------------------------
	// data
	// ------------------------------------------------------------------

	refresh() {
		return frappe
			.call({
				method: "production_log.production_floor.api.get_board",
				args: { production_date: this.date },
				freeze: !this.board,
				freeze_message: __("Loading production…"),
			})
			.then((response) => {
				this.board = response.message;
				this.render();
			});
	}

	apply_day(day) {
		if (this.board) {
			this.board.day = day;
		}
		this.render();
	}

	// ------------------------------------------------------------------
	// render
	// ------------------------------------------------------------------

	render() {
		if (!this.board) {
			return;
		}
		this.$date_input.val(this.date);
		this.$container.find(".vcl-tab").removeClass("active");
		this.$container.find(`.vcl-tab[data-tab="${this.tab}"]`).addClass("active");

		const show_add = this.tab === "today" && this.board.day.status === "Open";
		this.$add_job_btn.toggle(show_add);

		if (this.tab === "today") {
			this.render_today();
		} else if (this.tab === "report") {
			this.render_report();
		} else {
			this.render_history();
		}
	}

	render_today() {
		const day = this.board.day;
		const parts = [this.render_day_header(day), this.render_summary(day)];

		const attention = this.render_attention(day);
		if (attention) {
			parts.push(attention);
		}

		if (!day.items.length) {
			parts.push(`
				<div class="vcl-empty">
					<div class="vcl-empty-title">${__("Nothing entered yet")}</div>
					<div class="vcl-empty-hint">${__("Tap + Add Job to record what is running.")}</div>
				</div>
			`);
		} else {
			day.department_order.forEach((department) => {
				const rows = day.items.filter(
					(row) => (row.department || __("Unassigned")) === department
				);
				parts.push(`
					<div class="vcl-dept">
						<div class="vcl-dept-head">
							<span>${frappe.utils.escape_html(department.toUpperCase())}</span>
							<span class="vcl-dept-count">${rows.length}</span>
						</div>
						${rows.map((row) => this.render_card(row)).join("")}
					</div>
				`);
			});
		}

		parts.push(this.render_day_footer(day));
		this.$body.html(parts.join(""));
		this.bind_footer();
	}

	render_day_header(day) {
		const closed = day.status === "Closed";
		return `
			<div class="vcl-day-head">
				<div class="vcl-day-title">${frappe.utils.escape_html(
					frappe.datetime.str_to_user(day.production_date)
				)}</div>
				<div class="vcl-day-meta">
					<span class="vcl-badge ${closed ? "vcl-badge-completed" : "vcl-badge-running"}">
						${closed ? __("Closed") : __("Open")}
					</span>
					${day.is_demo ? `<span class="vcl-badge vcl-badge-demo">${__("Demo Data")}</span>` : ""}
				</div>
			</div>
		`;
	}

	render_summary(day) {
		const summary = day.summary || {};
		const cards = [
			["Planned", summary["Planned"] || 0],
			["Running", summary["Running"] || 0],
			["Completed", summary["Completed"] || 0],
			["Not Started", summary["Not Started"] || 0],
			["Carried Forward", summary["Carried Forward"] || 0],
		];
		if (summary["Paused"]) {
			cards.push(["Paused", summary["Paused"]]);
		}
		return `
			<div class="vcl-summary">
				${cards
					.map(
						([label, count]) => `
					<div class="vcl-stat ${VCL_STATUS_CLASS[label]}">
						<div class="vcl-stat-number">${count}</div>
						<div class="vcl-stat-label">${__(label)}</div>
					</div>
				`
					)
					.join("")}
			</div>
		`;
	}

	render_attention(day) {
		const exceptions = day.exceptions || {};
		if (!exceptions.all || !exceptions.all.length) {
			return "";
		}
		const items = exceptions.all
			.map(
				(item) => `
			<li class="${item.severity === "critical" ? "vcl-critical" : ""}">
				<strong>${frappe.utils.escape_html(item.label)}</strong> — ${frappe.utils.escape_html(
					item.message
				)}
			</li>
		`
			)
			.join("");
		return `
			<div class="vcl-attention">
				<div class="vcl-attention-head">
					${__("Attention Required")}
					<span class="vcl-attention-count">${exceptions.jobs_needing_attention}</span>
				</div>
				<ul>${items}</ul>
			</div>
		`;
	}

	render_card(row) {
		const unit = frappe.utils.escape_html(row.uom || "");
		const planned = this.format_qty(row.planned_quantity);
		const actual = this.format_qty(row.actual_quantity);
		const reason = (row.reason || "").trim();
		return `
			<div class="vcl-card" data-row="${frappe.utils.escape_html(row.name)}">
				<div class="vcl-card-main">
					<div class="vcl-machine">${frappe.utils.escape_html(row.machine || "")}</div>
					<div class="vcl-customer">${frappe.utils.escape_html(row.customer_name || "")}</div>
					<div class="vcl-job">${frappe.utils.escape_html(row.job_name || "")}</div>
					<div class="vcl-qty">
						<span class="vcl-qty-actual">${actual || "0"}</span>
						<span class="vcl-qty-sep">/</span>
						<span class="vcl-qty-plan">${planned || "—"}</span>
						<span class="vcl-qty-unit">${unit}</span>
					</div>
					${reason ? `<div class="vcl-reason">${frappe.utils.escape_html(reason)}</div>` : ""}
				</div>
				<div class="vcl-card-side">
					<span class="vcl-badge ${VCL_STATUS_CLASS[row.status] || ""}">${__(row.status)}</span>
				</div>
			</div>
		`;
	}

	render_day_footer(day) {
		if (day.status === "Closed") {
			return `
				<div class="vcl-footer">
					<div class="vcl-footer-note">
						${__("Closed by")} ${frappe.utils.escape_html(day.closed_by || "")}
					</div>
					${
						this.board.is_manager
							? `<button class="btn btn-default btn-lg vcl-wide" data-action="reopen">${__(
									"Reopen Day"
							  )}</button>`
							: ""
					}
				</div>
			`;
		}
		return `
			<div class="vcl-footer">
				<button class="btn btn-default btn-lg vcl-wide" data-action="notes">
					${day.notes ? __("Edit Day Notes") : __("Add Day Notes")}
				</button>
				<button class="btn btn-default btn-lg vcl-wide" data-action="whatsapp">
					${__("Copy WhatsApp Report")}
				</button>
				${
					this.board.is_manager
						? `<button class="btn btn-primary btn-lg vcl-wide" data-action="close">${__(
								"Close Production Day"
						  )}</button>`
						: ""
				}
			</div>
		`;
	}

	bind_footer() {
		this.$body.find('[data-action="notes"]').on("click", () => this.day_notes_dialog());
		this.$body.find('[data-action="whatsapp"]').on("click", () => this.copy_whatsapp());
		this.$body.find('[data-action="close"]').on("click", () => this.close_day());
		this.$body.find('[data-action="reopen"]').on("click", () => this.reopen_day());
	}

	render_report() {
		this.$body.html(`<div class="vcl-loading">${__("Building report…")}</div>`);
		frappe
			.call({
				method: "production_log.production_floor.api.get_report",
				args: { production_date: this.date },
			})
			.then((response) => {
				const report = response.message;
				this.report = report;
				this.$body.html(`
					<div class="vcl-report">
						<div class="vcl-report-actions">
							<button class="btn btn-primary btn-lg vcl-wide" data-action="whatsapp">
								${__("Copy WhatsApp Report")}
							</button>
							<button class="btn btn-default btn-lg vcl-wide" data-action="copy-full">
								${__("Copy Full Report")}
							</button>
						</div>
						<pre class="vcl-report-text">${frappe.utils.escape_html(report.text)}</pre>
					</div>
				`);
				this.$body.find('[data-action="whatsapp"]').on("click", () => this.copy_whatsapp());
				this.$body.find('[data-action="copy-full"]').on("click", () => {
					frappe.utils.copy_to_clipboard(report.text);
					frappe.show_alert({ message: __("Report copied"), indicator: "green" });
				});
			});
	}

	render_history() {
		this.$body.html(`<div class="vcl-loading">${__("Loading history…")}</div>`);
		frappe
			.call({ method: "production_log.production_floor.api.get_history", args: { limit: 60 } })
			.then((response) => {
				const days = response.message || [];
				if (!days.length) {
					this.$body.html(
						`<div class="vcl-empty"><div class="vcl-empty-title">${__(
							"No production days yet"
						)}</div></div>`
					);
					return;
				}
				this.$body.html(`
					<div class="vcl-history">
						${days
							.map(
								(day) => `
							<div class="vcl-history-row" data-date="${frappe.utils.escape_html(day.production_date)}">
								<div class="vcl-history-date">
									${frappe.utils.escape_html(frappe.datetime.str_to_user(day.production_date))}
									${day.is_demo ? `<span class="vcl-badge vcl-badge-demo">${__("Demo")}</span>` : ""}
								</div>
								<div class="vcl-history-meta">
									<span>${day.total} ${__("jobs")}</span>
									<span class="vcl-badge ${
										day.status === "Closed"
											? "vcl-badge-completed"
											: "vcl-badge-running"
									}">${__(day.status)}</span>
								</div>
							</div>
						`
							)
							.join("")}
					</div>
				`);
				this.$body.find(".vcl-history-row").on("click", (event) => {
					this.date = $(event.currentTarget).data("date");
					this.tab = "report";
					this.refresh();
				});
			});
	}

	// ------------------------------------------------------------------
	// actions
	// ------------------------------------------------------------------

	day_notes_dialog() {
		const dialog = new frappe.ui.Dialog({
			title: __("Day Notes"),
			size: "small",
			fields: [
				{
					fieldname: "notes",
					fieldtype: "Small Text",
					label: __("Notes for the whole day"),
					default: this.board.day.notes || "",
					description: __("Shown at the end of the report and the WhatsApp message."),
				},
			],
			primary_action_label: __("Save"),
			primary_action: (values) => {
				frappe
					.call({
						method: "production_log.production_floor.api.set_day_notes",
						args: { production_date: this.date, notes: values.notes || "" },
						freeze: true,
					})
					.then((response) => {
						if (response.message) {
							dialog.hide();
							this.apply_day(response.message);
						}
					});
			},
		});
		dialog.show();
	}

	remember_job(row, dialog) {
		frappe
			.call({
				method: "production_log.production_floor.api.remember_current_job",
				args: {
					customer_name: row.customer_name,
					job_name: row.job_name,
					department: row.department,
					uom: row.uom,
				},
				freeze: true,
			})
			.then((response) => {
				if (response.message) {
					frappe.show_alert({
						message: __("Remembered {0}", [response.message.label]),
						indicator: "green",
					});
					dialog.hide();
					this.refresh();
				}
			});
	}

	copy_whatsapp() {
		frappe
			.call({
				method: "production_log.production_floor.api.get_report",
				args: { production_date: this.date },
			})
			.then((response) => {
				frappe.utils.copy_to_clipboard(response.message.whatsapp);
				frappe.show_alert({
					message: __("WhatsApp report copied — paste it into the group"),
					indicator: "green",
				});
			});
	}

	close_day() {
		const exceptions = this.board.day.exceptions || {};
		const warnings = exceptions.warnings || [];
		let message = __("Close production for {0}?", [
			frappe.datetime.str_to_user(this.board.day.production_date),
		]);
		if (warnings.length) {
			message +=
				"<br><br><b>" +
				__("Still outstanding") +
				"</b><br>" +
				warnings
					.map((item) => frappe.utils.escape_html(item.label + " — " + item.message))
					.join("<br>");
		}
		frappe.confirm(message, () => {
			frappe
				.call({
					method: "production_log.production_floor.api.close_day",
					args: { production_date: this.date },
					freeze: true,
				})
				.then((response) => {
					if (response.message) {
						this.apply_day(response.message.day);
						frappe.show_alert({ message: __("Day closed"), indicator: "green" });
					}
				});
		});
	}

	reopen_day() {
		frappe.confirm(__("Reopen this production day for editing?"), () => {
			frappe
				.call({
					method: "production_log.production_floor.api.reopen_day",
					args: { production_date: this.date },
					freeze: true,
				})
				.then((response) => {
					if (response.message) {
						this.apply_day(response.message);
					}
				});
		});
	}

	// ------------------------------------------------------------------
	// dialogs
	// ------------------------------------------------------------------

	add_job_dialog() {
		const departments = this.board.departments || [];
		const units = this.board.units || [];
		const default_department = departments[0];

		const dialog = new frappe.ui.Dialog({
			title: __("Add Job"),
			size: "small",
			fields: [
				{
					fieldname: "department",
					fieldtype: "Select",
					label: __("Department"),
					options: departments,
					default: default_department,
					reqd: 1,
					onchange: () => this.on_department_change(dialog),
				},
				{
					fieldname: "machine",
					fieldtype: "Select",
					label: __("Machine / Process"),
					options: [],
					reqd: 1,
				},
				{ fieldtype: "Section Break" },
				{
					fieldname: "recent",
					fieldtype: "HTML",
					label: __("Recent Jobs"),
				},
				{
					fieldname: "job_cards",
					fieldtype: "HTML",
					label: __("Open Job Cards"),
				},
				{
					fieldname: "production_job",
					fieldtype: "Link",
					label: __("Search Remembered Jobs"),
					options: "VCL Production Job",
					description: __("Optional — or just type a new customer and job below."),
					onchange: () => this.on_job_pick(dialog),
				},
				{
					fieldname: "customer_name",
					fieldtype: "Data",
					label: __("Customer"),
					reqd: 1,
				},
				{
					fieldname: "job_name",
					fieldtype: "Data",
					label: __("Job"),
					reqd: 1,
				},
				{ fieldtype: "Section Break" },
				{
					fieldname: "planned_quantity",
					fieldtype: "Data",
					label: __("Planned Quantity"),
				},
				{ fieldtype: "Column Break" },
				{
					fieldname: "uom",
					fieldtype: "Select",
					label: __("Unit"),
					options: units,
					default: units[0],
				},
				{
					fieldname: "remember",
					fieldtype: "Check",
					label: __("Remember this Job"),
					default: 1,
				},
			],
			primary_action_label: __("Add"),
			primary_action: (values) => this.submit_add_job(dialog, values),
		});

		this.picked_job_card = null;
		dialog.show();
		this.make_numeric(dialog, "planned_quantity");
		this.on_department_change(dialog);
		this.render_recent_jobs(dialog);
		this.render_job_cards(dialog);
	}

	on_department_change(dialog) {
		const department = dialog.get_value("department");
		const machines = (this.board.machines || []).filter(
			(machine) => machine.department === department
		);
		const field = dialog.fields_dict.machine;
		field.df.options = machines.map((machine) => machine.name);
		field.refresh();
		if (machines.length) {
			dialog.set_value("machine", machines[0].name);
		} else {
			dialog.set_value("machine", "");
		}
		this.picked_job_card = null;
		this.render_recent_jobs(dialog);
		this.render_job_cards(dialog);
	}

	on_job_pick(dialog) {
		const name = dialog.get_value("production_job");
		if (!name) {
			return;
		}
		frappe.db
			.get_doc("VCL Production Job", name)
			.then((job) => this.fill_job(dialog, job));
	}

	fill_job(dialog, job) {
		// Picking a remembered job is a different route in. The stamp records
		// that a supervisor chose a live card today, so it must not survive a
		// change of mind - and a card remembered months ago may be closed now.
		this.picked_job_card = null;
		dialog.$wrapper.find(".vcl-jobcard").removeClass("selected");
		dialog.set_value("customer_name", job.customer_name);
		dialog.set_value("job_name", job.job_name);
		if (job.default_uom) {
			dialog.set_value("uom", job.default_uom);
		}
		if (job.department && (this.board.departments || []).includes(job.department)) {
			if (dialog.get_value("department") !== job.department) {
				dialog.set_value("department", job.department);
			}
		}
	}

	render_recent_jobs(dialog) {
		const wrapper = dialog.fields_dict.recent.$wrapper;
		frappe
			.call({
				method: "production_log.production_floor.api.suggest_jobs",
				args: { department: dialog.get_value("department"), limit: 8 },
			})
			.then((response) => {
				const jobs = response.message || [];
				if (!jobs.length) {
					wrapper.html(
						`<div class="vcl-chip-empty">${__(
							"No remembered jobs yet — type a new one below."
						)}</div>`
					);
					return;
				}
				wrapper.html(`
					<div class="vcl-chips">
						${jobs
							.map(
								(job, index) => `
							<button type="button" class="vcl-chip" data-index="${index}">
								${frappe.utils.escape_html(job.full_label || job.customer_name)}
							</button>
						`
							)
							.join("")}
					</div>
				`);
				wrapper.find(".vcl-chip").on("click", (event) => {
					const job = jobs[$(event.currentTarget).data("index")];
					dialog.set_value("production_job", job.name);
					this.fill_job(dialog, job);
				});
			});
	}

	render_job_cards(dialog) {
		// Optional shortcut, never a requirement. Computer Paper job cards are
		// the only kind that exist, so the row is shown for that department
		// only; every other department types as it always has.
		const wrapper = dialog.fields_dict.job_cards.$wrapper;
		const department = dialog.get_value("department");
		dialog.set_df_property("job_cards", "hidden", department !== "Computer");
		if (department !== "Computer") {
			wrapper.empty();
			return;
		}
		frappe
			.call({ method: "production_log.production_floor.api.list_open_job_cards" })
			.then((response) => {
				const cards = response.message || [];
				if (!cards.length) {
					wrapper.html(
						`<div class="vcl-chip-empty">${__("No open job cards.")}</div>`
					);
					return;
				}
				wrapper.html(`
					<div class="vcl-jobcards">
						${cards
							.map(
								(card, index) => `
							<button type="button" class="vcl-jobcard" data-index="${index}">
								<span class="vcl-jobcard-ref">${frappe.utils.escape_html(card.ref)}</span>
								<span class="vcl-jobcard-label">
									<span class="vcl-jobcard-customer">${frappe.utils.escape_html(
										card.customer_name
									)}</span>
									<span class="vcl-jobcard-job">${frappe.utils.escape_html(card.job_name)}</span>
								</span>
							</button>
						`
							)
							.join("")}
					</div>
				`);
				wrapper.find(".vcl-jobcard").on("click", (event) => {
					const card = cards[$(event.currentTarget).data("index")];
					wrapper.find(".vcl-jobcard").removeClass("selected");
					$(event.currentTarget).addClass("selected");
					dialog.set_value("customer_name", card.customer_name);
					dialog.set_value("job_name", card.job_name);
					this.picked_job_card = card.job_card;
				});
			})
			.catch(() => {
				// Job Card Tracking is not this screen's problem. Fail quiet.
				wrapper.empty();
			});
	}

	submit_add_job(dialog, values) {
		const invalid = this.numeric_error(values.planned_quantity, __("Planned Quantity"));
		if (invalid) {
			frappe.msgprint(invalid);
			return;
		}
		frappe
			.call({
				method: "production_log.production_floor.api.add_item",
				args: {
					production_date: this.date,
					department: values.department,
					machine: values.machine,
					customer_name: values.customer_name,
					job_name: values.job_name,
					planned_quantity: values.planned_quantity || null,
					uom: values.uom,
					production_job: values.production_job || null,
					remember: values.remember ? 1 : 0,
					job_card: this.picked_job_card || null,
				},
				freeze: true,
			})
			.then((response) => {
				if (response.message) {
					dialog.hide();
					this.apply_day(response.message);
					frappe.show_alert({ message: __("Job added"), indicator: "green" });
				}
			});
	}

	quick_update_dialog(row_name) {
		const row = (this.board.day.items || []).find((item) => item.name === row_name);
		if (!row) {
			return;
		}
		if (this.board.day.status === "Closed") {
			frappe.msgprint(__("This day is closed. A manager must reopen it first."));
			return;
		}

		let selected_status = row.status;

		const dialog = new frappe.ui.Dialog({
			title: __("Update Job"),
			size: "small",
			fields: [
				{ fieldname: "header", fieldtype: "HTML" },
				{ fieldname: "status_buttons", fieldtype: "HTML", label: __("Status") },
				{
					fieldname: "actual_quantity",
					fieldtype: "Data",
					label: __("Actual Quantity"),
					default: row.actual_quantity || "",
				},
				{ fieldtype: "Column Break" },
				{
					fieldname: "uom",
					fieldtype: "Select",
					label: __("Unit"),
					options: this.board.units || [],
					default: row.uom,
				},
				{ fieldtype: "Section Break" },
				{
					fieldname: "planned_quantity",
					fieldtype: "Data",
					label: __("Planned Quantity"),
					default: row.planned_quantity || "",
				},
				{
					fieldname: "reason",
					fieldtype: "Small Text",
					label: __("Reason"),
					default: row.reason || "",
					description: __("Required when a job is paused or carried forward."),
				},
				{
					fieldname: "notes",
					fieldtype: "Small Text",
					label: __("Notes"),
					default: row.notes || "",
				},
			],
			primary_action_label: __("Save"),
			primary_action: (values) => {
				const invalid =
					this.numeric_error(values.actual_quantity, __("Actual Quantity")) ||
					this.numeric_error(values.planned_quantity, __("Planned Quantity"));
				if (invalid) {
					frappe.msgprint(invalid);
					return;
				}
				frappe
					.call({
						method: "production_log.production_floor.api.update_item",
						args: {
							production_date: this.date,
							row: row.name,
							status: selected_status,
							actual_quantity: values.actual_quantity || "",
							planned_quantity: values.planned_quantity || "",
							uom: values.uom,
							reason: values.reason || "",
							notes: values.notes || "",
						},
						freeze: true,
					})
					.then((response) => {
						if (response.message) {
							dialog.hide();
							this.apply_day(response.message);
							frappe.show_alert({ message: __("Updated"), indicator: "green" });
						}
					});
			},
			secondary_action_label: __("Remove"),
			secondary_action: () => {
				frappe.confirm(__("Remove this job from the day?"), () => {
					frappe
						.call({
							method: "production_log.production_floor.api.remove_item",
							args: { production_date: this.date, row: row.name },
							freeze: true,
						})
						.then((response) => {
							if (response.message) {
								dialog.hide();
								this.apply_day(response.message);
							}
						});
				});
			},
		});

		dialog.fields_dict.header.$wrapper.html(`
			<div class="vcl-update-head">
				<div class="vcl-machine">${frappe.utils.escape_html(row.machine || "")}</div>
				<div class="vcl-customer">${frappe.utils.escape_html(row.customer_name || "")}</div>
				<div class="vcl-job">${frappe.utils.escape_html(row.job_name || "")}</div>
			</div>
		`);

		const $status = dialog.fields_dict.status_buttons.$wrapper;
		$status.html(`
			<div class="vcl-status-grid">
				${VCL_STATUSES.map(
					(status) => `
					<button type="button" class="vcl-status-btn ${VCL_STATUS_CLASS[status]} ${
						status === selected_status ? "selected" : ""
					}" data-status="${frappe.utils.escape_html(status)}">
						${__(status).toUpperCase()}
					</button>
				`
				).join("")}
			</div>
		`);
		$status.find(".vcl-status-btn").on("click", (event) => {
			selected_status = $(event.currentTarget).data("status");
			$status.find(".vcl-status-btn").removeClass("selected");
			$(event.currentTarget).addClass("selected");
			const needs_reason = ["Paused", "Carried Forward"].includes(selected_status);
			dialog.set_df_property("reason", "reqd", needs_reason ? 1 : 0);
			dialog.fields_dict.reason.refresh();
			if (needs_reason) {
				dialog.fields_dict.reason.$input && dialog.fields_dict.reason.$input.focus();
			}
		});

		dialog.show();
		this.make_numeric(dialog, "actual_quantity");
		this.make_numeric(dialog, "planned_quantity");

		// A row typed in a hurry, with "Remember this Job" unticked, would
		// otherwise never make it into the master.
		if (!row.production_job) {
			dialog.add_custom_action(__("Remember this Job"), () => this.remember_job(row, dialog));
		}
	}

	// ------------------------------------------------------------------
	// helpers
	// ------------------------------------------------------------------

	/**
	 * Quantities are typed on a phone. A numeric keypad and a number input
	 * together mean "41+6" cannot reach the server in the first place — and
	 * `numeric_error` catches it on a browser that allows it anyway.
	 */
	make_numeric(dialog, fieldname) {
		const field = dialog.fields_dict[fieldname];
		if (field && field.$input) {
			field.$input.attr({
				type: "number",
				step: "any",
				min: "0",
				inputmode: "decimal",
			});
		}
	}

	numeric_error(value, label) {
		if (value === null || value === undefined || String(value).trim() === "") {
			return null;
		}
		const text = String(value).trim();
		if (!/^\d*\.?\d+$/.test(text)) {
			return __(
				"{0} must be a plain number such as 0.5, 9 or 1031. Please add it up and enter the total.",
				[label]
			);
		}
		return null;
	}

	format_qty(value) {
		if (value === null || value === undefined || value === "") {
			return "";
		}
		const number = Number(value);
		if (isNaN(number)) {
			return "";
		}
		if (number === Math.round(number)) {
			return String(Math.round(number));
		}
		return String(parseFloat(number.toFixed(3)));
	}
}
