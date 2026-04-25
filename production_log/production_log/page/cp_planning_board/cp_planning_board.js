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

// Stage ordering is now driven by `Workstation Type.custom_stage_position`
// (Int field, seeded by patch_v5_5). The server returns it on every row
// from `get_workstation_columns` as `stage_position`. WTs without a
// position fall back to the sentinel 999 — they still render, just at
// the right edge until the admin assigns one. Duplicate positions are
// blocked at save time by `validate_stage_position` on the server.

// 3-letter chip label next to each stage name. Keys are the stage
// ids that `_stageIdFromWT` produces (lowercase + space→underscore).
// Hand-mapped so an id like `reel_to_reel_printing` yields `PRN`,
// not `REE`.
const TAG_BY_ID = {
	design: "DES",
	reel_to_reel_printing: "PRN",
	ruling: "RUL",
	sheeting: "SHE",
	collation: "COL",
	slitting: "SLT",
};

// UOM per stage. Reel-to-reel printing is asymmetric: planned side
// tracks reels in (the scheduler's input) + expected sheet yield,
// actual side tracks sheets out. Ruling and Sheeting default to
// `sheets` per live-site notes — confirm with Tanuj before the
// next UAT pass; swap to reams/jobs if that's how the floor counts.
const UOM_BY_STAGE = {
	design:                { planned: "days",   actual: "days" },
	reel_to_reel_printing: { planned: "reels",  actual: "sheets" },
	ruling:                { planned: "sheets", actual: "sheets" },
	sheeting:              { planned: "sheets", actual: "sheets" },
	collation:             { planned: "sets",   actual: "sets" },
	slitting:              { planned: "rolls",  actual: "rolls" },
};

// Day-of-week labels for the Week view (Mon–Sat, six rows — matches
// the prototype). Sunday is treated as non-working.
const WEEK_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

// Qty field definitions per stage. `key` matches the DocType fieldname
// on PSL / PE, so the same map drives both the modal form and the
// save payload. Reel-to-reel printing is asymmetric: two planned
// fields (reels in, sheets out) and one actual field (sheets). Ruling
// and Sheeting use single planned/actual sheet fields pending UOM
// confirmation.
const STAGE_QTY = {
	design: {
		planned: [{ key: "planned_qty",    label: "Planned Days",   uom: "days" }],
		actual:  [{ key: "actual_qty",     label: "Actual Days",    uom: "days" }],
	},
	reel_to_reel_printing: {
		planned: [
			{ key: "planned_reels",  label: "Planned Reels",  uom: "reels" },
			{ key: "planned_sheets", label: "Planned Sheets", uom: "sheets" },
		],
		actual: [{ key: "actual_sheets", label: "Actual Sheets", uom: "sheets" }],
	},
	ruling: {
		planned: [{ key: "planned_sheets", label: "Planned Sheets", uom: "sheets" }],
		actual:  [{ key: "actual_sheets",  label: "Actual Sheets",  uom: "sheets" }],
	},
	sheeting: {
		planned: [{ key: "planned_sheets", label: "Planned Sheets", uom: "sheets" }],
		actual:  [{ key: "actual_sheets",  label: "Actual Sheets",  uom: "sheets" }],
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

// Left-panel Job Card doctype per planner dept. Mirrors the server's
// JOB_CARD_DOCTYPE_BY_PRODUCT_LINE. The remaining tabs render the empty
// state in the left panel, and `+ Add Job` disables itself via
// `_onAddJobClick`. Note the doctype is still `Job Card Label` even
// though the dept renamed to `Self Adhesive Label` in patch_v5_5 —
// renaming a doctype is a separate, larger change.
const JOB_CARD_DOCTYPE_BY_DEPT = {
	"Computer Paper": "Job Card Computer Paper",
	"ETR": "Job Card ETR",
	"Self Adhesive Label": "Job Card Label",
};

// Dept tabs rendered in the header, in order. Values are the exact
// product_line strings — the client sends them verbatim to the server
// in every get_workstation_columns / get_schedule_entries /
// get_job_cards / get_machine_conflicts call. `Trading` is in the
// taxonomy but has no operations stages so isn't rendered as a tab.
const PLANNER_DEPTS = [
	"Computer Paper",
	"ETR",
	"Self Adhesive Label",
	"General Stationery and Exercise Book",
	"Mono Boxes",
	"Corrugation and Carton Department",
	"R2R",
];

// Bundle version marker. Change every commit — when the planner loads
// and the browser console prints a stale version, you know the asset
// cache or Frappe Cloud rebuild hasn't picked up the newest push yet.
// Also rendered in the header so a field report can confirm which
// build they're on without opening DevTools.
const PLANNER_BUNDLE = "2026-04-25-v5_5-stage-position-print-v2";


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

		// Dept tab state. Each value is the exact `product_line` string
		// stored on PSL / PE / Workstation Product Line Tag, so server
		// calls filter without translation. Full list lives in
		// PLANNER_DEPTS at module top.
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

		// Conflict state. `conflicts` is the raw array from
		// get_machine_conflicts; `conflictByCell` maps
		// `${date}|${workstation}` -> conflict info so the renderer
		// can look up in O(1); `conflictedNames` is a Set of PSL names
		// the renderer marks with `.conflicted`.
		this.conflicts = [];
		this.conflictByCell = {};
		this.conflictedNames = new Set();

		// Left-panel Job Card state. `jobCards` is the full server
		// payload for the current dept; `jobCardFilter` is the current
		// `.lp-search` query (client-side filter only); `selectedJobCard`
		// is `{doctype, name}` when a tile is active, otherwise null.
		this.jobCards = [];
		this.jobCardFilter = "";
		this.selectedJobCard = null;

		console.info(`[planner] bundle ${PLANNER_BUNDLE}`);

		this._render();
		this._bindEvents();
		this._refreshAddJobState();
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
							<div class="logo-sub">Vimit Converters Ltd · build ${PLANNER_BUNDLE}</div>
						</div>
					</div>

					<div class="h-controls">
						${PLANNER_DEPTS.map(
							(d) =>
								`<button class="dept-btn${d === this.dept ? " active" : ""}" data-dept="${frappe.utils.escape_html(d)}">${frappe.utils.escape_html(d)}</button>`,
						).join("")}

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

						<span class="conflict-badge" data-role="conflict-badge" style="display:none;">⚠ 0 conflicts</span>
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
								Loading job cards…
							</div>
						</div>
						<div class="lp-foot">
							<span class="lp-count">0 jobs</span>
							<button class="btn-add-job" type="button">+ Add Job</button>
						</div>
					</aside>

					<section class="right">
						<div class="stage-header"></div>
						<div class="grid-wrap"></div>
					</section>
				</div>

				<div class="overlay entry-overlay" data-role="entry-overlay">
					<div class="vcl-modal">
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

				<div class="overlay day-picker-overlay" data-role="day-picker-overlay">
					<div class="vcl-modal" style="width:380px;">
						<div class="modal-head">
							<div>
								<div class="modal-title">Print Daily Sheet</div>
								<div class="modal-sub">Pick a day from this week</div>
							</div>
							<button class="modal-close" type="button" data-role="day-picker-close" aria-label="Close">×</button>
						</div>
						<div class="modal-body">
							<div class="day-picker-grid" data-role="day-grid"></div>
							<div class="divider"></div>
							<div class="section-label">Sheet type</div>
							<div class="toggle-row" style="gap:16px;font-size:12px;color:var(--text-dim);">
								<label style="display:flex;gap:6px;align-items:center;cursor:pointer;">
									<input type="radio" name="print-variant" value="blank" checked />
									Blank Actuals Sheet
								</label>
								<label style="display:flex;gap:6px;align-items:center;cursor:pointer;">
									<input type="radio" name="print-variant" value="pva" />
									Plan vs Actuals
								</label>
							</div>
							<div class="divider"></div>
							<div class="section-label">Include</div>
							<div class="toggle-row" style="gap:16px;font-size:12px;color:var(--text-dim);">
								<label style="display:flex;gap:6px;align-items:center;cursor:pointer;">
									<input type="radio" name="print-scope" value="current" checked />
									Current dept only
								</label>
								<label style="display:flex;gap:6px;align-items:center;cursor:pointer;">
									<input type="radio" name="print-scope" value="all" />
									All departments
								</label>
							</div>
						</div>
						<div class="modal-foot">
							<div class="foot-left"></div>
							<div class="foot-right">
								<button class="btn btn-ghost" type="button" data-role="day-picker-cancel">Cancel</button>
								<button class="btn btn-primary" type="button" data-role="print-confirm" disabled>Print</button>
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

		// Left-panel Job Card list — search, tile select, + Add Job.
		this.$root.on("input", ".lp-search", (e) => {
			this.jobCardFilter = (e.currentTarget.value || "").trim();
			this._renderJobCards();
		});
		this.$root.on("click", ".job-card", (e) => {
			const $c = $(e.currentTarget);
			this._onJobCardClick($c.data("name"), $c.data("doctype"));
		});
		this.$root.on("click", ".btn-add-job", () => this._onAddJobClick());

		// Print Daily — opens the day picker.
		this.$root.on("click", ".print-btn", () => this._openDayPicker());
		this.$root.on("click", '[data-role="day-picker-close"]', () => this._closeDayPicker());
		this.$root.on("click", '[data-role="day-picker-cancel"]', () => this._closeDayPicker());
		this.$root.on("click", ".day-picker-overlay", (e) => {
			if ($(e.target).hasClass("day-picker-overlay")) this._closeDayPicker();
		});
		this.$root.on("click", ".day-pick-btn", (e) => {
			this.$root.find(".day-pick-btn").removeClass("selected");
			$(e.currentTarget).addClass("selected");
			this.$root.find('[data-role="print-confirm"]').prop("disabled", false);
		});
		this.$root.on("click", '[data-role="print-confirm"]', () => this._onPrintConfirm());

		// Horizontal scroll sync. The stage header and grid body are
		// separate scroll containers, so a wide week (13+ machine
		// columns) drifts out of alignment the moment the user scrolls
		// the grid right. Sync the header's scrollLeft to track the
		// grid as the user pans.
		const $wrap = this.$root.find(".grid-wrap");
		const $header = this.$root.find(".stage-header");
		$wrap.on("scroll", () => {
			$header.scrollLeft($wrap.scrollLeft());
		});
	}

	_onDeptChange() {
		// CP job cards aren't valid on ETR entries and vice versa — drop
		// any active selection + search box before refetch so stale state
		// can't bleed into the next modal open.
		this.selectedJobCard = null;
		this.jobCardFilter = "";
		this.$root.find(".lp-search").val("");
		this._refreshAddJobState();
		this._loadAll();
	}

	_refreshAddJobState() {
		// Grey out + Add Job on dept tabs that don't have a Job Card
		// doctype yet (ETR / General Stationery / Mono Boxes /
		// Corrugation). Title attribute surfaces the reason on hover so
		// a user doesn't wonder why the button went quiet.
		const hasDoctype = !!JOB_CARD_DOCTYPE_BY_DEPT[this.dept];
		const $btn = this.$root.find(".btn-add-job");
		$btn.prop("disabled", !hasDoctype);
		$btn.attr(
			"title",
			hasDoctype
				? ""
				: __("No Job Card doctype for {0} yet.", [this.dept]),
		);
	}

	_onViewChange() {
		// All three views run against the same cached data — no
		// refetch needed, just a re-render.
		this._renderViewHeader();
		this._renderViewGrid();
	}

	_onWeekChange() {
		this._loadAll();
	}

	// ─────────────────────────────────────────────────────────────
	// frappe.call wrapper
	// ─────────────────────────────────────────────────────────────
	call(method, args = {}, opts = {}) {
		return frappe
			.call({
				method: `production_log.production_log.page.cp_planning_board.cp_planning_board.${method}`,
				args,
			})
			.then((r) => r && r.message)
			.catch((err) => {
				console.error(`[planner] ${method} failed`, err);
				if (!opts.silent) {
					this.toast(__("Server error — see console."), "err");
				}
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

		// Promise.allSettled so one failing endpoint doesn't nuke the
		// rest of the board. Each `call()` runs in silent mode — we
		// summarise at the end with the names of the methods that
		// failed, and log each rejection's stack to the console so a
		// browser session can trivially produce a diagnostic report.
		const plan = [
			["get_workstation_columns", { product_line: this.dept }],
			[
				"get_schedule_entries",
				{ date_from: dateFrom, date_to: dateTo, product_line: this.dept },
			],
			["get_machine_conflicts", { date_from: dateFrom, date_to: dateTo }],
			["get_job_cards", { product_line: this.dept }],
		];

		const settled = await Promise.allSettled(
			plan.map(([method, args]) => this.call(method, args, { silent: true })),
		);

		const failures = [];
		const pick = (i, fallback) => {
			const r = settled[i];
			if (r.status === "fulfilled") return r.value;
			failures.push(plan[i][0]);
			return fallback;
		};

		const columns = pick(0, []);
		const entries = pick(1, { schedule: [], actuals: [] });
		const conflicts = pick(2, []);
		const jobCards = pick(3, []);

		// State assignments — cheap and individually safe. A prior
		// revision wrapped the whole block in one try/catch; that
		// meant a throw in *any* render step (e.g. the grid) took
		// down `_renderJobCards` which runs last, producing the
		// observed "Loading job cards…" + "Failed to load" symptom
		// even when the JC call had succeeded. Each step now gets
		// its own try/catch so a broken grid doesn't hide the JC
		// panel, and each failure logs its stack against a named
		// step so the cause is visible in the console.
		this.columns = Array.isArray(columns) ? columns : [];
		this.entries = this._indexByName(entries && entries.schedule);
		this.actuals = this._indexByName(entries && entries.actuals);
		this.jobCards = Array.isArray(jobCards) ? jobCards : [];

		const step = (name, fn) => {
			try {
				fn.call(this);
			} catch (err) {
				failures.push(name);
				console.error(`[planner] ${name} threw`, err);
			}
		};

		step("_buildStages", this._buildStages);
		step("_indexConflicts", () =>
			this._indexConflicts(Array.isArray(conflicts) ? conflicts : []),
		);
		step("_renderViewHeader", this._renderViewHeader);
		step("_renderViewGrid", this._renderViewGrid);
		step("_renderConflictBadge", this._renderConflictBadge);
		step("_renderJobCards", this._renderJobCards);

		if (failures.length) {
			this.toast(
				__("Planner had trouble: {0}. See console.", [failures.join(", ")]),
				"err",
			);
		}
	}

	// ─────────────────────────────────────────────────────────────
	// View dispatch (Week / Job Card / Station)
	// ─────────────────────────────────────────────────────────────
	_renderViewHeader() {
		if (this.view === "station") this._renderDayHeader();
		else this._renderStageHeader();
	}

	_renderViewGrid() {
		if (this.view === "jobcard") this._renderJobCardGrid();
		else if (this.view === "station") this._renderStationGrid();
		else this._renderWeekGrid();
	}

	_indexConflicts(rows) {
		this.conflicts = rows;
		this.conflictByCell = {};
		this.conflictedNames = new Set();
		for (const c of rows) {
			const key = `${c.date}|${c.workstation}`;
			this.conflictByCell[key] = c;
			for (const n of c.psl_names || []) this.conflictedNames.add(n);
		}
	}

	_renderConflictBadge() {
		const $b = this.$root.find('[data-role="conflict-badge"]');
		const n = this.conflicts.length;
		if (!n) {
			$b.hide();
			return;
		}
		$b.text(`⚠ ${n} conflict${n === 1 ? "" : "s"}`).show();
	}

	// ─────────────────────────────────────────────────────────────
	// Left-panel — Job Card tiles
	// ─────────────────────────────────────────────────────────────
	_renderJobCards() {
		const $list = this.$root.find(".lp-list");
		const $count = this.$root.find(".lp-count");
		const filter = (this.jobCardFilter || "").toLowerCase();
		const rows = filter
			? this.jobCards.filter((jc) => this._jobCardMatches(jc, filter))
			: this.jobCards;

		$count.text(`${rows.length} job${rows.length === 1 ? "" : "s"}`);

		if (!rows.length) {
			$list.attr("data-empty", "");
			const msg = filter
				? __("No jobs match your search.")
				: __("No job cards for {0}.", [frappe.utils.escape_html(this.dept)]);
			$list.html(
				`<div style="padding:24px 12px;text-align:center;color:var(--text-faint);font-size:11px;">${msg}</div>`,
			);
			return;
		}

		$list.removeAttr("data-empty");
		const sel = this.selectedJobCard;
		const html = rows
			.map((jc) => {
				const badgeKey = jc.badge || "open";
				const cardClass = `s-${badgeKey}`;
				const badgeText = badgeKey.toUpperCase();
				const isSelected =
					sel && sel.name === jc.name && sel.doctype === jc.doctype;
				const name = frappe.utils.escape_html(jc.name || "");
				const cust = frappe.utils.escape_html(jc.customer || "");
				const spec = frappe.utils.escape_html(jc.customer_product_spec || "");
				return `
					<div class="job-card ${cardClass}${isSelected ? " selected" : ""}"
						data-name="${name}"
						data-doctype="${frappe.utils.escape_html(jc.doctype || "")}">
						<div class="jc-row">
							<div class="jc-id">${name}</div>
							<span class="jc-badge badge-${badgeKey}">${badgeText}</span>
						</div>
						<div class="jc-cust">${cust || "—"}</div>
						<div class="jc-meta">${spec || "&nbsp;"}</div>
					</div>
				`;
			})
			.join("");
		$list.html(html);
	}

	_jobCardMatches(jc, filterLower) {
		return (
			(jc.name || "").toLowerCase().includes(filterLower) ||
			(jc.customer || "").toLowerCase().includes(filterLower) ||
			(jc.customer_product_spec || "")
				.toLowerCase()
				.includes(filterLower)
		);
	}

	_onJobCardClick(name, doctype) {
		if (!name || !doctype) return;
		const already =
			this.selectedJobCard &&
			this.selectedJobCard.name === name &&
			this.selectedJobCard.doctype === doctype;
		this.selectedJobCard = already ? null : { name, doctype };
		this._renderJobCards();
	}

	_onAddJobClick() {
		const dt = JOB_CARD_DOCTYPE_BY_DEPT[this.dept];
		if (!dt) {
			this.toast(
				__("No Job Card doctype mapped for {0}.", [this.dept]),
				"err",
			);
			return;
		}
		// New tab so the planner keeps its week / selection state while
		// the user creates the Job Card.
		const slug = dt.toLowerCase().replace(/\s+/g, "-");
		window.open(`/app/${slug}/new`, "_blank", "noopener");
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
					// `stage_position` is the Int field on Workstation
					// Type seeded by patch_v5_5. Server falls back to
					// 999 for unset rows; we mirror that on a missing
					// payload so the column still renders, just last.
					position: Number.isFinite(Number(row.stage_position))
						? Number(row.stage_position)
						: 999,
				};
			}
			if (!byWT[wt].workstations.includes(row.workstation)) {
				byWT[wt].workstations.push(row.workstation);
			}
		}
		const stages = Object.values(byWT);
		stages.sort((a, b) => {
			if (a.position !== b.position) return a.position - b.position;
			return String(a.name).localeCompare(String(b.name));
		});
		this.stages = stages;
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
		const conflict = this.conflictByCell[`${iso}|${workstation}`];
		const cellClass = conflict ? "grid-cell conflict" : "grid-cell";

		let chip = "";
		if (conflict) {
			const lines = (conflict.product_lines || []).join(" + ");
			chip =
				'<div class="conflict-chip">' +
				'<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
				'<path d="M12 9v4"></path><path d="M12 17h.01"></path>' +
				'<path d="M10.3 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>' +
				"</svg>" +
				`<span>Double-booked · ${frappe.utils.escape_html(lines)}</span>` +
				"</div>";
		}

		const inner =
			tiles.map((t) => this._entryTile(t, stage)).join("") +
			chip +
			'<button class="add-btn" type="button"' +
			` data-date="${iso}"` +
			` data-stage-id="${stage.id}"` +
			` data-workstation="${frappe.utils.escape_html(workstation)}"` +
			' title="Add entry">+</button>';

		return (
			`<td class="${cellClass}"` +
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
		const fmt = (v) => Math.round(Number(v || 0)).toLocaleString("en-IN");

		// Composite qty string. Reel-to-reel printing carries both reels
		// AND sheets on the plan side; the actual side carries just
		// sheets. Every other stage has a single planned_qty / actual_qty.
		let qtyHtml;
		if (stage.id === "reel_to_reel_printing") {
			if (entry._kind === "actual") {
				qtyHtml = `${fmt(entry.actual_sheets)}<span class="eb-uom">sheets</span>`;
			} else {
				qtyHtml =
					`${fmt(entry.planned_reels)}<span class="eb-uom">reels</span>` +
					` · ${fmt(entry.planned_sheets)}<span class="eb-uom">sheets</span>`;
			}
		} else {
			const v = entry._kind === "actual" ? entry.actual_qty : entry.planned_qty;
			const u = entry._kind === "actual" ? uomMap.actual : uomMap.planned;
			qtyHtml = `${fmt(v)}<span class="eb-uom">${u}</span>`;
		}

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

		const conflictClass = this.conflictedNames.has(entry.name)
			? " conflicted"
			: "";

		return (
			`<div class="entry-block ${cssKind}${conflictClass}" data-name="${frappe.utils.escape_html(entry.name)}" data-kind="${entry._kind}">` +
			'<div class="eb-top">' +
			`<span class="eb-id" title="${frappe.utils.escape_html(entry.name)}">${frappe.utils.escape_html(shortId)}</span>` +
			`<span class="eb-type">${label}${status}</span>` +
			"</div>" +
			'<div class="eb-qty">' +
			qtyHtml +
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
		// status=Draft, date=clicked day (falls back to Monday). If the
		// user has a job tile selected in the left panel, pre-fill the
		// Job Card Type + Job Card — the dept switch always clears the
		// selection, so the tile cannot mismatch the current dept.
		const preJc = !entry ? this.selectedJobCard : null;
		const defaults = {
			job_card_doctype: preJc ? preJc.doctype : "",
			job_card: preJc ? preJc.name : "",
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
			await this._loadAll();
			this._checkPostSaveConflict(pslName, values.workstation, values.date);
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

	// ─────────────────────────────────────────────────────────────
	// Conflicts — post-save detection
	// ─────────────────────────────────────────────────────────────
	_checkPostSaveConflict(pslName, workstation, date) {
		if (!pslName) return;
		// Prefer a conflict row that actually lists the PSL we just
		// saved. Fall back to (date, workstation) in case the server
		// name didn't round-trip cleanly.
		let match = this.conflicts.find((c) =>
			(c.psl_names || []).includes(pslName),
		);
		if (!match && date && workstation) {
			match = this.conflictByCell[`${date}|${workstation}`];
		}
		if (!match) return;

		const others = (match.product_lines || []).filter((pl) => pl !== this.dept);
		const othersLabel = others.length ? others.join(", ") : match.product_lines.join(", ");
		this.toast(
			__("⚠ Machine conflict: {0} is also booked for {1} on {2}.", [
				match.workstation,
				othersLabel,
				match.date,
			]),
			"err",
		);
	}

	// ─────────────────────────────────────────────────────────────
	// Print — day picker
	// ─────────────────────────────────────────────────────────────
	_openDayPicker() {
		const $overlay = this.$root.find(".day-picker-overlay");
		const $grid = this.$root.find('[data-role="day-grid"]');
		const todayIso = this._iso(new Date());

		// Entry counts per day — simple O(entries) pass keyed by date.
		const countByDate = {};
		const bump = (d) => {
			if (!d) return;
			countByDate[d] = (countByDate[d] || 0) + 1;
		};
		for (const name in this.entries) bump(this.entries[name].date);
		for (const name in this.actuals) bump(this.actuals[name].date);

		const days = this._weekDays();
		$grid.html(
			days
				.map((d) => {
					const has = (countByDate[d.iso] || 0) > 0 ? "has-entries" : "";
					const today = d.iso === todayIso ? "today" : "";
					return (
						`<button type="button" class="day-pick-btn ${has} ${today}" data-iso="${d.iso}">` +
						`<div class="dpb-day">${d.dow}</div>` +
						`<div class="dpb-date">${d.display}</div>` +
						`<div class="dpb-dot"></div>` +
						"</button>"
					);
				})
				.join(""),
		);

		// Reset state.
		this.$root.find('[data-role="print-confirm"]').prop("disabled", true);
		this.$root.find('input[name="print-scope"][value="current"]').prop("checked", true);
		this.$root.find('input[name="print-variant"][value="blank"]').prop("checked", true);

		$overlay.addClass("open");
	}

	_closeDayPicker() {
		this.$root.find(".day-picker-overlay").removeClass("open");
	}

	async _onPrintConfirm() {
		const $sel = this.$root.find(".day-pick-btn.selected");
		if (!$sel.length) {
			this.toast(__("Pick a day."), "err");
			return;
		}
		const iso = $sel.data("iso");
		const scope = this.$root
			.find('input[name="print-scope"]:checked')
			.val();
		const variant = this.$root
			.find('input[name="print-variant"]:checked')
			.val() || "blank";
		const depts = scope === "all" ? PLANNER_DEPTS.slice() : [this.dept];

		const $btn = this.$root.find('[data-role="print-confirm"]');
		$btn.prop("disabled", true).text(__("Loading…"));

		try {
			let html;
			if (variant === "pva") {
				const data = await this.call("get_plan_vs_actuals", {
					date: iso,
					depts: JSON.stringify(depts),
				});
				html = this._buildPlanVsActualsHTML(iso, depts, data || {});
			} else {
				const data = await this.call("get_daily_schedule", {
					date: iso,
					depts: JSON.stringify(depts),
				});
				html = this._buildBlankActualsHTML(iso, depts, data || {});
			}
			this._closeDayPicker();
			this._openPrintWindow(iso, html);
		} catch (err) {
			// call() already toasted.
		} finally {
			$btn.prop("disabled", false).text(__("Print"));
		}
	}

	// ─────────────────────────────────────────────────────────────
	// Print — HTML generator + window opener
	// ─────────────────────────────────────────────────────────────
	_openPrintWindow(iso, html) {
		// Use document.write directly on a blank popup rather than a
		// blob: URL. Frappe Cloud's CSP used to kill blob: navigation
		// and some browsers silently swallow blob: popups. Writing
		// straight into the child document is more portable.
		// No third arg — we need to keep opener access so we can
		// document.write() into the child.
		const win = window.open("", "_blank");
		if (!win) {
			// Popup genuinely blocked — fall back to a Blob download so
			// the user can still print manually.
			const blob = new Blob([html], { type: "text/html" });
			const url = URL.createObjectURL(blob);
			const a = document.createElement("a");
			a.href = url;
			a.download = `production-schedule-${iso}.html`;
			a.style.display = "none";
			document.body.appendChild(a);
			a.click();
			document.body.removeChild(a);
			setTimeout(() => URL.revokeObjectURL(url), 5000);
			this.toast(
				__("Popup blocked — schedule downloaded. Open + print manually."),
				"err",
			);
			return;
		}

		try {
			win.document.open();
			win.document.write(html);
			win.document.close();
		} catch (e) {
			console.error("[planner] print window write failed", e);
			this.toast(__("Print failed — see console."), "err");
			return;
		}

		const tryPrint = () => {
			try {
				win.focus();
				win.print();
			} catch (e) {
				console.warn("[planner] auto-print failed", e);
			}
		};
		if (win.document.readyState === "complete") {
			setTimeout(tryPrint, 250);
		} else {
			win.addEventListener("load", () => setTimeout(tryPrint, 250));
		}
	}

	// Shared print shell. Returns a fully-formed HTML document with
	// VCL header, footer sign-off block, and inlined styles. The
	// Blank Actuals and Plan vs Actuals builders both call into this.
	_buildPrintShell({ iso, title, subtitle, sections }) {
		const esc = frappe.utils.escape_html;
		const dateObj = new Date(iso + "T00:00:00");
		const dayName = dateObj.toLocaleString("en-GB", { weekday: "long" });
		const dateDisplay = dateObj.toLocaleString("en-GB", {
			weekday: "long",
			day: "2-digit",
			month: "long",
			year: "numeric",
		});
		const timestamp = new Date().toLocaleString("en-GB");

		return (
			"<!doctype html>" +
			'<html lang="en"><head>' +
			'<meta charset="utf-8" />' +
			`<title>${esc(title)} — ${dateDisplay}</title>` +
			"<style>" +
			"@page { size: A4 landscape; margin: 10mm; }" +
			"* { box-sizing: border-box; }" +
			"body { font-family: Arial, Helvetica, sans-serif; font-size: 10pt; color: #000; margin: 0; padding: 0; }" +
			".hdr { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #2B3990; padding-bottom: 6pt; margin-bottom: 10pt; }" +
			".hdr-left { display: flex; gap: 10pt; align-items: center; }" +
			".logo-box { width: 44pt; height: 30pt; background: #2B3990; color: #fff; font-weight: 700; font-size: 10pt; display: flex; align-items: center; justify-content: center; border-radius: 3pt; }" +
			".hdr-title { font-size: 14pt; font-weight: 700; color: #2B3990; }" +
			".hdr-sub { font-size: 10pt; color: #333; }" +
			".hdr-right { text-align: right; font-size: 9pt; color: #555; }" +
			".dept-title { background: #eef0fa; border-left: 4pt solid #2B3990; padding: 5pt 10pt; margin: 10pt 0 4pt; font-weight: 700; font-size: 12pt; color: #2B3990; }" +
			".sched-table { width: 100%; border-collapse: collapse; margin-bottom: 8pt; }" +
			".sched-table th, .sched-table td { border: 0.5pt solid #888; padding: 4pt 6pt; text-align: left; vertical-align: top; font-size: 9pt; }" +
			".sched-table th { background: #f3f4f8; font-weight: 700; font-size: 9pt; text-transform: uppercase; letter-spacing: 0.5pt; color: #444; }" +
			".blank-cell { min-height: 18pt; }" +
			".signoff-cell { width: 60pt; min-height: 22pt; }" +
			".jc-id { font-weight: 600; }" +
			".jc-sub { font-size: 8pt; color: #555; margin-top: 1pt; }" +
			".variance-cell { font-weight: 700; text-align: right; }" +
			".variance-good   { background: #e6f7ef; color: #0e9e5a; }" +
			".variance-warn   { background: #fff5e0; color: #b97300; }" +
			".variance-bad    { background: #fde7e7; color: #b8211d; }" +
			".variance-na     { color: #888; }" +
			".signoff-block { display: flex; justify-content: space-between; gap: 20pt; margin-top: 18pt; padding-top: 8pt; border-top: 1pt solid #888; }" +
			".signoff-line { flex: 1; }" +
			".signoff-line .label { font-size: 9pt; color: #444; margin-bottom: 18pt; }" +
			".signoff-line .rule { border-bottom: 0.5pt solid #000; }" +
			".footer-note { margin-top: 10pt; font-size: 8pt; color: #888; text-align: center; }" +
			"</style>" +
			"</head><body>" +
			'<div class="hdr">' +
			'<div class="hdr-left">' +
			'<div class="logo-box">VCL</div>' +
			"<div>" +
			`<div class="hdr-title">Vimit Converters Ltd · ${esc(title)}</div>` +
			`<div class="hdr-sub">${esc(dayName)} · ${esc(dateDisplay)}</div>` +
			"</div>" +
			"</div>" +
			'<div class="hdr-right">' +
			`<div><strong>${esc(subtitle)}</strong></div>` +
			`<div>Printed ${esc(timestamp)}</div>` +
			"</div>" +
			"</div>" +
			sections +
			'<div class="signoff-block">' +
			'<div class="signoff-line"><div class="label">Production Manager Sign-off</div><div class="rule"></div></div>' +
			'<div class="signoff-line"><div class="label">Floor Supervisor Sign-off</div><div class="rule"></div></div>' +
			'<div class="signoff-line"><div class="label">Date &amp; Time</div><div class="rule"></div></div>' +
			"</div>" +
			'<div class="footer-note">Vimit Converters Ltd · Production Planner</div>' +
			"</body></html>"
		);
	}

	// Renders the Job Card cell (id + customer / spec, or MANUAL +
	// description) — shared between both print variants.
	_renderJobCardCell(row) {
		const esc = frappe.utils.escape_html;
		if (row.is_manual) {
			return `<em>MANUAL: ${esc(row.description || "")}</em>`;
		}
		const id = esc(row.job_card || "");
		const bits = [];
		if (row.customer) bits.push(esc(row.customer));
		if (row.customer_product_spec) bits.push(esc(row.customer_product_spec));
		const sub = bits.length
			? `<div class="jc-sub">${bits.join(" · ")}</div>`
			: "";
		return `<div class="jc-id">${id}</div>${sub}`;
	}

	// Format a planned-qty cell respecting per-stage UOM. Used by both
	// print variants.
	_formatPlannedQty(row) {
		const stageId = this._stageIdFromWT(row.workstation_type);
		const uomMap = UOM_BY_STAGE[stageId] || { planned: "" };
		if (stageId === "reel_to_reel_printing") {
			return `${Number(row.planned_reels || 0)} reels / ${Number(row.planned_sheets || 0)} sheets`;
		}
		return `${Number(row.planned_qty || 0)} ${uomMap.planned}`;
	}

	// Variant 1: Blank Actuals Sheet. Same per-day data as the legacy
	// print path, but the cells the floor fills in (Actual Qty,
	// Operator, Notes, Sign-off) come out blank.
	_buildBlankActualsHTML(iso, depts, dataByDept) {
		const esc = frappe.utils.escape_html;

		const renderRow = (row) => {
			const stage = `${esc(row.workstation_type || "")} · ${esc(row.workstation || "")}`;
			const jc = this._renderJobCardCell(row);
			const planned = this._formatPlannedQty(row);
			const shift = esc(row.shift || "");
			return (
				"<tr>" +
				`<td>${stage}</td>` +
				`<td>${jc}</td>` +
				`<td>${planned}</td>` +
				`<td>${shift}</td>` +
				'<td class="blank-cell"></td>' +  // Actual Qty (blank)
				'<td class="blank-cell"></td>' +  // Operator (blank)
				'<td class="blank-cell"></td>' +  // Notes (blank)
				'<td class="signoff-cell"></td>' +
				"</tr>"
			);
		};

		const renderDeptSection = (dept) => {
			const rows = dataByDept[dept] || [];
			const body = rows.length
				? rows.map(renderRow).join("")
				: '<tr><td colspan="8" style="text-align:center;color:#888;padding:12pt;">No scheduled entries.</td></tr>';
			return (
				`<div class="dept-title">${esc(dept)}</div>` +
				'<table class="sched-table">' +
				"<thead><tr>" +
				"<th>Stage / Machine</th>" +
				"<th>Job Card</th>" +
				"<th>Planned Qty</th>" +
				"<th>Shift</th>" +
				"<th>Actual Qty</th>" +
				"<th>Operator</th>" +
				"<th>Notes</th>" +
				"<th>Sign-off</th>" +
				"</tr></thead>" +
				`<tbody>${body}</tbody>` +
				"</table>"
			);
		};

		return this._buildPrintShell({
			iso,
			title: "Blank Actuals Sheet",
			subtitle: "Daily Floor Sheet (Blank Actuals)",
			sections: depts.map(renderDeptSection).join(""),
		});
	}

	// Variant 2: Plan vs Actuals. Server-aggregated PE rows are joined
	// onto the PSL spine; the Variance column is colour-coded.
	_buildPlanVsActualsHTML(iso, depts, dataByDept) {
		const esc = frappe.utils.escape_html;

		// Decide which actual total to show against which planned
		// baseline. Mirrors the server's baseline-picking logic in
		// `get_plan_vs_actuals`.
		const formatActual = (row) => {
			const planned_sheets = Number(row.planned_sheets || 0);
			const actual_sheets = Number(row.actual_sheets_total || 0);
			const actual_qty = Number(row.actual_qty_total || 0);
			const stageId = this._stageIdFromWT(row.workstation_type);
			const uomMap = UOM_BY_STAGE[stageId] || { actual: "" };
			if (planned_sheets > 0) {
				return `${actual_sheets} sheets`;
			}
			return `${actual_qty} ${uomMap.actual || ""}`.trim();
		};

		const varianceCell = (row) => {
			const v = row.variance_pct;
			if (v === null || v === undefined) {
				return '<td class="variance-cell variance-na">—</td>';
			}
			const abs = Math.abs(v);
			let cls = "variance-good";
			if (abs > 15) cls = "variance-bad";
			else if (abs > 5) cls = "variance-warn";
			const sign = v > 0 ? "+" : "";
			return `<td class="variance-cell ${cls}">${sign}${v.toFixed(1)}%</td>`;
		};

		const renderRow = (row) => {
			const stage = `${esc(row.workstation_type || "")} · ${esc(row.workstation || "")}`;
			const jc = this._renderJobCardCell(row);
			const planned = this._formatPlannedQty(row);
			const actual = esc(formatActual(row));
			const operator = esc(row.operator || "");
			const notes = esc(row.notes || "");
			return (
				"<tr>" +
				`<td>${stage}</td>` +
				`<td>${jc}</td>` +
				`<td>${planned}</td>` +
				`<td>${actual}</td>` +
				varianceCell(row) +
				`<td>${operator}</td>` +
				`<td>${notes}</td>` +
				"</tr>"
			);
		};

		const renderDeptSection = (dept) => {
			const rows = dataByDept[dept] || [];
			const body = rows.length
				? rows.map(renderRow).join("")
				: '<tr><td colspan="7" style="text-align:center;color:#888;padding:12pt;">No scheduled entries.</td></tr>';
			return (
				`<div class="dept-title">${esc(dept)}</div>` +
				'<table class="sched-table">' +
				"<thead><tr>" +
				"<th>Stage / Machine</th>" +
				"<th>Job Card</th>" +
				"<th>Planned</th>" +
				"<th>Actual</th>" +
				"<th>Variance</th>" +
				"<th>Operator</th>" +
				"<th>Notes</th>" +
				"</tr></thead>" +
				`<tbody>${body}</tbody>` +
				"</table>"
			);
		};

		return this._buildPrintShell({
			iso,
			title: "Plan vs Actuals",
			subtitle: "Daily Plan vs Actuals",
			sections: depts.map(renderDeptSection).join(""),
		});
	}

	// ─────────────────────────────────────────────────────────────
	// Station view — day-column header (Mon–Sat)
	// ─────────────────────────────────────────────────────────────
	_renderDayHeader() {
		const $h = this.$root.find(".stage-header");
		const days = this._weekDays();
		const parts = ['<div class="sh-corner">Stage · Machine</div>'];
		for (const d of days) {
			parts.push(
				'<div class="stage-group" style="flex:1;min-width:120px;">' +
				`<div class="sg-top"><span class="sg-name">${d.dow}</span></div>` +
				`<div class="sg-bottom"><div class="sg-single">${d.display}</div></div>` +
				"</div>",
			);
		}
		$h.html(parts.join(""));
	}

	// ─────────────────────────────────────────────────────────────
	// Job Card view — rows per job card, columns per stage×machine
	// ─────────────────────────────────────────────────────────────
	_renderJobCardGrid() {
		const $wrap = this.$root.find(".grid-wrap");

		if (!this.stages.length) {
			$wrap.html(
				'<div style="padding:40px 20px;text-align:center;color:var(--text-faint);font-size:12px;">' +
					__("No columns available for {0}.", [frappe.utils.escape_html(this.dept)]) +
					"</div>",
			);
			return;
		}

		const jobs = this._uniqueJobs();
		if (!jobs.length) {
			$wrap.html(
				'<div style="padding:40px 20px;text-align:center;color:var(--text-faint);font-size:12px;">' +
					__("No job cards scheduled this week. Switch to Week view and add some.") +
					"</div>",
			);
			return;
		}

		const rows = jobs
			.map((job) => {
				const label =
					'<td class="row-label">' +
					`<div class="rl-main">${frappe.utils.escape_html(job.label)}</div>` +
					`<div class="rl-sub">${frappe.utils.escape_html(job.sub)}</div>` +
					"</td>";

				const cells = this.stages
					.map((st) => {
						if (!st.workstations.length) {
							return '<td class="grid-cell col-disabled"></td>';
						}
						return st.workstations
							.map((ws) => this._renderCellForJob(st, ws, job))
							.join("");
					})
					.join("");

				return `<tr>${label}${cells}</tr>`;
			})
			.join("");

		$wrap.html(`<table class="grid"><tbody>${rows}</tbody></table>`);
	}

	_uniqueJobs() {
		// Index the current-dept Job Cards so we can decorate each row
		// with the customer name + product spec instead of the bare
		// doctype name. Missing entries fall back to the doctype so
		// cross-dept leftovers still render something sensible.
		const jcIndex = {};
		for (const jc of this.jobCards || []) {
			if (jc && jc.name) jcIndex[jc.name] = jc;
		}

		const jobMap = new Map();
		const bump = (e) => {
			if (e.is_manual) {
				if (!jobMap.has("__manual__")) {
					jobMap.set("__manual__", {
						key: "__manual__",
						label: "MANUAL",
						sub: __("Ad-hoc / maintenance"),
						isManual: true,
					});
				}
				return;
			}
			if (!e.job_card) return;
			if (!jobMap.has(e.job_card)) {
				const jc = jcIndex[e.job_card];
				const subBits = [];
				if (jc && jc.customer) subBits.push(jc.customer);
				if (jc && jc.customer_product_spec) subBits.push(jc.customer_product_spec);
				const sub = subBits.length
					? subBits.join(" · ")
					: e.job_card_doctype || "";
				jobMap.set(e.job_card, {
					key: e.job_card,
					label: e.job_card,
					sub,
					isManual: false,
				});
			}
		};
		for (const name in this.entries) bump(this.entries[name]);
		for (const name in this.actuals) bump(this.actuals[name]);

		// Stable order: MANUAL last, real job cards alphabetical.
		const jobs = [...jobMap.values()].sort((a, b) => {
			if (a.isManual && !b.isManual) return 1;
			if (!a.isManual && b.isManual) return -1;
			return String(a.key).localeCompare(String(b.key));
		});
		return jobs;
	}

	_renderCellForJob(stage, workstation, job) {
		const tiles = this._entriesMatchingJob(stage.id, workstation, job);
		const inner = tiles.length
			? tiles.map((t) => this._entryTile(t, stage)).join("")
			: '<div style="color:var(--text-faint);text-align:center;font-size:10px;padding:4px;">—</div>';

		// No add button here: Job Card view has no date context (rows
		// are jobs, not days). Users add entries from Week view.
		return '<td class="grid-cell">' + inner + "</td>";
	}

	_entriesMatchingJob(stageId, workstation, job) {
		const out = [];
		const scan = (bag, kind) => {
			for (const name in bag) {
				const e = bag[name];
				if (!e) continue;
				if (this._stageIdFromWT(e.workstation_type) !== stageId) continue;
				if (e.workstation !== workstation) continue;
				if (job.isManual) {
					if (!e.is_manual) continue;
				} else {
					if (e.is_manual) continue;
					if (e.job_card !== job.key) continue;
				}
				out.push(Object.assign({ _kind: kind }, e));
			}
		};
		scan(this.entries, "plan");
		scan(this.actuals, "actual");
		out.sort((a, b) => String(a.date || "").localeCompare(String(b.date || "")));
		return out;
	}

	// ─────────────────────────────────────────────────────────────
	// Station view — rows per stage×machine, columns per day
	// ─────────────────────────────────────────────────────────────
	_renderStationGrid() {
		const $wrap = this.$root.find(".grid-wrap");

		if (!this.stages.length) {
			$wrap.html(
				'<div style="padding:40px 20px;text-align:center;color:var(--text-faint);font-size:12px;">' +
					__("No workstations tagged for {0}.", [frappe.utils.escape_html(this.dept)]) +
					"</div>",
			);
			return;
		}

		const days = this._weekDays();
		const rows = [];
		for (const st of this.stages) {
			for (const ws of st.workstations) {
				const label =
					'<td class="row-label">' +
					`<div class="rl-main">${frappe.utils.escape_html(ws)}</div>` +
					`<div class="rl-sub">${frappe.utils.escape_html(st.name)}</div>` +
					"</td>";

				const cells = days
					.map((d) => this._renderCell(d.iso, st, ws))
					.join("");
				rows.push(`<tr>${label}${cells}</tr>`);
			}
		}

		if (!rows.length) {
			$wrap.html(
				'<div style="padding:40px 20px;text-align:center;color:var(--text-faint);font-size:12px;">' +
					__("No workstations available.") +
					"</div>",
			);
			return;
		}

		$wrap.html(`<table class="grid"><tbody>${rows.join("")}</tbody></table>`);
	}
}
