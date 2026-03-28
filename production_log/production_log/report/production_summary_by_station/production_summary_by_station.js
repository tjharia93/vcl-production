frappe.query_reports["Production Summary by Station"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
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
			fieldname: "station",
			label: __("Workstation"),
			fieldtype: "Link",
			options: "Workstation",
		},
		{
			fieldname: "shift",
			label: __("Shift"),
			fieldtype: "Select",
			options: "\nDay\nNight",
		},
	],
};
