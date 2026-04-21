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

		// Entry tile click — opens the edit modal in Phase 3. For now
		// just toast the target so testers can confirm the wiring.
		this.$root.on("click", ".entry-block", (e) => {
			const name = $(e.currentTarget).data("name");
			this.toast(__("Edit {0} — modal lands in Phase 3.", [name]), "ok");
		});

		// Empty-cell "+" button. Same story — Phase 3 opens the modal.
		this.$root.on("click", ".add-btn", (e) => {
			e.stopPropagation();
			const $btn = $(e.currentTarget);
			const iso = $btn.data("date");
			const ws = $btn.data("workstation");
			this.toast(__("Add on {0} / {1} — modal lands in Phase 3.", [iso, ws]), "ok");
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
}
