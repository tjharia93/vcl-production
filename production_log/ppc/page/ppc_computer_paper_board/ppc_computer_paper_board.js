// PPC Computer Paper Board — ppc_may26_v1 simple Desk Page.
// Tabs: Job Pool / Daily Plan (workstation-grouped) / Actuals / Dashboard.
// Backend: production_log.ppc.api whitelisted methods.

frappe.pages["ppc_computer_paper_board"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("PPC Computer Paper Board"),
		single_column: true,
	});
	new PPCBoard(page);
};

class PPCBoard {
	constructor(page) {
		this.page = page;
		this.activeTab = "job_pool";
		this.selectedDate = frappe.datetime.get_today();
		this.selectedShift = null;
		this.selectedWorkstation = null;
		this.workstations = [];
		this._renderShell();
		this._wireToolbar();
		this._loadWorkstations().then(() => this._renderTab());
	}

	_renderShell() {
		this.$body = $(`
			<div class="ppc-board">
				<div class="ppc-toolbar">
					<div class="ppc-tabs">
						<button class="ppc-tab is-active" data-tab="job_pool">${__("Job Pool")}</button>
						<button class="ppc-tab" data-tab="daily_plan">${__("Daily Plan")}</button>
						<button class="ppc-tab" data-tab="actuals">${__("Actuals")}</button>
						<button class="ppc-tab" data-tab="dashboard">${__("Dashboard")}</button>
					</div>
					<div class="ppc-toolbar-controls">
						<input type="date" class="ppc-date" value="${this.selectedDate}"/>
						<select class="ppc-shift">
							<option value="">${__("Any shift")}</option>
							<option value="Day Shift">${__("Day Shift")}</option>
							<option value="Night Shift">${__("Night Shift")}</option>
						</select>
						<select class="ppc-ws"><option value="">${__("All workstations")}</option></select>
						<button class="btn btn-default btn-xs ppc-refresh">${__("Refresh")}</button>
					</div>
				</div>
				<div class="ppc-tab-body"></div>
			</div>
		`).appendTo(this.page.body);
	}

	_wireToolbar() {
		this.$body.on("click", ".ppc-tab", (e) => {
			this.activeTab = $(e.currentTarget).data("tab");
			this.$body.find(".ppc-tab").removeClass("is-active");
			$(e.currentTarget).addClass("is-active");
			this._renderTab();
		});
		this.$body.on("change", ".ppc-date", (e) => { this.selectedDate = e.currentTarget.value; this._renderTab(); });
		this.$body.on("change", ".ppc-shift", (e) => { this.selectedShift = e.currentTarget.value || null; this._renderTab(); });
		this.$body.on("change", ".ppc-ws", (e) => { this.selectedWorkstation = e.currentTarget.value || null; this._renderTab(); });
		this.$body.on("click", ".ppc-refresh", () => this._renderTab());
	}

	async _loadWorkstations() {
		const { message } = await frappe.call({
			method: "production_log.ppc.page.ppc_computer_paper_board.ppc_computer_paper_board.list_workstations",
		});
		this.workstations = message || [];
		const opts = (this.workstations || []).map((w) =>
			`<option value="${frappe.utils.escape_html(w.name)}">${frappe.utils.escape_html(w.name)}</option>`
		).join("");
		this.$body.find(".ppc-ws").append(opts);
	}

	_renderTab() {
		const $body = this.$body.find(".ppc-tab-body").empty();
		switch (this.activeTab) {
			case "job_pool":   return this._renderJobPool($body);
			case "daily_plan": return this._renderDailyPlan($body);
			case "actuals":    return this._renderActuals($body);
			case "dashboard":  return this._renderDashboard($body);
		}
	}

	// ---------------------------------------------------------- Tab 1: Pool
	async _renderJobPool($body) {
		$body.html(`<div class="ppc-loading">${__("Loading Job Pool...")}</div>`);
		const { message } = await frappe.call({ method: "production_log.ppc.api.get_open_job_pool" });
		const jobs = message || [];
		const rows = jobs.map((j) => `
			<tr data-jc="${frappe.utils.escape_html(j.name)}">
				<td><a href="/app/job-card-computer-paper/${j.name}">${j.name}</a></td>
				<td>${frappe.utils.escape_html(j.customer || "")}</td>
				<td>${frappe.utils.escape_html(j.specification_name || "")}</td>
				<td>${j.quantity_ordered || 0}</td>
				<td>${j.packing || 0}</td>
				<td>${j.number_of_parts || 1}</td>
				<td>${j.packed_cartons || 0}</td>
				<td>${j.customer_completion_pct || 0}%</td>
				<td><span class="ppc-pill ppc-pill--${(j.priority || "Normal").toLowerCase()}">${frappe.utils.escape_html(j.priority || "Normal")}</span></td>
				<td><span class="ppc-pill ppc-pill--${(j.job_status || "").toLowerCase().replace(/\\s+/g, "-")}">${frappe.utils.escape_html(j.job_status || "")}</span></td>
				<td>${j.due_date ? frappe.datetime.str_to_user(j.due_date) : ""}</td>
			</tr>
		`).join("");
		$body.html(`
			<table class="ppc-table">
				<thead><tr>
					<th>${__("Job Card")}</th><th>${__("Customer")}</th><th>${__("Specification")}</th>
					<th>${__("Cartons")}</th><th>${__("Pack/Ctn")}</th><th>${__("Parts")}</th>
					<th>${__("Packed")}</th><th>${__("Completion")}</th>
					<th>${__("Priority")}</th><th>${__("Status")}</th><th>${__("Due")}</th>
				</tr></thead>
				<tbody>${rows || `<tr><td colspan="11" class="ppc-empty">${__("No open jobs.")}</td></tr>`}</tbody>
			</table>
		`);
	}

	// --------------------------------------------------- Tab 2: Daily Plan
	async _renderDailyPlan($body) {
		$body.html(`<div class="ppc-loading">${__("Loading Daily Plan...")}</div>`);
		const { message } = await frappe.call({
			method: "production_log.ppc.api.get_daily_plan",
			args: {
				planning_date: this.selectedDate,
				shift: this.selectedShift,
				workstation: this.selectedWorkstation,
			},
		});
		const plans = message || [];
		if (!plans.length) {
			return $body.html(`
				<div class="ppc-empty">
					${__("No plans for {0}", [frappe.datetime.str_to_user(this.selectedDate)])}<br/>
					<a href="/app/ppc-daily-plan/new" class="btn btn-primary btn-sm" style="margin-top:8px">${__("Create Daily Plan")}</a>
				</div>
			`);
		}
		// Group by workstation
		const byWs = {};
		plans.forEach((p) => { (byWs[p.workstation || "—"] = byWs[p.workstation || "—"] || []).push(p); });
		const html = Object.keys(byWs).map((ws) => `
			<div class="ppc-ws-section">
				<div class="ppc-ws-title">${frappe.utils.escape_html(ws)}</div>
				${byWs[ws].map((plan) => this._renderPlanCard(plan)).join("")}
			</div>
		`).join("");
		$body.html(html);
	}

	_renderPlanCard(plan) {
		const items = (plan.items || []).map((row) => `
			<tr>
				<td>${row.sequence || ""}</td>
				<td><a href="/app/job-card-computer-paper/${row.source_job_card}">${row.source_job_card}</a></td>
				<td>${frappe.utils.escape_html(row.customer || "")}</td>
				<td>${row.stage || ""}</td>
				<td>${row.planned_qty || 0} ${row.planned_uom || ""}</td>
				<td>${row.remaining_balance || 0}</td>
				<td><span class="ppc-pill ppc-pill--${(row.priority || "Normal").toLowerCase()}">${row.priority || "Normal"}</span></td>
				<td><span class="ppc-pill ppc-pill--${(row.line_status || "").toLowerCase().replace(/\\s+/g, "-")}">${row.line_status || ""}</span></td>
			</tr>
		`).join("");
		return `
			<div class="ppc-plan-card">
				<div style="display:flex; gap:10px; align-items:center; margin-bottom:6px;">
					<a href="/app/ppc-daily-plan/${plan.name}"><strong>${plan.name}</strong></a>
					<span>${plan.shift || ""}</span>
					<span class="ppc-pill ppc-pill--${(plan.status || "").toLowerCase()}">${plan.status || ""}</span>
				</div>
				<table class="ppc-table">
					<thead><tr>
						<th>${__("Seq")}</th><th>${__("Job Card")}</th><th>${__("Customer")}</th>
						<th>${__("Stage")}</th><th>${__("Planned")}</th><th>${__("Balance")}</th>
						<th>${__("Priority")}</th><th>${__("Line Status")}</th>
					</tr></thead>
					<tbody>${items || `<tr><td colspan="8" class="ppc-empty">${__("No items.")}</td></tr>`}</tbody>
				</table>
			</div>
		`;
	}

	// ------------------------------------------------------ Tab 3: Actuals
	async _renderActuals($body) {
		$body.html(`<div class="ppc-loading">${__("Loading Actuals...")}</div>`);
		const filters = { posting_date: this.selectedDate, docstatus: 1 };
		if (this.selectedShift) filters.shift = this.selectedShift;
		if (this.selectedWorkstation) filters.workstation = this.selectedWorkstation;
		const rows = await frappe.db.get_list("PPC Production Actual", {
			filters, fields: ["name", "posting_date", "shift", "workstation", "supervisor"],
			order_by: "creation desc", limit: 100,
		});
		if (!rows.length) {
			return $body.html(`<div class="ppc-empty">${__("No actuals submitted on {0}", [frappe.datetime.str_to_user(this.selectedDate)])}</div>`);
		}
		$body.html(`
			<table class="ppc-table">
				<thead><tr>
					<th>${__("Actual")}</th><th>${__("Shift")}</th><th>${__("Workstation")}</th><th>${__("Supervisor")}</th>
				</tr></thead>
				<tbody>
				${rows.map((r) => `
					<tr>
						<td><a href="/app/ppc-production-actual/${r.name}">${r.name}</a></td>
						<td>${r.shift || ""}</td>
						<td>${r.workstation || ""}</td>
						<td>${frappe.utils.escape_html(r.supervisor || "")}</td>
					</tr>
				`).join("")}
				</tbody>
			</table>
		`);
	}

	// ----------------------------------------------------- Tab 4: Dashboard
	async _renderDashboard($body) {
		$body.html(`<div class="ppc-loading">${__("Loading Dashboard...")}</div>`);
		const { message } = await frappe.call({
			method: "production_log.ppc.api.get_dashboard",
			args: { date: this.selectedDate },
		});
		const d = message || {};
		const kpi = (label, val, cls = "") =>
			`<div class="ppc-kpi"><div class="ppc-kpi-label">${label}</div><div class="ppc-kpi-value ${cls}">${val ?? 0}</div></div>`;
		$body.html(`
			<div class="ppc-kpi-grid">
				${kpi(__("Open Jobs"), d.open_jobs)}
				${kpi(__("On Hold"), d.on_hold, "ppc-kpi-value--warn")}
				${kpi(__("Packing Pending"), d.packing_pending, "ppc-kpi-value--warn")}
				${kpi(__("Awaiting Closure"), d.completed_awaiting_closure)}
				${kpi(__("Planned Today"), d.planned_today)}
				${kpi(__("Completed Today"), d.completed_today, "ppc-kpi-value--good")}
				${kpi(__("Overdue"), d.overdue, "ppc-kpi-value--warn")}
				${kpi(__("Good Today"), d.good_today, "ppc-kpi-value--good")}
				${kpi(__("Waste Today"), d.waste_today, "ppc-kpi-value--warn")}
				${kpi(__("Rejected Today"), d.rejected_today, "ppc-kpi-value--warn")}
				${kpi(__("Downtime (min)"), d.downtime_today)}
			</div>
		`);
	}
}
