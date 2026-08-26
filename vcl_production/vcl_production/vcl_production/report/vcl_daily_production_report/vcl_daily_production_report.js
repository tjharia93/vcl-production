// Copyright (c) 2026, VCL and contributors
// For license information, please see license.txt

frappe.query_reports["VCL Daily Production Report"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Data",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: [
				"",
				"Planned",
				"Not Started",
				"Running",
				"Paused",
				"Completed",
				"Carried Forward",
			],
		},
		{
			fieldname: "include_demo",
			label: __("Include Demo Data"),
			fieldtype: "Check",
			default: 0,
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data && data.status) {
			const colours = {
				"Running": "green",
				"Completed": "blue",
				"Carried Forward": "red",
				"Paused": "orange",
				"Not Started": "orange",
				"Planned": "gray",
			};
			const colour = colours[data.status] || "gray";
			value = `<span class="indicator-pill ${colour}">${frappe.utils.escape_html(
				data.status
			)}</span>`;
		}
		if (column.fieldname === "attention" && data && data.attention) {
			value = `<span style="color:#b02a37">${value}</span>`;
		}
		return value;
	},
};
