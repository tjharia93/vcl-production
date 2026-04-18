import frappe
from frappe import _
from frappe.utils import getdate, add_days, flt


@frappe.whitelist()
def get_cp_workstations():
    """Return Computer Paper workstations (product_line = Computer Paper or All)."""
    workstations = frappe.get_all(
        "Workstation",
        filters={"custom_product_line": ["in", ["Computer Paper", "All"]]},
        fields=["name", "custom_product_line", "custom_max_speed_per_hour"],
        order_by="name asc",
    )
    return workstations


@frappe.whitelist()
def get_job_pool():
    """Return submitted Job Card Computer Paper records with planning_status = Open."""
    jobs = frappe.get_all(
        "Job Card Computer Paper",
        filters={
            "planning_status": "Open",
            "docstatus": 1,
        },
        fields=[
            "name",
            "customer",
            "customer_product_spec",
            "specification_name",
            "quantity_ordered",
            "number_of_parts",
            "number_of_colours",
            "plate_status",
            "plates_confirmed",
            "plate_code",
            "job_size",
            "packing",
            "numbering_required",
            "weight_per_carton",
            "creation",
        ],
        order_by="creation asc",
    )
    return jobs


@frappe.whitelist()
def get_week_schedule(week_start):
    """Return DPS records for all CP workstations for the given week."""
    week_start_date = getdate(week_start)
    week_end_date = add_days(week_start_date, 6)

    cp_workstations = [w["name"] for w in get_cp_workstations()]

    if not cp_workstations:
        return {
            "schedules": [],
            "workstations": [],
            "week_start": str(week_start_date),
            "week_end": str(week_end_date),
        }

    schedules = frappe.get_all(
        "Daily Production Schedule",
        filters={
            "schedule_date": ["between", [str(week_start_date), str(week_end_date)]],
            "workstation": ["in", cp_workstations],
            "docstatus": ["!=", 2],
        },
        fields=[
            "name",
            "workstation",
            "schedule_date",
            "available_hours",
            "total_planned_hours",
            "utilization_pct",
            "docstatus",
        ],
    )

    # Fetch schedule lines for each DPS
    for s in schedules:
        s["schedule_lines"] = frappe.get_all(
            "Schedule Line",
            filters={"parent": s["name"]},
            fields=[
                "name",
                "sequence_order",
                "job_card_type",
                "job_card_id",
                "production_stage",
                "customer",
                "planned_qty",
                "estimated_hours",
                "status",
            ],
            order_by="sequence_order asc",
        )

    return {
        "schedules": schedules,
        "workstations": cp_workstations,
        "week_start": str(week_start_date),
        "week_end": str(week_end_date),
    }


@frappe.whitelist()
def assign_job(workstation, schedule_date, job_card_id, production_stage, planned_qty, estimated_hours):
    """
    Assign a Job Card to a workstation/date.
    Creates a draft DPS if none exists, then appends a Schedule Line.
    Only works with draft DPS records â submitted schedules must be amended first.
    """
    # Find existing draft DPS for this workstation + date
    dps_name = frappe.db.get_value(
        "Daily Production Schedule",
        {"workstation": workstation, "schedule_date": schedule_date, "docstatus": 0},
        "name",
    )

    if not dps_name:
        # Check if a submitted DPS exists â if so, warn the user
        submitted_name = frappe.db.get_value(
            "Daily Production Schedule",
            {"workstation": workstation, "schedule_date": schedule_date, "docstatus": 1},
            "name",
        )
        if submitted_name:
            frappe.throw(
                _(
                    "A submitted Daily Production Schedule ({0}) already exists for {1} on {2}. "
                    "Please amend it before adding new entries."
                ).format(submitted_name, workstation, schedule_date)
            )

        # Create new draft DPS
        dps = frappe.new_doc("Daily Production Schedule")
        dps.workstation = workstation
        dps.schedule_date = schedule_date
        dps.available_hours = 8
        dps.flags.ignore_permissions = True
        dps.insert()
        dps_name = dps.name

    dps = frappe.get_doc("Daily Production Schedule", dps_name)

    # Get customer from job card
    customer = frappe.db.get_value("Job Card Computer Paper", job_card_id, "customer") or ""

    # Determine next sequence order
    existing_max = max((l.sequence_order or 0 for l in dps.schedule_lines), default=0)
    next_seq = existing_max + 10

    dps.append(
        "schedule_lines",
        {
            "sequence_order": next_seq,
            "job_card_type": "Job Card Computer Paper",
            "job_card_id": job_card_id,
            "production_stage": production_stage,
            "customer": customer,
            "planned_qty": flt(planned_qty),
            "estimated_hours": flt(estimated_hours),
            "status": "Pending",
        },
    )
    dps.flags.ignore_permissions = True
    dps.save()

    return {"dps_name": dps.name, "status": "ok"}


@frappe.whitelist()
def remove_assignment(dps_name, schedule_line_name):
    """Remove a specific schedule line from a draft DPS."""
    dps = frappe.get_doc("Daily Production Schedule", dps_name)
    if dps.docstatus != 0:
        frappe.throw(_("Cannot modify a submitted or cancelled schedule."))

    dps.schedule_lines = [l for l in dps.schedule_lines if l.name != schedule_line_name]
    dps.flags.ignore_permissions = True
    dps.save()
    return {"status": "ok"}


@frappe.whitelist()
def update_job_planning_status(job_card_id, status):
    """Update planning_status on a Job Card Computer Paper."""
    frappe.db.set_value("Job Card Computer Paper", job_card_id, "planning_status", status)
    frappe.db.commit()
    return {"status": "ok"}


@frappe.whitelist()
def get_production_stages():
    """Return all production stages ordered by sequence."""
    stages = frappe.get_all(
        "Production Stage",
        fields=["name", "sequence"],
        order_by="sequence asc",
    )
    return stages
