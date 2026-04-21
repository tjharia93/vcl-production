/*
 * Production Planner — client controller (Phase 1 scaffold).
 *
 * This file will grow in phases: Phase 1 is just the boot, header, and
 * empty frames. Columns, entries, the modal, conflict detection, and
 * the print flow arrive in Phases 2–4.
 */

// ─────────────────────────────────────────────────────────────────────
// Module constants
// ─────────────────────────────────────────────────────────────────────

// Canonical stage ordering on the board. Any Workstation Type not in
// this list still renders but gets appended at the end — keeps Phase 1
// tidy without preventing Tanuj from spinning up new WTs later.
const STAGE_ORDER = ["Design", "Printing", "Collation", "Slitting"];

// 3-letter chip label next to each stage name. Hand-mapped so the
// server-side lowercased stage ids (`printing`, `collation`, `slitting`)
// don't yield the wrong abbreviation ("PRI"/"COL"/"SLI").
const TAG_BY_ID = {
	design: "DES",
	printing: "PRN",
	collation: "COL",
	slitting: "SLT",
};

// UOM per stage. Printing is asymmetric: planned side tracks reels in
// (the scheduler input); actual side tracks sheets out (what actually
// came off the press). Every other stage uses the same unit both ways.
const UOM_BY_STAGE = {
	design:    { planned: "days",  actual: "days" },
	printing:  { planned: "reels", actual: "sheets" },
	collation: { planned: "sets",  actual: "sets" },
	slitting:  { planned: "rolls", actual: "rolls" },
};

// Day-of-week labels for the Week view (Mon–Sat, six rows — matches
// the prototype). Sunday is treated as non-working.
const WEEK_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

// Qty field definitions per stage. `key` matches the DocType fieldname
// on PSL / PE, so the same map drives both the modal form and the
// save payload. Printing is asymmetric: two planned fields (reels in,
// sheets out) and one actual field (sheets).
const STAGE_QTY = {
	design: {
		planned: [{ key: "planned_qty",    label: "Planned Days",   uom: "days" }],
		actual:  [{ key: "actual_qty",     label: "Actual Days",    uom: "days" }],
	},
	printing: {
		planned: [
			{ key: "planned_reels",  label: "Planned Reels",  uom: "reels" },
			{ key: "planned_sheets", label: "Planned Sheets", uom: "sheets" },
		],
		actual: [{ key: "actual_sheets", label: "Actual Sheets", uom: "sheets" }],
	},
	collation: {
		planned: [{ key: "planned_qty",    label: "Planned Sets",   uom: "sets" }],
		actual:  [{ key: "actual_qty",     label: "Actual Sets",    uom: "sets" }],
	},
	slitting: {
		planned: [{ key: "planned_qty",    label: "Planned Rolls",  uom: "rolls" }],
		actual:  [{ key: "actual_qty",     label: "Actual Rolls",   uom: "rolls" }],
	},
};

// Options for the Job Card Type Select. Order matches the PSL JSON.
const JOB_CARD_DOCTYPES = [
	"Job Card Computer Paper",
	"Job Card Label",
	"Job Card Carton",
];

// PSL status values — kept in one place so the modal and the tile
// renderer agree on the option set.
const STATUS_OPTIONS = ["Draft", "Confirmed", "Cancelled"];

// Shift option values — stored on PSL/PE verbatim. Prototype form
// with the " Shift" suffix, per user direction.
const SHIFT_OPTIONS = ["Day Shift", "Evening Shift", "Night Shift"];


frappe.pages["cp_planning_board"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Production Planner"),
		single_column: true,
	});

	// Pull in page-scoped styles. Using frappe.require keeps the sheet
	// off every other desk route and lets us version the file through
	// the normal /assets/ URL.
	frappe.require(
		"/assets/production_log/css/cp_planning_board.css",
		() => new ProductionPlanner(page, wrapper),
	);
};

class ProductionPlanner {
	constructor(page, wrapper) {
		this.page = page;
		this.wrapper = wrapper;
		this.$body = $(wrapper).find(".layout-main-section");

		// Dept tab state. `Computer Paper` and `ETR / Thermal` are the
		// canonical product_line strings — match the stored Select values
		// verbatim so server calls can filter without translation.
		this.dept = "Computer Paper";

		// View state. `week` is the only view wired up in Phase 1;
		// `jobcard` and `station` become active in Phase 5.
		this.view = "week";

		// Week anchor — Monday of the week currently shown. ISO week
		// rules: Monday = day 1, Sunday = day 7.
		this.weekStart = this._mondayOf(new Date());

		// Server-derived state. `columns` is the raw response from
		// get_workstation_columns; `stages` is the grouped-by-WT view
		// the renderer consumes. `entries`/`actuals` are keyed by
		// Frappe `name` so lookups + updates are O(1).
		this.columns = [];
		this.stages = [];
		this.entries = {};
		this.actuals = {};

		this._render();
		this._bindEvents();
		this._loadAll();
	}

	// ─────────────────────────────────────────────────────────────
	// Render
	// ─────────────────────────────────────────────────────────────
	_render() {
		const weekLabel = this._formatWeekInput(this.weekStart);
		const html = `
			<div id="cp-planner-root">
				<div class="header">
					<div class="logo">
						<div class="logo-box">VCL</div>
						<div class="logo-text">
							<div class="logo-name">PRODUCTION PLANNER</div>
							<div class="logo-sub">Vimit Converters Ltd</div>
						</div>
					</div>

					<div class="h-controls">
						<button class="dept-btn active" data-dept="Computer Paper">Computer Paper</button>
						<button class="dept-btn" data-dept="ETR / Thermal">ETR / Thermal</button>

						<div class="hdiv"></div>

						<button class="view-btn active" data-view="week">Week</button>
						<button class="view-btn" data-view="jobcard">Job Card</button>
						<button class="view-btn" data-view="station">Station</button>

						<div class="hdiv"></div>

						<button class="view-btn wk-nav" data-dir="-1" title="Previous week">‹</button>
						<input type="week" class="week-input" value="${weekLabel}" />
						<button class="view-btn wk-nav" data-dir="1" title="Next week">›</button>

						<button class="print-btn">
							<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
								<polyline points="6 9 6 2 18 2 18 9"></polyline>
								<path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path>
								<rect x="6" y="14" width="12" height="8"></rect>
							</svg>
							Print Daily
						</button>
					</div>
				</div>

				<div class="body">
					<aside class="left">
						<div class="lp-head">
							<div class="lp-label">Job Cards</div>
							<input class="lp-search" placeholder="Search jobs…" />
						</div>
						<div class="lp-list" data-empty>
							<div style="padding:24px 12px;text-align:center;color:var(--text-faint);font-size:11px;">
								Job card list arrives in Phase 2.
							</div>
						</div>
						<div class="lp-foot">
							<span class="lp-count">0 jobs</span>
							<button class="btn-add-job" disabled title="Available in Phase 3">+ Add Job</button>
						</div>
					</aside>

					<section class="right">
						<div class="stage-header"></div>
						<div class="grid-wrap"></div>
					</section>
				</div>

				<div class="overlay entry-overlay" data-role="entry-overlay">
					<div class="modal">
						<div class="modal-head">
							<div>
								<div class="modal-title" data-role="modal-title">Add Entry</div>
								<div class="modal-sub" data-role="modal-sub"></div>
							</div>
							<button class="modal-close" type="button" data-role="modal-close" aria-label="Close">×</button>
						</div>

						<div class="modal-body">
							<div class="manual-note" data-role="manual-note">
								⚡ <strong>Manual entry</strong> — no job card linked. Use for maintenance, machine trials, or ad-hoc work.
							</div>

							<div class="field-row cols-2">
								<div class="field">
									<label>Job Card Type</label>
									<select data-field="job_card_doctype">
										<option value="">—</option>
										${JOB_CARD_DOCTYPES.map(
											(d) => `<option value="${d}">${d}</option>`,
										).join("")}
									</select>
								</div>
								<div class="field">
									<label>Job Card</label>
									<input type="text" data-field="job_card" placeholder="e.g. JCCP-2026-00042" />
								</div>
							</div>

							<div class="field" data-role="description-field" style="display:none;">
								<label>Description <span class="uom">(manual entries)</span></label>
								<input type="text" data-field="description" placeholder="Maintenance, machine trial, plate change…" />
							</div>

							<div class="field-row cols-3">
								<div class="field">
									<label>Stage</label>
									<input type="text" class="readonly" data-field="workstation_type" readonly />
								</div>
								<div class="field">
									<label>Workstation</label>
									<select data-field="workstation"></select>
								</div>
								<div class="field">
									<label>Date</label>
									<input type="date" data-field="date" />
								</div>
							</div>

							<div class="field-row cols-3">
								<div class="field">
									<label>Shift</label>
									<select data-field="shift">
										<option value="">—</option>
										${SHIFT_OPTIONS.map(
											(s) => `<option value="${s}">${s}</option>`,
										).join("")}
									</select>
								</div>
								<div class="field">
									<label>Operator / Assigned To</label>
									<input type="text" data-field="operator" />
								</div>
								<div class="field">
									<label>Status</label>
									<select data-field="status">
										${STATUS_OPTIONS.map(
											(s) => `<option value="${s}">${s}</option>`,
										).join("")}
									</select>
								</div>
							</div>

							<div class="divider"></div>
							<div class="section-label">Quantities</div>
							<div data-role="qty-section"></div>

							<div class="toggle-row">
								<div class="toggle-track" data-role="actual-toggle"><div class="toggle-thumb"></div></div>
								<div class="toggle-label" data-role="toggle-label">Plan only — toggle to include actuals</div>
							</div>

							<div class="field">
								<label>Notes / Issues</label>
								<textarea data-field="notes" rows="2"></textarea>
							</div>
						</div>

						<div class="modal-foot">
							<div class="foot-left">
								<button class="btn btn-danger" data-role="delete-btn" style="display:none;">Delete Entry</button>
							</div>
							<div class="foot-right">
								<button class="btn btn-ghost" data-role="cancel-btn">Cancel</button>
								<button class="btn btn-primary" data-role="save-btn">Save Entry</button>
							</div>
						</div>
					</div>
				</div>

				<div class="toast" role="status" aria-live="polite"></div>
			</div>
		`;

		this.$body.html(html);
		this.$root = this.$body.find("#cp-planner-root");
	}

	// ─────────────────────────────────────────────────────────────
	// Events (visual-only in Phase 1)
	// ─────────────────────────────────────────────────────────────
	_bindEvents() {
		// Dept tab switch
		this.$root.on("click", ".dept-btn", (e) => {
			const $btn = $(e.currentTarget);
			this.dept = $btn.data("dept");
			this.$root.find(".dept-btn").removeClass("active");
			$btn.addClass("active");
			this._onDeptChange();
		});

		// View switch. Scoped to buttons that carry `data-view` so the
		// prev/next week arrows (which share the `.view-btn` class for
		// styling) don't get captured here.
		this.$root.on("click", ".view-btn[data-view]", (e) => {
			const $btn = $(e.currentTarget);
			this.view = $btn.data("view");
			this.$root.find(".view-btn[data-view]").removeClass("active");
			$btn.addClass("active");
			this._onViewChange();
		});

		// Week picker (ISO week input)
		this.$root.on("change", ".week-input", (e) => {
			const val = e.target.value; // e.g. "2026-W17"
			if (!val) return;
			this.weekStart = this._mondayFromWeekInput(val);
			this._onWeekChange();
		});

		// Prev / next week buttons. Shift by 7 days and sync the input.
		this.$root.on("click", ".wk-nav", (e) => {
			const dir = Number($(e.currentTarget).data("dir")) || 0;
			if (!dir) return;
			this.weekStart = this._addDays(this.weekStart, dir * 7);
			this.$root.find(".week-input").val(this._formatWeekInput(this.weekStart));
			this._onWeekChange();
		});

		// Entry tile click — open modal in edit mode on the matched
		// PSL or PE.
		this.$root.on("click", ".entry-block", (e) => {
			const $tile = $(e.currentTarget);
			const name = $tile.data("name");
			const kind = $tile.data("kind"); // "plan" | "actual"
			this._openEntryModal({ mode: "edit", name, kind });
		});

		// Empty-cell "+" button. Cell context (date + stage + ws) goes
		// into the modal as pre-fill.
		this.$root.on("click", ".add-btn", (e) => {
			e.stopPropagation();
			const $btn = $(e.currentTarget);
			this._openEntryModal({
				mode: "new",
				date: $btn.data("date"),
				stageId: $btn.data("stage-id"),
				workstation: $btn.data("workstation"),
			});
		});

		// ── Modal wiring ──
		this.$root.on("click", '[data-role="modal-close"]', () => this._closeEntryModal());
		this.$root.on("click", '[data-role="cancel-btn"]', () => this._closeEntryModal());
		this.$root.on("click", ".entry-overlay", (e) => {
			// Click on the dark backdrop (but not the dialog itself) closes.
			if ($(e.target).hasClass("entry-overlay")) this._closeEntryModal();
		});
		this.$root.on("click", '[data-role="save-btn"]', () => this._saveEntry());
		this.$root.on("click", '[data-role="delete-btn"]', () => this._deleteEntry());
		this.$root.on("click", '[data-role="actual-toggle"]', () => this._toggleActual());

		// Job Card Type switch: empty means manual. Keep description
		// field + ⚡ banner in sync.
		this.$root.on("change", '[data-field="job_card_doctype"]', (e) => {
			const isManual = !$(e.currentTarget).val();
			this._setManualMode(isManual);
		});

		// Print Daily (Phase 4)
		this.$root.on("click", ".print-btn", () => {
			this.toast(__("Print Daily lands in Phase 4."), "ok");
		});
	}

	_onDeptChange() {
		this._loadAll();
	}

	_onViewChange() {
		if (this.view === "week") {
			// Re-render against current data without re-fetching.
			this._renderStageHeader();
			this._renderWeekGrid();
		} else {
			this.toast(__("{0} view lands in Phase 5.", [this.view]), "ok");
		}
	}

	_onWeekChange() {
		this._loadAll();
	}

	// ─────────────────────────────────────────────────────────────
	// frappe.call wrapper
	// ─────────────────────────────────────────────────────────────
	call(method, args = {}) {
		return frappe
			.call({
				method: `production_log.production_log.page.cp_planning_board.cp_planning_board.${method}`,
				args,
			})
			.then((r) => r && r.message)
			.catch((err) => {
				console.error(`[planner] ${method} failed`, err);
				this.toast(__("Server error — see console."), "err");
				throw err;
			});
	}

	// ─────────────────────────────────────────────────────────────
	// Toast
	// ─────────────────────────────────────────────────────────────
	toast(message, kind = "ok") {
		const $t = this.$root.find(".toast");
		$t.removeClass("ok err").addClass(kind === "err" ? "err" : "ok");
		$t.text(message).addClass("show");
		clearTimeout(this._toastTimer);
		this._toastTimer = setTimeout(() => $t.removeClass("show"), 2200);
	}

	// ─────────────────────────────────────────────────────────────
	// Date helpers
	// ─────────────────────────────────────────────────────────────
	_mondayOf(date) {
		const d = new Date(date);
		d.setHours(0, 0, 0, 0);
		const day = d.getDay(); // 0=Sun..6=Sat
		const diff = day === 0 ? -6 : 1 - day;
		d.setDate(d.getDate() + diff);
		return d;
	}

	_formatWeekInput(mondayDate) {
		// <input type="week"> uses ISO "YYYY-Www" format.
		const d = new Date(mondayDate);
		d.setHours(0, 0, 0, 0);
		// Thursday in current week decides ISO year+week
		d.setDate(d.getDate() + 3 - ((d.getDay() + 6) % 7));
		const year = d.getFullYear();
		const weekOneStart = new Date(year, 0, 4);
		weekOneStart.setDate(
			weekOneStart.getDate() + 3 - ((weekOneStart.getDay() + 6) % 7),
		);
		const week = 1 + Math.round((d - weekOneStart) / (7 * 24 * 3600 * 1000));
		return `${year}-W${String(week).padStart(2, "0")}`;
	}

	_mondayFromWeekInput(value) {
		// Inverse of _formatWeekInput — given "YYYY-Www", return the
		// Monday of that ISO week at 00:00 local time.
		const m = /^(\d{4})-W(\d{1,2})$/.exec(value);
		if (!m) return this._mondayOf(new Date());
		const year = Number(m[1]);
		const week = Number(m[2]);
		// ISO week 1 contains Jan 4th. Find Jan 4 and walk back to its Monday.
		const jan4 = new Date(year, 0, 4);
		jan4.setHours(0, 0, 0, 0);
		const jan4Day = jan4.getDay() || 7; // 1..7 (Mon..Sun)
		const week1Monday = new Date(jan4);
		week1Monday.setDate(jan4.getDate() - (jan4Day - 1));
		const target = new Date(week1Monday);
		target.setDate(week1Monday.getDate() + (week - 1) * 7);
		return target;
	}

	_iso(date) {
		const y = date.getFullYear();
		const m = String(date.getMonth() + 1).padStart(2, "0");
		const d = String(date.getDate()).padStart(2, "0");
		return `${y}-${m}-${d}`;
	}

	_addDays(date, days) {
		const d = new Date(date);
		d.setDate(d.getDate() + days);
		return d;
	}

	_indexByName(rows) {
		const out = {};
		for (const r of rows || []) if (r && r.name) out[r.name] = r;
		return out;
	}

	_stageIdFromWT(name) {
		// Match the server's buildStageConfig: lowercase + underscore.
		return String(name || "").trim().toLowerCase().replace(/\s+/g, "_");
	}

	// ─────────────────────────────────────────────────────────────
	// Data loading
	// ─────────────────────────────────────────────────────────────
	async _loadAll() {
		this._showLoading();
		const dateFrom = this._iso(this.weekStart);
		const dateTo = this._iso(this._addDays(this.weekStart, 5)); // Mon..Sat

		try {
			const [columns, entries] = await Promise.all([
				this.call("get_workstation_columns", { product_line: this.dept }),
				this.call("get_schedule_entries", {
					date_from: dateFrom,
					date_to: dateTo,
					product_line: this.dept,
				}),
			]);

			this.columns = Array.isArray(columns) ? columns : [];
			this._buildStages();
			this.entries = this._indexByName(entries && entries.schedule);
			this.actuals = this._indexByName(entries && entries.actuals);

			this._renderStageHeader();
			this._renderWeekGrid();
		} catch (err) {
			// call() already toasted the user.
			this._showLoadError();
		}
	}

	_showLoading() {
		const $h = this.$root.find(".stage-header");
		const $g = this.$root.find(".grid-wrap");
		$h.html(
			'<div class="sh-corner">Day · Date</div>' +
			'<div style="flex:1;display:flex;align-items:center;justify-content:center;color:var(--text-faint);font-size:11px;">Loading…</div>',
		);
		$g.html(
			'<div style="padding:40px 20px;text-align:center;color:var(--text-faint);font-size:12px;">Loading…</div>',
		);
	}

	_showLoadError() {
		const $g = this.$root.find(".grid-wrap");
		$g.html(
			'<div style="padding:40px 20px;text-align:center;color:var(--red);font-size:12px;">Failed to load — see console. Try switching tab / week to retry.</div>',
		);
	}

	// ─────────────────────────────────────────────────────────────
	// Stage grouping
	// ─────────────────────────────────────────────────────────────
	_buildStages() {
		const byWT = {};
		for (const row of this.columns) {
			const wt = row.workstation_type;
			if (!byWT[wt]) {
				byWT[wt] = {
					id: this._stageIdFromWT(wt),
					name: wt,
					workstations: [],
					is_shared: row.is_shared ? 1 : 0,
				};
			}
			if (!byWT[wt].workstations.includes(row.workstation)) {
				byWT[wt].workstations.push(row.workstation);
			}
		}
		const keys = Object.keys(byWT);
		keys.sort((a, b) => {
			const ia = STAGE_ORDER.indexOf(a);
			const ib = STAGE_ORDER.indexOf(b);
			return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
		});
		this.stages = keys.map((k) => byWT[k]);
	}

	// ─────────────────────────────────────────────────────────────
	// Rendering — stage header
	// ─────────────────────────────────────────────────────────────
	_renderStageHeader() {
		const $h = this.$root.find(".stage-header");
		const parts = ['<div class="sh-corner">Day · Date</div>'];

		if (!this.stages.length) {
			parts.push(
				'<div style="flex:1;display:flex;align-items:center;justify-content:center;color:var(--text-faint);font-size:11px;">' +
					__("No workstations tagged for {0}. Add product-line tags on Workstation.", [
						frappe.utils.escape_html(this.dept),
					]) +
					"</div>",
			);
			$h.html(parts.join(""));
			return;
		}

		for (const st of this.stages) {
			const tag = TAG_BY_ID[st.id] || (st.name || "").slice(0, 3).toUpperCase();
			const tagClass = TAG_BY_ID[st.id] ? `tag-${st.id}` : "tag-na";
			const top =
				'<div class="sg-top">' +
				`<span class="sg-name">${frappe.utils.escape_html(st.name)}</span>` +
				`<span class="sg-tag ${tagClass}">${tag}</span>` +
				"</div>";

			let bottom;
			if (st.workstations.length > 1) {
				bottom =
					'<div class="sg-bottom">' +
					st.workstations
						.map(
							(w) =>
								`<div class="sg-machine" title="${frappe.utils.escape_html(
									w,
								)}">${frappe.utils.escape_html(w)}</div>`,
						)
						.join("") +
					"</div>";
			} else if (st.workstations.length === 1) {
				bottom =
					'<div class="sg-bottom"><div class="sg-single">' +
					frappe.utils.escape_html(st.workstations[0]) +
					"</div></div>";
			} else {
				bottom = '<div class="sg-bottom"><div class="sg-single" style="color:var(--text-faint);">—</div></div>';
			}

			parts.push(
				`<div class="stage-group" data-stage-id="${st.id}" data-shared="${st.is_shared}">${top}${bottom}</div>`,
			);
		}

		$h.html(parts.join(""));
	}

	// ─────────────────────────────────────────────────────────────
	// Rendering — week grid
	// ─────────────────────────────────────────────────────────────
	_renderWeekGrid() {
		const $wrap = this.$root.find(".grid-wrap");

		if (!this.stages.length) {
			$wrap.html(
				'<div style="padding:40px 20px;text-align:center;color:var(--text-faint);font-size:12px;">' +
					__("Nothing to schedule yet — tag at least one workstation with this product line.") +
					"</div>",
			);
			return;
		}

		const days = this._weekDays();
		const rows = days
			.map((day) => {
				const rowLabel =
					'<td class="row-label">' +
					`<div class="rl-main">${day.dow}</div>` +
					`<div class="rl-sub">${day.display}</div>` +
					"</td>";

				const cells = this.stages
					.map((st) => {
						if (!st.workstations.length) {
							return '<td class="grid-cell col-disabled"></td>';
						}
						return st.workstations
							.map((ws) => this._renderCell(day.iso, st, ws))
							.join("");
					})
					.join("");

				return `<tr data-date="${day.iso}">${rowLabel}${cells}</tr>`;
			})
			.join("");

		$wrap.html(`<table class="grid"><tbody>${rows}</tbody></table>`);
	}

	_renderCell(iso, stage, workstation) {
		const tiles = this._entriesIn(iso, stage.id, workstation);
		const inner =
			tiles.map((t) => this._entryTile(t, stage)).join("") +
			'<button class="add-btn" type="button"' +
			` data-date="${iso}"` +
			` data-stage-id="${stage.id}"` +
			` data-workstation="${frappe.utils.escape_html(workstation)}"` +
			' title="Add entry">+</button>';

		return (
			'<td class="grid-cell"' +
			` data-date="${iso}"` +
			` data-stage-id="${stage.id}"` +
			` data-workstation="${frappe.utils.escape_html(workstation)}">` +
			inner +
			"</td>"
		);
	}

	_entriesIn(iso, stageId, workstation) {
		const matches = [];
		const scan = (bag, kind) => {
			for (const name in bag) {
				const e = bag[name];
				if (!e) continue;
				if (String(e.date) !== iso) continue;
				if (this._stageIdFromWT(e.workstation_type) !== stageId) continue;
				if (e.workstation !== workstation) continue;
				matches.push(Object.assign({ _kind: kind }, e));
			}
		};
		scan(this.entries, "plan");
		scan(this.actuals, "actual");
		return matches;
	}

	_entryTile(entry, stage) {
		const isManual = !!entry.is_manual;
		// Class precedence: manual > actual > plan.
		const cssKind = isManual ? "manual" : entry._kind;
		const label = cssKind === "manual" ? "MANUAL" : cssKind === "actual" ? "ACTUAL" : "PLAN";

		const uomMap = UOM_BY_STAGE[stage.id] || { planned: "", actual: "" };
		let qtyVal;
		let uom;
		if (entry._kind === "actual") {
			qtyVal = stage.id === "printing" ? entry.actual_sheets : entry.actual_qty;
			uom = uomMap.actual;
		} else {
			qtyVal = stage.id === "printing" ? entry.planned_reels : entry.planned_qty;
			uom = uomMap.planned;
		}
		qtyVal = Number(qtyVal || 0);

		const shortId = isManual
			? "MANUAL"
			: entry.job_card
				? String(entry.job_card).slice(-10)
				: String(entry.name || "").slice(-8);

		const shift = entry.shift ? String(entry.shift).replace(/ Shift$/i, "") : "";
		const operator = entry.operator ? String(entry.operator) : "";
		const metaBits = [shift, operator].filter(Boolean).map(frappe.utils.escape_html).join(" · ");

		const status = entry.status
			? ` · ${frappe.utils.escape_html(entry.status)}`
			: "";

		return (
			`<div class="entry-block ${cssKind}" data-name="${frappe.utils.escape_html(entry.name)}" data-kind="${entry._kind}">` +
			'<div class="eb-top">' +
			`<span class="eb-id" title="${frappe.utils.escape_html(entry.name)}">${frappe.utils.escape_html(shortId)}</span>` +
			`<span class="eb-type">${label}${status}</span>` +
			"</div>" +
			'<div class="eb-qty">' +
			frappe.utils.format_number(qtyVal, null, 0) +
			`<span class="eb-uom">${uom}</span>` +
			"</div>" +
			(metaBits ? `<div class="eb-meta">${metaBits}</div>` : "") +
			"</div>"
		);
	}

	// ─────────────────────────────────────────────────────────────
	// Week day helpers (Mon–Sat)
	// ─────────────────────────────────────────────────────────────
	_weekDays() {
		return WEEK_DAYS.map((dow, i) => {
			const d = this._addDays(this.weekStart, i);
			const dayNum = String(d.getDate()).padStart(2, "0");
			const monShort = d.toLocaleString("en-GB", { month: "short" });
			return {
				dow,
				date: d,
				iso: this._iso(d),
				display: `${dayNum} ${monShort}`,
			};
		});
	}

	// ─────────────────────────────────────────────────────────────
	// Modal — open / close
	// ─────────────────────────────────────────────────────────────
	_openEntryModal({ mode, name, kind, date, stageId, workstation } = {}) {
		const $modal = this.$root.find(".entry-overlay");
		this._resetModalForm();

		let stage;
		let entry = null;

		if (mode === "edit" && name) {
			entry = this._lookupEntry(name, kind);
			if (!entry) {
				this.toast(__("Entry not found — reload the board."), "err");
				return;
			}
			stageId = this._stageIdFromWT(entry.workstation_type);
			stage = this.stages.find((s) => s.id === stageId);
			workstation = entry.workstation;
			date = entry.date;
		} else {
			stage = this.stages.find((s) => s.id === stageId);
		}

		if (!stage) {
			this.toast(__("Unknown stage — reload the board."), "err");
			return;
		}

		this._currentEditing = {
			mode: mode || "new",
			name: entry ? entry.name : null,
			kind: kind || (entry && entry._kind) || null,
		};

		// Header copy
		$modal.find('[data-role="modal-title"]').text(
			entry ? __("Edit Entry") : __("Add Entry"),
		);
		$modal.find('[data-role="modal-sub"]').text(
			entry
				? `${entry.name} · ${stage.name} · ${workstation}`
				: `${stage.name} · ${workstation || "—"}`,
		);
		$modal.find('[data-role="delete-btn"]').toggle(!!entry);

		// Seed form values. For a new entry we default shift=Day Shift,
		// status=Draft, date=clicked day (falls back to Monday).
		const defaults = {
			job_card_doctype: "",
			job_card: "",
			is_manual: 0,
			description: "",
			workstation_type: stage.name,
			workstation: workstation || stage.workstations[0] || "",
			date: date || this._iso(this.weekStart),
			shift: "Day Shift",
			operator: "",
			status: "Draft",
			planned_qty: "",
			planned_reels: "",
			planned_sheets: "",
			actual_qty: "",
			actual_sheets: "",
			notes: "",
		};
		const values = entry ? Object.assign({}, defaults, entry) : defaults;

		this._populateWorkstationOptions(stage.id, values.workstation);

		// Scalar fields.
		$modal.find("[data-field]").each((i, el) => {
			const $f = $(el);
			const key = $f.data("field");
			if (!(key in values)) return;
			$f.val(values[key] == null ? "" : values[key]);
		});

		// Manual mode follows the Job Card Type value (+ is_manual for
		// server-side saved entries).
		const isManual = !!values.is_manual || !values.job_card_doctype;
		this._setManualMode(isManual);

		// Actual toggle on if we're editing a PE tile or the row has
		// any actual figures recorded.
		const hasActual =
			Number(values.actual_qty || 0) > 0 ||
			Number(values.actual_sheets || 0) > 0;
		const toggleOn = this._currentEditing.kind === "actual" || hasActual;
		this._setActualToggle(toggleOn);

		this._buildQtySection(stage.id, toggleOn, values);

		$modal.addClass("open");
		setTimeout(() => {
			$modal.find('[data-field="job_card_doctype"]').trigger("focus");
		}, 50);
	}

	_closeEntryModal() {
		this.$root.find(".entry-overlay").removeClass("open");
		this._currentEditing = null;
	}

	_resetModalForm() {
		const $m = this.$root.find(".entry-overlay");
		$m.find("input, select, textarea").each((i, el) => {
			if (el.type === "checkbox" || el.type === "radio") el.checked = false;
			else el.value = "";
		});
		$m.find('[data-role="qty-section"]').empty();
		$m.find('[data-role="manual-note"]').removeClass("show");
		$m.find('[data-role="description-field"]').hide();
		$m.find('[data-role="actual-toggle"]').removeClass("on");
		$m.find('[data-role="toggle-label"]').text(
			__("Plan only — toggle to include actuals"),
		);
		$m.find('[data-field="job_card"]').prop("disabled", false);
	}

	_lookupEntry(name, kind) {
		if (kind === "actual") return this.actuals[name] || null;
		return this.entries[name] || this.actuals[name] || null;
	}

	// ─────────────────────────────────────────────────────────────
	// Modal — field helpers
	// ─────────────────────────────────────────────────────────────
	_populateWorkstationOptions(stageId, currentValue) {
		const stage = this.stages.find((s) => s.id === stageId);
		const $sel = this.$root.find('[data-field="workstation"]');
		$sel.empty();
		if (!stage) return;
		for (const ws of stage.workstations) {
			const opt = document.createElement("option");
			opt.value = ws;
			opt.textContent = ws;
			if (ws === currentValue) opt.selected = true;
			$sel.append(opt);
		}
	}

	_buildQtySection(stageId, includeActual, savedValues) {
		const cfg = STAGE_QTY[stageId] || { planned: [], actual: [] };
		const render = (f) => {
			const raw = savedValues && savedValues[f.key];
			const val =
				raw == null || raw === undefined || Number.isNaN(Number(raw))
					? ""
					: raw;
			return (
				'<div class="field">' +
				`<label>${f.label} <span class="uom">(${f.uom})</span></label>` +
				`<input type="number" step="0.01" min="0" data-field="${f.key}" value="${val}" />` +
				"</div>"
			);
		};

		const planned = cfg.planned.map(render).join("");
		const actual = includeActual ? cfg.actual.map(render).join("") : "";
		const cls = cfg.planned.length + (includeActual ? cfg.actual.length : 0) >= 3
			? "cols-3"
			: "cols-2";

		this.$root
			.find('[data-role="qty-section"]')
			.html(`<div class="field-row ${cls}">${planned}${actual}</div>`);
	}

	_setManualMode(isManual) {
		const $m = this.$root.find(".entry-overlay");
		if (isManual) {
			$m.find('[data-role="manual-note"]').addClass("show");
			$m.find('[data-role="description-field"]').show();
			$m.find('[data-field="job_card_doctype"]').val("");
			$m.find('[data-field="job_card"]').val("").prop("disabled", true);
		} else {
			$m.find('[data-role="manual-note"]').removeClass("show");
			$m.find('[data-role="description-field"]').hide();
			$m.find('[data-field="description"]').val("");
			$m.find('[data-field="job_card"]').prop("disabled", false);
		}
	}

	_setActualToggle(on) {
		const $t = this.$root.find('[data-role="actual-toggle"]');
		const $l = this.$root.find('[data-role="toggle-label"]');
		if (on) {
			$t.addClass("on");
			$l.text(__("Actual recorded"));
		} else {
			$t.removeClass("on");
			$l.text(__("Plan only — toggle to include actuals"));
		}
	}

	_toggleActual() {
		const $t = this.$root.find('[data-role="actual-toggle"]');
		const newState = !$t.hasClass("on");
		this._setActualToggle(newState);

		// Re-render the qty section preserving whatever the user typed.
		const stageId = this._stageIdFromWT(
			this.$root.find('[data-field="workstation_type"]').val(),
		);
		const savedValues = this._collectFormValues();
		this._buildQtySection(stageId, newState, savedValues);
	}

	_collectFormValues() {
		const out = {};
		this.$root.find(".entry-overlay [data-field]").each((i, el) => {
			const $f = $(el);
			const key = $f.data("field");
			let v = $f.val();
			if (el.tagName === "INPUT" && el.type === "number") {
				v = v === "" ? null : Number(v);
				if (Number.isNaN(v)) v = null;
			}
			out[key] = v;
		});
		return out;
	}

	// ─────────────────────────────────────────────────────────────
	// Modal — save
	// ─────────────────────────────────────────────────────────────
	async _saveEntry() {
		const $save = this.$root.find('[data-role="save-btn"]');
		if ($save.prop("disabled")) return;

		const values = this._collectFormValues();
		const editing = this._currentEditing || {};
		const toggleOn = this.$root
			.find('[data-role="actual-toggle"]')
			.hasClass("on");

		// Dept tab is authoritative for product_line. Stamp unconditionally.
		values.product_line = this.dept;

		// Manual-vs-job-card invariant — same rules the server-side
		// before_save enforces. Fail fast here so the user sees the
		// error without a round-trip.
		const isManual = !values.job_card_doctype;
		values.is_manual = isManual ? 1 : 0;

		if (isManual) {
			if (!String(values.description || "").trim()) {
				this.toast(__("Description is required for manual entries."), "err");
				return;
			}
			values.job_card_doctype = null;
			values.job_card = null;
		} else {
			if (!String(values.job_card || "").trim()) {
				this.toast(__("Job Card is required unless this is a manual entry."), "err");
				return;
			}
		}

		if (!values.workstation) {
			this.toast(__("Workstation is required."), "err");
			return;
		}
		if (!values.date) {
			this.toast(__("Date is required."), "err");
			return;
		}

		$save.prop("disabled", true).text(__("Saving…"));

		try {
			// Editing a PE tile directly — save as PE, don't touch PSL.
			if (editing.mode === "edit" && editing.kind === "actual") {
				const pePayload = Object.assign({}, values, { name: editing.name });
				await this.call("save_production_entry", {
					entry: JSON.stringify(pePayload),
				});
				this.toast(__("Entry updated ✓"), "ok");
				this._closeEntryModal();
				this._loadAll();
				return;
			}

			// Otherwise: save/update PSL. Strip PE-only fields first —
			// PSL doesn't have actual_qty / actual_sheets / schedule_line.
			const pslPayload = Object.assign({}, values);
			delete pslPayload.actual_qty;
			delete pslPayload.actual_sheets;
			delete pslPayload.schedule_line;

			if (editing.mode === "edit" && editing.kind === "plan" && editing.name) {
				pslPayload.name = editing.name;
			}

			const pslName = await this.call("save_schedule_entry", {
				entry: JSON.stringify(pslPayload),
			});

			// If the actual toggle is on, also create/update a PE that
			// points back at this PSL. Phase 3 always creates a new PE —
			// updating an existing linked PE requires editing its tile
			// directly.
			if (toggleOn) {
				const pePayload = Object.assign({}, values, {
					schedule_line: pslName,
				});
				delete pePayload.name;
				try {
					await this.call("save_production_entry", {
						entry: JSON.stringify(pePayload),
					});
				} catch (err) {
					this.toast(
						__("Plan saved; actual failed — see console."),
						"err",
					);
					this._closeEntryModal();
					this._loadAll();
					return;
				}
			}

			this.toast(
				editing.mode === "edit" ? __("Entry updated ✓") : __("Entry saved ✓"),
				"ok",
			);
			this._closeEntryModal();
			this._loadAll();
		} catch (err) {
			// call() already toasted.
		} finally {
			$save.prop("disabled", false).text(__("Save Entry"));
		}
	}

	// ─────────────────────────────────────────────────────────────
	// Modal — delete
	// ─────────────────────────────────────────────────────────────
	async _deleteEntry() {
		const editing = this._currentEditing || {};
		if (editing.mode !== "edit" || !editing.name) return;

		const doctype =
			editing.kind === "actual"
				? "Production Entry"
				: "Production Schedule Line";

		const confirmed = await new Promise((resolve) => {
			frappe.confirm(
				__("Delete {0} {1}? This cannot be undone.", [doctype, editing.name]),
				() => resolve(true),
				() => resolve(false),
			);
		});
		if (!confirmed) return;

		try {
			await frappe.db.delete_doc(doctype, editing.name);
			this.toast(__("Deleted"), "ok");
			this._closeEntryModal();
			this._loadAll();
		} catch (err) {
			console.error("[planner] delete failed", err);
			this.toast(__("Delete failed — see console."), "err");
		}
	}
}
