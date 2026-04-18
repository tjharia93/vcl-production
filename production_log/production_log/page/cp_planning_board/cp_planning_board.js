frappe.pages["cp-planning-board"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "CP Planning Board",
		single_column: true,
	});

	frappe.cp_planning_board = new CPPlanningBoard(page, wrapper);
};

frappe.pages["cp-planning-board"].on_page_show = function (wrapper) {
	if (frappe.cp_planning_board) {
		frappe.cp_planning_board.refresh();
	}
};

// ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
// Main Controller
// ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

class CPPlanningBoard {
	constructor(page, wrapper) {
		this.page = page;
		this.wrapper = wrapper;
		this.week_start = this.get_monday(frappe.datetime.get_today());
		this.selected_job = null;
		this.workstations = [];
		this.schedules = {};
		this.production_stages = [];
		this.job_pool = [];

		this._inject_styles();
		this._render_template();
		this._bind_toolbar();
		this.refresh();
	}

	// ââ Initialisation ââââââââââââââââââââââââââââââââââââââââââââââââââââââ

	_render_template() {
		$(this.wrapper).find(".layout-main-section").html(
			frappe.render_template("cp_planning_board", {})
		);
	}

	_inject_styles() {
		if (document.getElementById("cp-board-styles")) return;
		const style = document.createElement("style");
		style.id = "cp-board-styles";
		style.textContent = `
/* ââ Layout ââ */
.cp-planning-board-container {
	display: flex;
	flex-direction: column;
	height: calc(100vh - 120px);
	font-size: 13px;
}
.cp-board-toolbar {
	display: flex;
	align-items: center;
	gap: 16px;
	padding: 8px 12px;
	background: #f7f7f7;
	border-bottom: 1px solid #ddd;
	flex-shrink: 0;
}
.board-week-nav {
	display: flex;
	align-items: center;
	gap: 6px;
}
.cp-week-label {
	font-weight: 600;
	min-width: 200px;
	text-align: center;
}
.board-status-legend {
	display: flex;
	align-items: center;
	gap: 4px;
	font-size: 12px;
	color: #6b6b6b;
}
.legend-dot {
	display: inline-block;
	width: 10px;
	height: 10px;
	border-radius: 50%;
}
.legend-pending  { background: #adb5bd; }
.legend-inprogress { background: #007bff; }
.legend-done     { background: #28a745; }
.board-actions { margin-left: auto; }

/* ââ Body ââ */
.cp-board-body {
	display: flex;
	flex: 1;
	overflow: hidden;
}

/* ââ Job Pool ââ */
.cp-job-pool {
	width: 260px;
	min-width: 240px;
	border-right: 1px solid #ddd;
	display: flex;
	flex-direction: column;
	background: #fff;
}
.pool-header {
	display: flex;
	align-items: center;
	gap: 8px;
	padding: 10px 12px 6px;
	border-bottom: 1px solid #eee;
	font-size: 14px;
}
.pool-search-wrap { padding: 6px 10px; }
.pool-hint { padding: 0 10px 6px; font-size: 11px; }
.pool-list {
	flex: 1;
	overflow-y: auto;
	padding: 4px 8px;
}

/* ââ Job Card in Pool ââ */
.job-card {
	border: 1px solid #d1d5db;
	border-radius: 6px;
	padding: 8px 10px;
	margin-bottom: 6px;
	cursor: pointer;
	background: #fff;
	transition: background 0.15s, border-color 0.15s;
	position: relative;
}
.job-card:hover { background: #f0f4ff; border-color: #4a90d9; }
.job-card.selected {
	background: #e8f0fe;
	border-color: #1a73e8;
	box-shadow: 0 0 0 2px rgba(26,115,232,.25);
}
.job-card.plates-warning { border-left: 4px solid #dc3545; }
.job-card.plates-ok      { border-left: 4px solid #28a745; }
.job-card-title {
	font-weight: 600;
	font-size: 12px;
	color: #2B3990;
}
.job-card-sub {
	font-size: 11px;
	color: #555;
	margin-top: 2px;
}
.job-card-meta {
	display: flex;
	flex-wrap: wrap;
	gap: 4px;
	margin-top: 5px;
}
.job-meta-tag {
	background: #e9ecef;
	border-radius: 3px;
	padding: 1px 5px;
	font-size: 10px;
	color: #495057;
}
.job-meta-tag.warn { background: #f8d7da; color: #721c24; }
.job-meta-tag.ok   { background: #d4edda; color: #155724; }

/* ââ Planning Grid ââ */
.cp-grid-wrap {
	flex: 1;
	overflow: auto;
	padding: 8px;
}
.cp-planning-grid {
	border-collapse: collapse;
	width: 100%;
	min-width: 800px;
	table-layout: fixed;
}
.cp-planning-grid th {
	background: #2B3990;
	color: #fff;
	padding: 8px 10px;
	text-align: center;
	font-size: 12px;
	white-space: nowrap;
}
.cp-planning-grid th.day-col {
	background: #3d4fa8;
	min-width: 120px;
}
.cp-planning-grid td.day-label {
	background: #f0f2f8;
	font-weight: 600;
	font-size: 12px;
	padding: 6px 10px;
	vertical-align: middle;
	text-align: center;
	color: #2B3990;
	white-space: nowrap;
}
.cp-planning-grid td.day-label.today {
	background: #e8f0fe;
	border-left: 3px solid #2B3990;
}
.schedule-cell {
	vertical-align: top;
	padding: 4px 6px;
	min-height: 80px;
	cursor: pointer;
	transition: background 0.15s;
}
.schedule-cell:hover { background: #f5f7ff; }
.schedule-cell.drop-target {
	background: #e8f0fe;
	outline: 2px dashed #1a73e8;
}
.cell-inner { min-height: 60px; }

/* ââ Schedule Line chips ââ */
.schedule-chip {
	border-radius: 4px;
	padding: 3px 6px;
	margin-bottom: 3px;
	font-size: 11px;
	position: relative;
	display: flex;
	align-items: flex-start;
	gap: 4px;
}
.chip-pending   { background: #e9ecef; color: #343a40; }
.chip-inprogress { background: #cfe2ff; color: #084298; }
.chip-done      { background: #d1e7dd; color: #0a3622; }
.chip-skipped   { background: #f8d7da; color: #721c24; text-decoration: line-through; }
.chip-text { flex: 1; min-width: 0; overflow: hidden; }
.chip-job  { font-weight: 600; font-size: 10px; }
.chip-stage { font-size: 10px; opacity: 0.8; }
.chip-qty  { font-size: 10px; }
.chip-remove {
	cursor: pointer;
	color: #dc3545;
	font-weight: bold;
	opacity: 0.6;
	flex-shrink: 0;
	line-height: 1;
}
.chip-remove:hover { opacity: 1; }

/* ââ Add button in cell ââ */
.cell-add-btn {
	display: inline-block;
	cursor: pointer;
	color: #aaa;
	font-size: 18px;
	line-height: 1;
	width: 100%;
	text-align: center;
	padding: 4px 0;
	border-radius: 4px;
}
.cell-add-btn:hover { color: #2B3990; background: #e8f0fe; }

/* ââ Utilisation bar ââ */
.util-bar-wrap {
	height: 4px;
	background: #e9ecef;
	border-radius: 2px;
	margin-top: 4px;
}
.util-bar {
	height: 100%;
	border-radius: 2px;
	background: #28a745;
	transition: width 0.3s;
}
.util-bar.warn  { background: #ffc107; }
.util-bar.over  { background: #dc3545; }
		`;
		document.head.appendChild(style);
	}

	_bind_toolbar() {
		const self = this;

		$(this.wrapper).on("click", "#cp-prev-week", () => {
			self.week_start = frappe.datetime.add_days(self.week_start, -7);
			self.refresh();
		});
		$(this.wrapper).on("click", "#cp-next-week", () => {
			self.week_start = frappe.datetime.add_days(self.week_start, 7);
			self.refresh();
		});
		$(this.wrapper).on("click", "#cp-today-btn", () => {
			self.week_start = self.get_monday(frappe.datetime.get_today());
			self.refresh();
		});
		$(this.wrapper).on("click", "#cp-refresh-btn", () => {
			self.refresh();
		});

		// Pool search
		$(this.wrapper).on("input", "#cp-pool-search", function () {
			self._filter_pool($(this).val());
		});
	}

	// ââ Data Loading ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

	refresh() {
		this._set_week_label();
		this._load_data();
	}

	_load_data() {
		const self = this;
		self._show_loading(true);

		// Load in parallel
		Promise.all([
			frappe.call({
				method: "production_log.production_log.page.cp_planning_board.cp_planning_board.get_job_pool",
			}),
			frappe.call({
				method: "production_log.production_log.page.cp_planning_board.cp_planning_board.get_week_schedule",
				args: { week_start: self.week_start },
			}),
			frappe.call({
				method: "production_log.production_log.page.cp_planning_board.cp_planning_board.get_production_stages",
			}),
		]).then(([pool_r, schedule_r, stages_r]) => {
			self.job_pool = (pool_r && pool_r.message) || [];
			const schedule_data = (schedule_r && schedule_r.message) || {};
			self.workstations = schedule_data.workstations || [];
			self.production_stages = (stages_r && stages_r.message) || [];

			// Index schedules by workstation+date for fast lookup
			self.schedules = {};
			for (const s of schedule_data.schedules || []) {
				const key = self._cell_key(s.workstation, s.schedule_date);
				self.schedules[key] = s;
			}

			self._render_pool();
			self._render_grid();
			self._show_loading(false);
		});
	}

	_show_loading(on) {
		$("#cp-grid-loading").toggle(on);
		$("#cp-planning-grid").toggle(!on);
	}

	// ââ Job Pool ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

	_render_pool() {
		const count = this.job_pool.length;
		$("#cp-pool-count").text(count);
		this._filter_pool($("#cp-pool-search").val() || "");
	}

	_filter_pool(query) {
		const q = (query || "").toLowerCase();
		const filtered = this.job_pool.filter((j) => {
			return (
				!q ||
				(j.name || "").toLowerCase().includes(q) ||
				(j.customer || "").toLowerCase().includes(q) ||
				(j.specification_name || "").toLowerCase().includes(q)
			);
		});

		const self = this;
		const list = $("#cp-pool-list");
		list.empty();

		if (!filtered.length) {
			list.html('<div class="text-muted text-center" style="padding:20px">No open jobs</div>');
			return;
		}

		filtered.forEach((job) => {
			list.append(self._make_job_card_html(job));
		});

		// Click to select
		list.find(".job-card").on("click", function () {
			const job_id = $(this).data("job-id");
			self._select_job(job_id);
		});
	}

	_make_job_card_html(job) {
		const plates_ok =
			job.plate_status === "Old" || (job.plate_status === "New" && job.plates_confirmed);
		const plate_class = plates_ok ? "plates-ok" : "plates-warning";
		const plate_label = plates_ok
			? `<span class="job-meta-tag ok">Plates Ready</span>`
			: `<span class="job-meta-tag warn">Plates Pending</span>`;

		const parts_label =
			parseInt(job.number_of_parts) > 1
				? `<span class="job-meta-tag">${job.number_of_parts}-Part NCR</span>`
				: "";
		const colour_label =
			parseInt(job.number_of_colours) === 0
				? `<span class="job-meta-tag">Plain</span>`
				: `<span class="job-meta-tag">${job.number_of_colours} Colour(s)</span>`;

		const selected_class =
			this.selected_job && this.selected_job.name === job.name ? "selected" : "";

		return `
<div class="job-card ${plate_class} ${selected_class}" data-job-id="${frappe.utils.escape_html(job.name)}">
  <div class="job-card-title">${frappe.utils.escape_html(job.name)}</div>
  <div class="job-card-sub">${frappe.utils.escape_html(job.customer || "")}</div>
  <div class="job-card-sub" style="font-size:10px;color:#888">${frappe.utils.escape_html(job.specification_name || "")}</div>
  <div class="job-card-meta">
    <span class="job-meta-tag">Qty: ${frappe.utils.escape_html(String(job.quantity_ordered || ""))}</span>
    ${parts_label}
    ${colour_label}
    ${plate_label}
  </div>
</div>`;
	}

	_select_job(job_id) {
		this.selected_job = this.job_pool.find((j) => j.name === job_id) || null;
		// Re-render pool to update selected state
		this._filter_pool($("#cp-pool-search").val() || "");
		// Highlight cells
		if (this.selected_job) {
			$(".schedule-cell").addClass("drop-target");
			frappe.show_alert(
				{
					message: `<strong>${job_id}</strong> selected â click a machine cell to assign`,
					indicator: "blue",
				},
				3
			);
		} else {
			$(".schedule-cell").removeClass("drop-target");
		}
	}

	// ââ Grid ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

	_render_grid() {
		const head = $("#cp-grid-head");
		const body = $("#cp-grid-body");
		head.empty();
		body.empty();

		const days = this._week_days();
		const today = frappe.datetime.get_today();

		// Header row: machine columns
		let header_html = "<tr><th style='width:110px'>Date</th>";
		for (const ws of this.workstations) {
			header_html += `<th class="day-col">${frappe.utils.escape_html(ws)}</th>`;
		}
		header_html += "</tr>";
		head.html(header_html);

		// One row per day
		for (const day of days) {
			const is_today = day.date === today;
			const day_label = frappe.datetime.str_to_user(day.date);
			let row_html = `<tr>
<td class="day-label${is_today ? " today" : ""}">
  <div>${frappe.utils.escape_html(day.label)}</div>
  <div style="font-size:10px;color:#888">${frappe.utils.escape_html(day_label)}</div>
</td>`;

			for (const ws of this.workstations) {
				const key = this._cell_key(ws, day.date);
				const schedule = this.schedules[key] || null;
				row_html += this._make_cell_html(ws, day.date, schedule);
			}
			row_html += "</tr>";
			body.append(row_html);
		}

		// Bind cell clicks
		const self = this;
		body.find(".schedule-cell").on("click", function () {
			const ws = $(this).data("workstation");
			const date = $(this).data("date");
			if (self.selected_job) {
				self._open_assign_dialog(ws, date);
			}
		});

		// Bind chip remove buttons
		body.find(".chip-remove").on("click", function (e) {
			e.stopPropagation();
			const dps_name = $(this).data("dps");
			const line_name = $(this).data("line");
			self._remove_assignment(dps_name, line_name);
		});
	}

	_make_cell_html(workstation, date, schedule) {
		const lines_html = schedule
			? (schedule.schedule_lines || []).map((l) => this._make_chip_html(l, schedule.name)).join("")
			: "";

		const util_pct = schedule ? (schedule.utilization_pct || 0) : 0;
		const util_class = util_pct > 100 ? "over" : util_pct > 80 ? "warn" : "";
		const util_html =
			util_pct > 0
				? `<div class="util-bar-wrap"><div class="util-bar ${util_class}" style="width:${Math.min(util_pct, 100)}%"></div></div>`
				: "";

		return `
<td class="schedule-cell"
    data-workstation="${frappe.utils.escape_html(workstation)}"
    data-date="${frappe.utils.escape_html(date)}">
  <div class="cell-inner">
    ${lines_html}
    <div class="cell-add-btn" title="Assign job">+</div>
  </div>
  ${util_html}
</td>`;
	}

	_make_chip_html(line, dps_name) {
		const status_class = {
			Pending: "chip-pending",
			"In Progress": "chip-inprogress",
			Done: "chip-done",
			Skipped: "chip-skipped",
		}[line.status] || "chip-pending";

		return `
<div class="schedule-chip ${status_class}">
  <div class="chip-text">
    <div class="chip-job">${frappe.utils.escape_html(line.job_card_id || "")}</div>
    <div class="chip-stage">${frappe.utils.escape_html(line.production_stage || "")}</div>
    <div class="chip-qty">Qty: ${frappe.utils.escape_html(String(line.planned_qty || ""))}</div>
  </div>
  <span class="chip-remove"
        data-dps="${frappe.utils.escape_html(dps_name)}"
        data-line="${frappe.utils.escape_html(line.name)}"
        title="Remove">Ã</span>
</div>`;
	}

	// ââ Assignment Dialog ââââââââââââââââââââââââââââââââââââââââââââââââââââ

	_open_assign_dialog(workstation, date) {
		const self = this;
		const job = self.selected_job;

		// Determine applicable stages based on workstation type
		const is_collater = workstation.toLowerCase().includes("collat");
		const default_stage = is_collater ? "Collating" : "Printing";

		const stage_options = self.production_stages.map((s) => ({
			value: s.name,
			label: `${s.name}`,
		}));

		const d = new frappe.ui.Dialog({
			title: `Assign ${job.name} â ${workstation} on ${frappe.datetime.str_to_user(date)}`,
			fields: [
				{
					label: "Job Card",
					fieldname: "job_card_id",
					fieldtype: "Data",
					default: job.name,
					read_only: 1,
				},
				{
					label: "Production Stage",
					fieldname: "production_stage",
					fieldtype: "Select",
					options: self.production_stages.map((s) => s.name).join("\n"),
					default: default_stage,
					reqd: 1,
				},
				{
					label: "Planned Quantity",
					fieldname: "planned_qty",
					fieldtype: "Float",
					default: job.quantity_ordered || 0,
					reqd: 1,
					description: "Quantity to process in this run",
				},
				{
					label: "Estimated Hours",
					fieldname: "estimated_hours",
					fieldtype: "Float",
					default: 4,
					reqd: 1,
				},
			],
			primary_action_label: "Assign",
			primary_action(values) {
				d.hide();
				frappe.call({
					method: "production_log.production_log.page.cp_planning_board.cp_planning_board.assign_job",
					args: {
						workstation: workstation,
						schedule_date: date,
						job_card_id: job.name,
						production_stage: values.production_stage,
						planned_qty: values.planned_qty,
						estimated_hours: values.estimated_hours,
					},
					callback(r) {
						if (r.message && r.message.status === "ok") {
							frappe.show_alert(
								{ message: `${job.name} assigned to ${workstation}`, indicator: "green" },
								3
							);
							// Deselect job
							self.selected_job = null;
							$(".schedule-cell").removeClass("drop-target");
							// Refresh data
							self._load_data();
						}
					},
				});
			},
		});
		d.show();
	}

	// ââ Remove Assignment ââââââââââââââââââââââââââââââââââââââââââââââââââââ

	_remove_assignment(dps_name, schedule_line_name) {
		const self = this;
		frappe.confirm(
			`Remove this schedule entry?`,
			() => {
				frappe.call({
					method: "production_log.production_log.page.cp_planning_board.cp_planning_board.remove_assignment",
					args: { dps_name, schedule_line_name },
					callback(r) {
						if (r.message && r.message.status === "ok") {
							frappe.show_alert({ message: "Entry removed", indicator: "green" }, 2);
							self._load_data();
						}
					},
				});
			}
		);
	}

	// ââ Utilities ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

	get_monday(date_str) {
		const d = new Date(date_str);
		const day = d.getDay(); // 0=Sun
		const diff = day === 0 ? -6 : 1 - day;
		d.setDate(d.getDate() + diff);
		return frappe.datetime.obj_to_str(d);
	}

	_week_days() {
		const labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
		const days = [];
		for (let i = 0; i < 7; i++) {
			const date = frappe.datetime.add_days(this.week_start, i);
			days.push({ date, label: labels[i] });
		}
		return days;
	}

	_set_week_label() {
		const end = frappe.datetime.add_days(this.week_start, 6);
		const start_user = frappe.datetime.str_to_user(this.week_start);
		const end_user = frappe.datetime.str_to_user(end);
		$("#cp-week-label").text(`Week: ${start_user} â ${end_user}`);
	}

	_cell_key(workstation, date) {
		return `${workstation}|${date}`;
	}
}
