/*
 * Production Planner — client controller (Phase 1 scaffold).
 *
 * This file will grow in phases: Phase 1 is just the boot, header, and
 * empty frames. Columns, entries, the modal, conflict detection, and
 * the print flow arrive in Phases 2–4.
 */

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

		this._render();
		this._bindEvents();
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

						<input type="week" class="week-input" value="${weekLabel}" />

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
						<div class="stage-header">
							<div class="sh-corner">Day · Date</div>
							<div style="flex:1;display:flex;align-items:center;justify-content:center;color:var(--text-faint);font-size:11px;">
								Stages load in Phase 2
							</div>
						</div>
						<div class="grid-wrap">
							<div style="padding:40px 20px;text-align:center;color:var(--text-faint);font-size:12px;">
								<div style="font-size:24px;margin-bottom:8px;">📅</div>
								Week grid renders here in Phase 2 once <code>get_workstation_columns</code> and <code>get_schedule_entries</code> are wired in.
							</div>
						</div>
					</section>
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

		// View switch
		this.$root.on("click", ".view-btn", (e) => {
			const $btn = $(e.currentTarget);
			this.view = $btn.data("view");
			this.$root.find(".view-btn").removeClass("active");
			$btn.addClass("active");
			this._onViewChange();
		});

		// Week picker
		this.$root.on("change", ".week-input", (e) => {
			const val = e.target.value; // e.g. "2026-W17"
			if (!val) return;
			this.weekStart = this._mondayFromWeekInput(val);
			this._onWeekChange();
		});

		// Print Daily (Phase 4)
		this.$root.on("click", ".print-btn", () => {
			this.toast(__("Print Daily lands in Phase 4."), "ok");
		});
	}

	_onDeptChange() {
		// Real reload wires in Phase 2. For now just confirm the switch.
		this.toast(`${this.dept} · Phase 2 will reload columns here.`, "ok");
	}

	_onViewChange() {
		this.toast(`View: ${this.view} · rendering lands in Phase 2/5.`, "ok");
	}

	_onWeekChange() {
		this.toast(`Week: ${this._formatWeekInput(this.weekStart)}`, "ok");
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
}
