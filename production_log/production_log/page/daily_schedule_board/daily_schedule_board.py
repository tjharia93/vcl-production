import frappe


@frappe.whitelist()
def get_schedule_data(schedule_date, product_line=None):
    filters = {"schedule_date": schedule_date, "docstatus": ["!=", 2]}

    dps_list = frappe.get_all(
        "Daily Production Schedule",
        filters=filters,
        fields=["name", "workstation", "workstation_type", "product_line",
                "total_planned_qty", "total_planned_hours", "available_hours",
                "utilization_pct", "docstatus"],
        order_by="workstation asc",
    )

    for dps in dps_list:
        dps["schedule_lines"] = frappe.get_all(
            "Schedule Line",
            filters={"parent": dps["name"]},
            fields=["name", "sequence_order", "job_card_type", "job_card_id",
                    "production_stage", "customer", "planned_qty",
                    "estimated_hours", "status", "notes"],
            order_by="sequence_order asc",
        )

    if product_line and product_line != "All":
        dps_list = [d for d in dps_list if d.get("product_line") in (product_line, "All")]

    workstations_with_dps = {d["workstation"] for d in dps_list}

    ws_filters = {"status": "Active"} if frappe.db.has_column("Workstation", "status") else {}
    all_workstations = frappe.get_all(
        "Workstation",
        filters=ws_filters,
        fields=["name", "workstation_type"],
        order_by="name asc",
    )

    for ws in all_workstations:
        if ws["name"] not in workstations_with_dps:
            dps_list.append({
                "name": None,
                "workstation": ws["name"],
                "workstation_type": ws["workstation_type"],
                "product_line": frappe.db.get_value("Workstation", ws["name"], "custom_product_line") or "All",
                "total_planned_qty": 0,
                "total_planned_hours": 0,
                "available_hours": 8,
                "utilization_pct": 0,
                "docstatus": 0,
                "schedule_lines": [],
            })

    dps_list.sort(key=lambda d: d["workstation"])
    return dps_list


@frappe.whitelist()
def reorder_schedule_lines(dps_name, new_order):
    import json
    if isinstance(new_order, str):
        new_order = json.loads(new_order)

    dps = frappe.get_doc("Daily Production Schedule", dps_name)
    if dps.docstatus == 1:
        frappe.throw("Cannot reorder lines on a submitted schedule")

    line_map = {row.name: row for row in dps.schedule_lines}
    for seq, line_name in enumerate(new_order):
        if line_name in line_map:
            line_map[line_name].sequence_order = (seq + 1) * 10

    dps.save(ignore_permissions=True)
    return "ok"


@frappe.whitelist()
def update_line_status(dps_name, line_name, status):
    dps = frappe.get_doc("Daily Production Schedule", dps_name)
    for row in dps.schedule_lines:
        if row.name == line_name:
            row.status = status
            break
    dps.save(ignore_permissions=True)
    return "ok"
