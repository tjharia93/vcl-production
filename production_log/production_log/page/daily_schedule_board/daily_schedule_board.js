frappe.pages["daily-schedule-board"].on_page_load = function (wrapper) {
	let page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Daily Schedule Board",
		single_column: true,
	});

	page.schedule_date = frappe.datetime.get_today();

	// Date navigation
	page.set_secondary_action("◀ Prev", () => {
		page.schedule_date = frappe.datetime.add_days(page.schedule_date, -1);
		page.date_indicator.html(page.schedule_date);
		load_board(page);
	});
	page.set_primary_action("Next ▶", () => {
		page.schedule_date = frappe.datetime.add_days(page.schedule_date, 1);
		page.date_indicator.html(page.schedule_date);
		load_board(page);
	});

	page.date_indicator = $(`<span class="text-muted ml-3" style="font-size:16px; font-weight:600;">${page.schedule_date}</span>`);
	page.page_actions.find(".custom-btn-group").after(page.date_indicator);

	// Product line filter
	let $filter = $(`<select class="form-control input-xs" style="width:160px; display:inline-block; margin-left:16px;">
		<option value="All">All Lines</option>
		<option value="Computer Paper">Computer Paper</option>
		<option value="Label">Label</option>
		<option value="Carton">Carton</option>
	</select>`);
	page.page_actions.append($filter);
	$filter.on("change", () => {
		page.product_line_filter = $filter.val();
		load_board(page);
	});
	page.product_line_filter = "All";

	page.board_area = $('<div class="schedule-board-container"></div>').appendTo(page.body);

	load_board(page);
};

function load_board(page) {
	page.board_area.html('<div class="text-center text-muted p-5">Loading...</div>');

	frappe.call({
		method: "production_log.production_log.page.daily_schedule_board.daily_schedule_board.get_schedule_data",
		args: {
			schedule_date: page.schedule_date,
			product_line: page.product_line_filter || "All",
		},
		callback: function (r) {
			render_board(page, r.message || []);
		},
	});
}

function render_board(page, data) {
	page.board_area.empty();

	if (!data.length) {
		page.board_area.html('<div class="text-center text-muted p-5">No workstations found.</div>');
		return;
	}

	let $row = $('<div class="row" style="overflow-x:auto; flex-wrap:nowrap; display:flex;"></div>');
	page.board_area.append($row);

	data.forEach((dps) => {
		let util_class = "";
		if (dps.utilization_pct > 100) util_class = "text-danger";
		else if (dps.utilization_pct > 85) util_class = "text-warning";

		let $col = $(`<div class="col" style="min-width:260px; max-width:320px; flex:0 0 280px; margin:4px;">
			<div class="card h-100">
				<div class="card-header p-2">
					<strong>${dps.workstation}</strong><br>
					<small class="text-muted">${dps.product_line || ""}</small>
					<span class="float-right ${util_class}" style="font-size:12px;">
						${(dps.total_planned_hours || 0).toFixed(1)}h / ${(dps.available_hours || 8).toFixed(1)}h
						(${(dps.utilization_pct || 0).toFixed(0)}%)
					</span>
				</div>
				<div class="card-body p-2 schedule-column" data-dps="${dps.name || ""}" data-workstation="${dps.workstation}" style="min-height:200px;">
				</div>
			</div>
		</div>`);

		let $body = $col.find(".schedule-column");

		(dps.schedule_lines || []).forEach((line) => {
			let status_color = {
				Pending: "orange",
				"In Progress": "blue",
				Done: "green",
				Skipped: "grey",
			}[line.status] || "grey";

			let $card = $(`<div class="card mb-2 schedule-card" data-line="${line.name}" style="cursor:grab; border-left:3px solid ${status_color};">
				<div class="card-body p-2" style="font-size:12px;">
					<strong>${line.job_card_id}</strong><br>
					<span class="text-muted">${line.customer || ""}</span><br>
					${line.production_stage} · ${line.planned_qty} pcs<br>
					<span style="font-size:11px;">~${(line.estimated_hours || 0).toFixed(1)}h</span>
					<span class="badge float-right" style="background:${status_color}; color:white;">${line.status}</span>
				</div>
			</div>`);

			$card.find(".badge").on("click", function (e) {
				e.stopPropagation();
				if (!dps.name) return;
				let next_status = { Pending: "In Progress", "In Progress": "Done", Done: "Pending" };
				let new_status = next_status[line.status] || "Pending";
				frappe.call({
					method: "production_log.production_log.page.daily_schedule_board.daily_schedule_board.update_line_status",
					args: { dps_name: dps.name, line_name: line.name, status: new_status },
					callback: () => load_board(page),
				});
			});

			$body.append($card);
		});

		$row.append($col);
	});
}
