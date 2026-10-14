# TRANSITIONAL (14/10/2026): live copy of the carton size/build + board-plan branch of
# production_log.job_card_tracking.cps_revise.revise (build= / carton=), so the
# Revise dialog works before the app is deployed. safe_exec forbids imports, so the
# rules and board geometry are inlined here. DELETE once the app is deployed and the
# fixture Client Script (which calls the app method) has been migrated over this one.
spec_name = frappe.form_dict.get("spec")
reason = (frappe.form_dict.get("reason") or "").strip()
build_in = json.loads(frappe.form_dict.get("build") or "{}") or {}
carton_in = json.loads(frappe.form_dict.get("carton") or "{}") or {}

if not spec_name:
    frappe.throw("spec is required.")
if not reason:
    frappe.throw("A reason for the revision is required.")

doc = frappe.get_doc("Customer Product Specification", spec_name)
if doc.docstatus != 1:
    frappe.throw("Only a submitted specification is revised here.")
if doc.product_type != "Carton":
    frappe.throw("Size and build apply to Carton specifications only.")

MATERIALS = ["", "Test Liner", "Kraft", "White Test Liner"]
BUILD = [
    ["ctn_length_mm", "int", None], ["ctn_width_mm", "int", None], ["ctn_height_mm", "int", None],
    ["idod", "select", ["", "ID", "OD"]],
    ["product_type_carton", "select", ["", "Tray", "Die Cut", "1 Flap RSC", "2 Flap RSC", "3 Flap RSC"]],
    ["ply", "select", ["SFK", "3", "5"]],
    ["flute_type", "select", ["B", "C", "E"]],
    ["joint_type", "select", ["", "Gluing - Manual", "Gluing - Machine", "Stitched"]],
    ["1_ply_top_layer_gsm", "int", None], ["1_ply_top_layer_material", "select", MATERIALS],
    ["2_ply_fluting_gsm", "int", None], ["2_ply_top_layer_material", "select", MATERIALS],
    ["3_ply_bottom_gsm", "int", None], ["3_ply_top_layer_material", "select", MATERIALS],
    ["4_ply_fluting_gsm", "int", None], ["4_ply_top_layer_material", "select", MATERIALS],
    ["5_ply_fluting_gsm", "int", None], ["5_ply_top_layer_material", "select", MATERIALS],
]
LAYERS = ["1_ply_top_layer_gsm", "2_ply_fluting_gsm", "3_ply_bottom_gsm", "4_ply_fluting_gsm", "5_ply_fluting_gsm"]
GEOMETRY = ["ctn_length_mm", "ctn_width_mm", "ctn_height_mm", "product_type_carton", "ply"]
known = [b[0] for b in BUILD]


def nn(v):
    # non-negative int, junk -> 0 (cps_carton_board._int)
    try:
        out = int(float(v))
    except Exception:
        return 0
    return out if out > 0 else 0


def shown(v):
    return "empty" if v in (None, "") else v


def active_layers(ply):
    # Own copy of the layer list: in safe_exec a function cannot see top-level names.
    layers = ["1_ply_top_layer_gsm", "2_ply_fluting_gsm", "3_ply_bottom_gsm", "4_ply_fluting_gsm", "5_ply_fluting_gsm"]
    if ply == "5":
        return layers
    if ply == "3":
        return layers[:3]
    return layers[:2]


clean = {}
for field in build_in:
    if field not in known:
        frappe.throw(field + " is not part of a carton's size or build.")
for b in BUILD:
    field = b[0]
    if field not in build_in:
        continue
    value = build_in.get(field)
    if b[1] == "int":
        try:
            number = float(value if value not in (None, "") else 0)
        except Exception:
            frappe.throw(field + " must be a whole number.")
        if number < 0 or number != int(number):
            frappe.throw(field + " must be a whole number, not negative.")
        clean[field] = int(number)
    else:
        text = str(value or "").strip()
        if text not in b[2]:
            frappe.throw(field + ": '" + text + "' is not one of " + ", ".join([a for a in b[2] if a]) + ".")
        clean[field] = text

after = doc.as_dict()
after.update(clean)
ply = str(after.get("ply") or "").strip()
if not ply:
    frappe.throw("Ply is required for a carton.")
if not str(after.get("flute_type") or "").strip():
    frappe.throw("Flute Type is required for a carton.")
if int(after.get("ctn_length_mm") or 0) <= 0:
    frappe.throw("Carton Length (mm) must be greater than 0.")
if int(after.get("ctn_width_mm") or 0) <= 0:
    frappe.throw("Carton Width (mm) must be greater than 0.")
if ply != "SFK" and int(after.get("ctn_height_mm") or 0) <= 0:
    frappe.throw("Carton Height (mm) must be greater than 0 unless Ply is SFK.")
for f in active_layers(ply):
    if int(after.get(f) or 0) <= 0:
        frappe.throw("A " + ply + "-ply board needs a GSM on layer " + f[0] + ".")

changes = []
moved = []
for b in BUILD:
    field = b[0]
    if field not in clean:
        continue
    old = doc.get(field)
    new = clean[field]
    if b[1] == "int":
        same = int(old or 0) == new
    else:
        same = (old or "") == new
    if not same:
        changes.append((doc.meta.get_label(field) or field) + ": " + str(shown(old)) + " -> " + str(shown(new)))
        doc.set(field, new)
        moved.append(field)

if moved and [f for f in ["ctn_length_mm", "ctn_width_mm", "ctn_height_mm", "ply"] if f in clean]:
    if doc.ply == "SFK" or not int(doc.ctn_height_mm or 0):
        size = str(int(doc.ctn_length_mm or 0)) + " X " + str(int(doc.ctn_width_mm or 0))
    else:
        size = str(int(doc.ctn_length_mm or 0)) + " X " + str(int(doc.ctn_width_mm or 0)) + " X " + str(int(doc.ctn_height_mm or 0))
    if doc.job_size != size:
        changes.append("Job Size: " + str(shown(doc.job_size)) + " -> " + size)
        doc.job_size = size

# ── Board plan (cps_carton_board.board_plan + revisable_changes) ──
replan = len([f for f in moved if f in GEOMETRY or f in LAYERS]) > 0
if carton_in or replan:
    style = str(doc.product_type_carton or "").strip()
    flap = nn(carton_in.get("ctn_flap_mm"))
    if not flap and ("ctn_width_mm" in moved or "product_type_carton" in moved) and style != "Tray":
        flap = (nn(doc.ctn_width_mm) + 6) // 2
    if not flap:
        flap = nn(doc.ctn_flap_mm)

    length = nn(doc.ctn_length_mm)
    width = nn(doc.ctn_width_mm)
    height = nn(doc.ctn_height_mm)
    not_ok = ""
    if ply == "SFK":
        not_ok = "SFK is an un-glued web - there is no blank to plan."
    elif style == "Die Cut":
        not_ok = "Die Cut blanks vary per job, so there is no formula to derive."
    elif not style:
        not_ok = "This specification has no carton style, so the blank cannot be derived."
    needs_flap = style != "Tray"
    if not flap and needs_flap:
        flap = (width + 6) // 2 if width > 0 else 0
    if not not_ok and (length <= 0 or width <= 0 or (needs_flap and (height <= 0 or flap <= 0))):
        not_ok = "This specification is missing a length, width or height, so the blank cannot be derived. Correct the dimensions first."

    if not_ok:
        if carton_in:
            frappe.throw(not_ok)
    else:
        TAB = 30
        TRIM = 10
        if style == "Tray":
            bw = width + 2 * height
            bl = length + 2 * height
        elif style == "1 Flap RSC":
            bw = height + flap
            bl = 2 * length + 2 * width + TAB
        else:
            bw = flap + height + flap
            bl = 2 * length + 2 * width + TAB
        pw = bw + 2 * TRIM
        pl = bl + 2 * TRIM
        gsm = nn(doc.get("1_ply_top_layer_gsm")) + nn(doc.get("2_ply_fluting_gsm"))
        if ply in ("3", "5"):
            gsm += nn(doc.get("3_ply_bottom_gsm"))
        if ply == "5":
            gsm += nn(doc.get("4_ply_fluting_gsm")) + nn(doc.get("5_ply_fluting_gsm"))
        weight = frappe.utils.flt((pw * pl) / 1000000.0 * gsm, 2)

        proposed = {
            "ctn_flap_mm": flap,
            "board_width_planned_mm": pw,
            "board_length_planned_mm": pl,
            "approximate_weight_grams": weight,
            "board_width_actual_mm": nn(carton_in.get("board_width_actual_mm")) or bw,
            "board_length_actual_mm": nn(carton_in.get("board_length_actual_mm")) or bl,
        }
        floats = ["approximate_weight_grams"]
        for f in ["printed_weight", "empty_carton_weight"]:
            if carton_in.get(f) not in (None, ""):
                proposed[f] = frappe.utils.flt(carton_in.get(f))
                floats.append(f)
        for f in sorted(proposed.keys()):
            old = doc.get(f)
            new = proposed[f]
            if f in floats:
                differs = frappe.utils.flt(old or 0, 2) != frappe.utils.flt(new, 2)
            else:
                differs = nn(old) != nn(new)
            if differs:
                changes.append((doc.meta.get_label(f) or f) + ": " + str(old or 0) + " -> " + str(new))
                doc.set(f, new)

if (build_in or carton_in) and not changes:
    frappe.throw("Nothing changed - revision not recorded.")

summary = "; ".join(changes) if changes else "note only (no field changes)"
entry = "[" + frappe.utils.now()[:16] + "] " + frappe.session.user + "\nReason: " + reason + "\nChanged: " + summary
doc.revision_notes = ((doc.revision_notes or "") + "\n\n" + entry).strip()
doc.save()

frappe.response["message"] = {"ok": True, "spec": doc.name, "changes": changes}
