# cps_revise - revise a SUBMITTED Customer Product Specification in place.
# Never cancels, never amends. The spec keeps its name, linked job cards keep
# their own snapshot of the old values, and Frappe's Version log records the diff.
#
# TRANSITIONAL. Superseded at the next deploy by the whitelisted app method
# production_log.job_card_tracking.cps_revise.revise, which imports the board
# geometry from cps_carton_board instead of inlining it below. Patch v9_7 DELETES
# this Server Script in that same migrate. The geometry here is duplicated only
# because safe_exec forbids imports - keep it in step with cps_carton_board.py
# until it dies, and do not add a third caller to it.

spec = frappe.form_dict.get("spec")
reason = (frappe.form_dict.get("reason") or "").strip()
parts_in = frappe.form_dict.get("parts")
carton_in = frappe.form_dict.get("carton")

if not spec:
    frappe.throw("spec is required.")
if not reason:
    frappe.throw("A reason for the revision is required.")

doc = frappe.get_doc("Customer Product Specification", spec)

if doc.docstatus == 0:
    frappe.throw("This specification is still a Draft - edit it directly, no revision needed.")
if doc.docstatus == 2:
    frappe.throw("This specification is cancelled and cannot be revised.")

changes = []
supplied = False

# ── Computer Paper: Colour of Parts ──────────────────────────────────────────
if parts_in:
    supplied = True
    if doc.product_type != "Computer Paper":
        frappe.throw("Colour of Parts applies to Computer Paper specifications only.")

    rows = json.loads(parts_in) if isinstance(parts_in, str) else parts_in
    n = len(rows)

    if n != len(doc.colour_of_parts):
        frappe.throw("Revise cannot add or remove parts - Number of Parts is fixed after submit. Create a new specification instead.")

    # validate() does NOT re-run on update-after-submit, so mirror
    # CustomerProductSpecification._validate_paper_type_and_gsm here.
    if n == 1:
        allowed = [[("60 GSM Bond", 60), ("CB", 55), ("70 GSM Bond", 70)]]
    else:
        allowed = [[("CB", 55)]] + [[("CFB", 50)]] * (n - 2) + [[("CF", 55)]]

    for i in range(n):
        pt = (rows[i].get("paper_type") or "").strip()
        gsm = int(rows[i].get("gsm") or 0)
        colour = (rows[i].get("colour") or "").strip().upper()
        if not colour:
            frappe.throw("Part " + str(i + 1) + " is missing a colour.")
        ok = False
        for a in allowed[i]:
            if pt == a[0] and gsm == a[1]:
                ok = True
        if not ok:
            opts = ", ".join([a[0] + " (" + str(a[1]) + " GSM)" for a in allowed[i]])
            frappe.throw("Part " + str(i + 1) + ": invalid paper type / GSM. Expected one of: " + opts + ". Got: " + pt + " (" + str(gsm) + " GSM).")

    for i in range(n):
        row = doc.colour_of_parts[i]
        pt = (rows[i].get("paper_type") or "").strip()
        gsm = int(rows[i].get("gsm") or 0)
        colour = (rows[i].get("colour") or "").strip().upper()
        label = "Part " + str(row.part_number)
        if (row.colour or "").strip().upper() != colour:
            changes.append(label + " colour: " + str(row.colour) + " -> " + colour)
            row.colour = colour
        if (row.paper_type or "") != pt:
            changes.append(label + " paper: " + str(row.paper_type) + " -> " + pt)
            row.paper_type = pt
        if int(row.gsm or 0) != gsm:
            changes.append(label + " gsm: " + str(row.gsm) + " -> " + str(gsm))
            row.gsm = gsm

# ── Carton: Board Plan ───────────────────────────────────────────────────────
# A carton submitted before 2026-07-23 carries zeroes for all six board fields
# because they did not exist. Only the flap and the two actual sizes are the
# operator's to state; everything else is derived here, so a caller cannot post
# a board plan that does not follow from the carton it describes.
if carton_in is not None:
    supplied = True
    if doc.product_type != "Carton":
        frappe.throw("The Board Plan applies to Carton specifications only.")

    req = json.loads(carton_in) if isinstance(carton_in, str) else carton_in

    TAB = 30    # VCL standard for every joint type since 2026-07-23.
    TRIM = 10   # per OUTER edge, so a full axis gains twice this.

    style = (doc.product_type_carton or "").strip()
    ply = (doc.ply or "").strip()
    L = int(doc.ctn_length_mm or 0)
    W = int(doc.ctn_width_mm or 0)
    H = int(doc.ctn_height_mm or 0)

    if ply == "SFK":
        frappe.throw("SFK is an un-glued web - there is no blank to plan.")
    if style == "Die Cut":
        frappe.throw("Die Cut blanks vary per job, so there is no formula to derive.")
    if not style:
        frappe.throw("This specification has no carton style, so the blank cannot be derived.")

    needs_flap = style != "Tray"

    # A flap the record already carries is an override in its own right, or
    # revising for an unrelated reason would reset a hand-measured flap back to
    # the formula and take the blank, planned size and weight with it.
    override = int(req.get("ctn_flap_mm") or 0) or int(doc.ctn_flap_mm or 0)
    if override > 0:
        flap = override
    elif needs_flap and W > 0:
        flap = (W + 6) // 2      # ceil((W + 5) / 2), without importing math
    else:
        flap = 0

    if L <= 0 or W <= 0 or (needs_flap and (H <= 0 or flap <= 0)):
        frappe.throw("This specification is missing a length, width or height, so the blank cannot be derived. Correct the dimensions first.")

    if style == "Tray":
        blank_w = W + 2 * H
        blank_l = L + 2 * H
    elif style == "1 Flap RSC":
        blank_w = H + flap
        blank_l = (2 * L) + (2 * W) + TAB
    else:
        blank_w = flap + H + flap
        blank_l = (2 * L) + (2 * W) + TAB

    planned_w = blank_w + (2 * TRIM)
    planned_l = blank_l + (2 * TRIM)

    gsm = int(doc.get("1_ply_top_layer_gsm") or 0) + int(doc.get("2_ply_fluting_gsm") or 0)
    if ply == "3" or ply == "5":
        gsm = gsm + int(doc.get("3_ply_bottom_gsm") or 0)
    if ply == "5":
        gsm = gsm + int(doc.get("4_ply_fluting_gsm") or 0) + int(doc.get("5_ply_fluting_gsm") or 0)

    # Struck on the PLANNED size: the trim is board that is bought and paid for
    # even though it is cut away. Understated - it ignores flute take-up.
    weight_g = frappe.utils.flt((planned_w * planned_l) / 1000000.0 * gsm, 2)

    proposed = {
        "ctn_flap_mm": flap,
        "board_width_planned_mm": planned_w,
        "board_length_planned_mm": planned_l,
        "approximate_weight_grams": weight_g,
    }

    # The actuals default to the blank but are the operator's to override.
    supplied_w = int(req.get("board_width_actual_mm") or 0)
    supplied_l = int(req.get("board_length_actual_mm") or 0)
    proposed["board_width_actual_mm"] = supplied_w if supplied_w > 0 else blank_w
    proposed["board_length_actual_mm"] = supplied_l if supplied_l > 0 else blank_l

    # Weights are measurements, never derived. Only carried through when given.
    for f in ["printed_weight", "empty_carton_weight"]:
        if req.get(f) not in (None, ""):
            proposed[f] = frappe.utils.flt(req.get(f), 2)

    labels = {
        "ctn_flap_mm": "Carton Flap (mm)",
        "board_width_planned_mm": "Board Width Planned (mm)",
        "board_length_planned_mm": "Board Length Planned (mm)",
        "board_width_actual_mm": "Board Width Actual (mm)",
        "board_length_actual_mm": "Board Length Actual (mm)",
        "approximate_weight_grams": "Approximate Weight (g)",
        "printed_weight": "Printed Weight / Carton (kg)",
        "empty_carton_weight": "Empty Carton Weight (g)",
    }

    for f in sorted(proposed.keys()):
        new = proposed[f]
        old = doc.get(f)
        if isinstance(new, float):
            same = frappe.utils.flt(old or 0, 2) == frappe.utils.flt(new, 2)
        else:
            same = int(old or 0) == int(new)
        if not same:
            changes.append(labels[f] + ": " + str(old or 0) + " -> " + str(new))
            doc.set(f, new)

if supplied and not changes:
    frappe.throw("Nothing changed - revision not recorded.")

stamp = frappe.utils.now()[:16]
summary = "; ".join(changes) if changes else "note only (no field changes)"
entry = "[" + stamp + "] " + frappe.session.user + "\nReason: " + reason + "\nChanged: " + summary
doc.revision_notes = ((doc.revision_notes or "") + "\n\n" + entry).strip()
doc.save()

frappe.response["message"] = {"ok": True, "spec": doc.name, "changes": changes}
