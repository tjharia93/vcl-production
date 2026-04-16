"""
Utility helpers for the production_log app.

Registered as Jinja methods in hooks.py so print formats can call them.
"""

# ---------------------------------------------------------------------------
# Carton die-cut SVG generator (used by the Carton Job Traveller print format)
# ---------------------------------------------------------------------------

_COLORS = {
    "primary": "#2B3990",
    "fold": "#FF6B35",
    "glue": "#4CAF50",
    "stitch": "#D32F2F",
    "cut": "#333333",
    "face": "#C5CAE9",
    "side": "#9FA8DA",
    "top": "#7986CB",
    "base": "#B39DDB",
    "trayWall": "#81C784",
}

_JOINT_CONFIG = {
    "Gluing - Manual":  {"tabWidth": 30, "label": "Glue Tab",   "color": "#4CAF5040", "markerType": "glue"},
    "Gluing - Machine": {"tabWidth": 30, "label": "Glue Tab",   "color": "#4CAF5040", "markerType": "glue"},
    "Stitched":         {"tabWidth": 40, "label": "Stitch Flap", "color": "#D32F2F30", "markerType": "stitch"},
}


def get_carton_svg(doc):
    """Return an SVG string for the carton die-cut layout.

    Called from Jinja print formats as ``{{ get_carton_svg(doc) }}``.
    Returns an empty string when there is nothing to draw.
    """
    product_type = (getattr(doc, "product_type", None) or "").strip()
    L = int(getattr(doc, "ctn_length_mm", 0) or 0)
    W = int(getattr(doc, "ctn_width_mm", 0) or 0)
    H = int(getattr(doc, "ctn_height_mm", 0) or 0)
    flap = int(getattr(doc, "ctn_flap_mm", 0) or 0)
    joint_type = (getattr(doc, "joint_type", None) or "Stitched").strip()
    ply = (getattr(doc, "ply", None) or "").strip()

    if ply == "SFK" or L <= 0 or W <= 0:
        return ""

    if product_type in ("2 Flap RSC", "3 Flap RSC"):
        return _svg_two_flap_rsc(L, W, H, flap, joint_type)
    if product_type == "1 Flap RSC":
        return _svg_one_flap_rsc(L, W, H, flap, joint_type)
    if product_type == "Tray":
        return _svg_tray(L, W, H)

    return ""


# ── helpers ──────────────────────────────────────────────────────────────────

def _joint(joint_type):
    return _JOINT_CONFIG.get(joint_type, _JOINT_CONFIG["Stitched"])


def _rect(ox, oy, x, y, w, h, scale, fill, stroke="#333333", sw=1.5):
    rx = ox + x * scale
    ry = oy + y * scale
    rw = w * scale
    rh = h * scale
    return (
        f'<rect x="{rx:.1f}" y="{ry:.1f}" width="{rw:.1f}" height="{rh:.1f}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'
    )


def _text(x, y, label, size=10, fill="#333", weight="500", anchor="middle",
          baseline="middle", style=""):
    extra = f' font-style="{style}"' if style else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
        f'dominant-baseline="{baseline}" font-size="{size}" fill="{fill}" '
        f'font-weight="{weight}"{extra}>{label}</text>'
    )


def _line(x1, y1, x2, y2, stroke, sw=1.5, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{stroke}" stroke-width="{sw}"{d}/>'
    )


def _panel_label(ox, oy, p, scale, min_w=36):
    """Render a centred label inside a panel if it is wide enough."""
    if p["w"] * scale <= min_w:
        return ""
    fs = min(11, p["w"] * scale * 0.13)
    cx = ox + (p["x"] + p["w"] / 2) * scale
    cy = oy + (p["y"] + p["h"] / 2) * scale
    return _text(cx, cy, p["label"], size=round(fs, 1), fill="#333", weight="500")


# ── 2-Flap / 3-Flap RSC ─────────────────────────────────────────────────────

def _svg_two_flap_rsc(L, W, H, flap, joint_type):
    jt = _joint(joint_type)
    tab = jt["tabWidth"]
    totalW = tab + L + W + L + W
    totalH = flap + H + flap
    if totalW <= 0 or totalH <= 0:
        return ""

    scale = min(0.38, 500 / totalW, 300 / totalH)
    ox, oy = 25, 35
    svgW = totalW * scale + 60
    svgH = totalH * scale + 55

    parts = []
    parts.append(
        f'<svg width="{svgW:.0f}" height="{svgH:.0f}" '
        f'style="border:1px solid #ccc;border-radius:3px;background:#FAFAFA;">'
    )

    # body panels
    panels = [
        {"label": jt["label"], "x": 0, "y": flap, "w": tab, "h": H, "color": jt["color"]},
        {"label": f"Side ({W})", "x": tab, "y": flap, "w": L, "h": H,
         "color": _COLORS["side"] + "60"},
        {"label": f"Front ({L})", "x": tab + L, "y": flap, "w": W, "h": H,
         "color": _COLORS["face"] + "80"},
        {"label": f"Side ({W})", "x": tab + L + W, "y": flap, "w": L, "h": H,
         "color": _COLORS["side"] + "60"},
        {"label": f"Back ({L})", "x": tab + L + W + L, "y": flap, "w": W, "h": H,
         "color": _COLORS["face"] + "80"},
    ]

    # flaps
    xs = [tab, tab + L, tab + L + W, tab + L + W + L]
    ws = [L, W, L, W]
    fc = [_COLORS["top"] + "35", _COLORS["top"] + "50",
          _COLORS["top"] + "35", _COLORS["top"] + "50"]
    for i in range(4):
        panels.append({"label": "Top", "x": xs[i], "y": 0,
                        "w": ws[i], "h": flap, "color": fc[i]})
        panels.append({"label": "Btm", "x": xs[i], "y": flap + H,
                        "w": ws[i], "h": flap, "color": fc[i]})

    for p in panels:
        parts.append(_rect(ox, oy, p["x"], p["y"], p["w"], p["h"], scale, p["color"]))
        parts.append(_panel_label(ox, oy, p, scale))

    # vertical fold lines
    for fx in xs:
        parts.append(_line(ox + fx * scale, oy, ox + fx * scale,
                           oy + totalH * scale, _COLORS["fold"], 1.5, "6,4"))
    # horizontal fold lines
    for fy in (flap, flap + H):
        parts.append(_line(ox + tab * scale, oy + fy * scale,
                           ox + totalW * scale, oy + fy * scale,
                           _COLORS["fold"], 1, "4,3"))

    # joint markers
    parts.extend(_joint_markers(ox, oy, tab, H, flap, scale, jt))

    # dimension labels
    parts.append(_text(ox + (tab + L / 2) * scale, oy + totalH * scale + 12,
                       f"{L}mm", 9, "#666"))
    parts.append(_text(ox + (tab + L + W / 2) * scale, oy + totalH * scale + 12,
                       f"{W}mm", 9, "#666"))
    parts.append(_text(ox + totalW * scale + 5, oy + (flap + H / 2) * scale,
                       f"{H}mm", 9, "#666", anchor="start"))
    parts.append(_text(ox + totalW * scale + 5, oy + (flap / 2) * scale,
                       f"{flap}mm", 9, "#666", anchor="start"))
    parts.append(_text(ox + (tab / 2) * scale, oy - 7,
                       f"{tab}mm", 8, "#888"))

    # summary
    parts.append(_line(ox, oy + totalH * scale + 20,
                       ox + totalW * scale, oy + totalH * scale + 20,
                       "#999", 0.5))
    parts.append(_text(ox + (totalW / 2) * scale, oy + totalH * scale + 33,
                       f"Blank: {totalW}mm x {totalH}mm", 10,
                       _COLORS["primary"], "700"))

    parts.append("</svg>")
    return "\n".join(parts)


# ── 1-Flap RSC ──────────────────────────────────────────────────────────────

def _svg_one_flap_rsc(L, W, H, flap, joint_type):
    jt = _joint(joint_type)
    tab = jt["tabWidth"]
    totalW = tab + L + W + L + W
    totalH = H + flap
    if totalW <= 0 or totalH <= 0:
        return ""

    scale = min(0.38, 500 / totalW, 300 / totalH)
    ox, oy = 25, 35
    svgW = totalW * scale + 60
    svgH = totalH * scale + 55

    parts = []
    parts.append(
        f'<svg width="{svgW:.0f}" height="{svgH:.0f}" '
        f'style="border:1px solid #ccc;border-radius:3px;background:#FAFAFA;">'
    )

    # body panels (start at y=0)
    panels = [
        {"label": jt["label"], "x": 0, "y": 0, "w": tab, "h": H, "color": jt["color"]},
        {"label": f"Side ({W})", "x": tab, "y": 0, "w": L, "h": H,
         "color": _COLORS["side"] + "60"},
        {"label": f"Front ({L})", "x": tab + L, "y": 0, "w": W, "h": H,
         "color": _COLORS["face"] + "80"},
        {"label": f"Side ({W})", "x": tab + L + W, "y": 0, "w": L, "h": H,
         "color": _COLORS["side"] + "60"},
        {"label": f"Back ({L})", "x": tab + L + W + L, "y": 0, "w": W, "h": H,
         "color": _COLORS["face"] + "80"},
    ]

    # bottom flaps only
    xs = [tab, tab + L, tab + L + W, tab + L + W + L]
    ws = [L, W, L, W]
    fc = [_COLORS["top"] + "35", _COLORS["top"] + "50",
          _COLORS["top"] + "35", _COLORS["top"] + "50"]
    for i in range(4):
        panels.append({"label": "Flap", "x": xs[i], "y": H,
                        "w": ws[i], "h": flap, "color": fc[i]})

    for p in panels:
        parts.append(_rect(ox, oy, p["x"], p["y"], p["w"], p["h"], scale, p["color"]))
        parts.append(_panel_label(ox, oy, p, scale))

    # vertical fold lines
    for fx in xs:
        parts.append(_line(ox + fx * scale, oy, ox + fx * scale,
                           oy + totalH * scale, _COLORS["fold"], 1.5, "6,4"))
    # horizontal fold line (body/flap)
    parts.append(_line(ox + tab * scale, oy + H * scale,
                       ox + totalW * scale, oy + H * scale,
                       _COLORS["fold"], 1, "4,3"))

    # open end label
    parts.append(_text(ox + (totalW / 2) * scale, oy - 10,
                       "Open end (no flap)", 8, "#999", "400", style="italic"))

    # joint markers
    parts.extend(_joint_markers(ox, oy, tab, H, 0, scale, jt))

    # dimension labels
    parts.append(_text(ox + (tab + L / 2) * scale, oy + totalH * scale + 12,
                       f"{L}mm", 9, "#666"))
    parts.append(_text(ox + (tab + L + W / 2) * scale, oy + totalH * scale + 12,
                       f"{W}mm", 9, "#666"))
    parts.append(_text(ox + totalW * scale + 5, oy + (H / 2) * scale,
                       f"{H}mm", 9, "#666", anchor="start"))
    parts.append(_text(ox + totalW * scale + 5, oy + (H + flap / 2) * scale,
                       f"{flap}mm", 9, "#666", anchor="start"))
    parts.append(_text(ox + (tab / 2) * scale, oy - 7,
                       f"{tab}mm", 8, "#888"))

    # summary
    parts.append(_line(ox, oy + totalH * scale + 20,
                       ox + totalW * scale, oy + totalH * scale + 20,
                       "#999", 0.5))
    parts.append(_text(ox + (totalW / 2) * scale, oy + totalH * scale + 33,
                       f"Blank: {totalW}mm x {totalH}mm", 10,
                       _COLORS["primary"], "700"))

    parts.append("</svg>")
    return "\n".join(parts)


# ── Tray (FTD) ───────────────────────────────────────────────────────────────

def _svg_tray(L, W, H):
    totalW = H + W + H
    totalH = H + L + H
    if totalW <= 0 or totalH <= 0:
        return ""

    scale = min(0.50, 440 / totalW, 360 / totalH)
    ox, oy = 25, 25
    svgW = totalW * scale + 50
    svgH = totalH * scale + 55

    parts = []
    parts.append(
        f'<svg width="{svgW:.0f}" height="{svgH:.0f}" '
        f'style="border:1px solid #ccc;border-radius:3px;background:#FAFAFA;">'
    )

    # corner ear tabs
    ears = [
        {"x": 0, "y": 0, "w": H, "h": H},
        {"x": H + W, "y": 0, "w": H, "h": H},
        {"x": 0, "y": H + L, "w": H, "h": H},
        {"x": H + W, "y": H + L, "w": H, "h": H},
    ]
    for i, e in enumerate(ears):
        sx = ox + e["x"] * scale
        sy = oy + e["y"] * scale
        sw = e["w"] * scale
        sh = e["h"] * scale
        if i == 0:
            pts = f"{sx:.1f},{sy + sh:.1f} {sx + sw:.1f},{sy:.1f} {sx + sw:.1f},{sy + sh:.1f}"
        elif i == 1:
            pts = f"{sx:.1f},{sy:.1f} {sx + sw:.1f},{sy + sh:.1f} {sx:.1f},{sy + sh:.1f}"
        elif i == 2:
            pts = f"{sx + sw:.1f},{sy:.1f} {sx:.1f},{sy + sh:.1f} {sx + sw:.1f},{sy + sh:.1f}"
        else:
            pts = f"{sx:.1f},{sy:.1f} {sx + sw:.1f},{sy:.1f} {sx:.1f},{sy + sh:.1f}"
        parts.append(
            f'<polygon points="{pts}" fill="#E0E0E0" stroke="{_COLORS["cut"]}" '
            f'stroke-width="1" stroke-dasharray="3,3"/>'
        )

    # panels
    panels = [
        {"label": f"Base ({L}x{W})", "x": H, "y": H, "w": W, "h": L,
         "color": _COLORS["base"] + "50"},
        {"label": f"Front ({H})", "x": H, "y": 0, "w": W, "h": H,
         "color": _COLORS["trayWall"] + "50"},
        {"label": f"Back ({H})", "x": H, "y": H + L, "w": W, "h": H,
         "color": _COLORS["trayWall"] + "50"},
        {"label": f"Side ({H})", "x": 0, "y": H, "w": H, "h": L,
         "color": _COLORS["trayWall"] + "35"},
        {"label": f"Side ({H})", "x": H + W, "y": H, "w": H, "h": L,
         "color": _COLORS["trayWall"] + "35"},
    ]
    for p in panels:
        parts.append(_rect(ox, oy, p["x"], p["y"], p["w"], p["h"], scale, p["color"]))
        if p["w"] * scale > 45 and p["h"] * scale > 18:
            fs = min(10, min(p["w"], p["h"]) * scale * 0.14)
            cx = ox + (p["x"] + p["w"] / 2) * scale
            cy = oy + (p["y"] + p["h"] / 2) * scale
            parts.append(_text(cx, cy, p["label"], round(fs, 1), "#333", "500"))

    # fold lines
    parts.append(_line(ox + H * scale, oy, ox + H * scale,
                       oy + totalH * scale, _COLORS["fold"], 1.5, "6,4"))
    parts.append(_line(ox + (H + W) * scale, oy, ox + (H + W) * scale,
                       oy + totalH * scale, _COLORS["fold"], 1.5, "6,4"))
    parts.append(_line(ox, oy + H * scale, ox + totalW * scale,
                       oy + H * scale, _COLORS["fold"], 1.5, "6,4"))
    parts.append(_line(ox, oy + (H + L) * scale, ox + totalW * scale,
                       oy + (H + L) * scale, _COLORS["fold"], 1.5, "6,4"))

    # dimension labels
    parts.append(_text(ox + (H + W / 2) * scale, oy + totalH * scale + 12,
                       f"{W}mm", 9, "#666"))
    parts.append(_text(ox + (H / 2) * scale, oy + totalH * scale + 12,
                       f"{H}mm", 9, "#666"))
    parts.append(_text(ox + totalW * scale + 5, oy + (H + L / 2) * scale,
                       f"{L}mm", 9, "#666", anchor="start"))
    parts.append(_text(ox + totalW * scale + 5, oy + (H / 2) * scale,
                       f"{H}mm", 9, "#666", anchor="start"))

    # summary
    parts.append(_line(ox, oy + totalH * scale + 20,
                       ox + totalW * scale, oy + totalH * scale + 20,
                       "#999", 0.5))
    parts.append(_text(ox + (totalW / 2) * scale, oy + totalH * scale + 33,
                       f"Blank: {totalW}mm x {totalH}mm", 10,
                       _COLORS["primary"], "700"))

    parts.append("</svg>")
    return "\n".join(parts)


# ── shared: joint markers ────────────────────────────────────────────────────

def _joint_markers(ox, oy, tab, H, flap_offset, scale, jt):
    """Render stitch X-marks or glue dashed lines on the tab panel."""
    parts = []
    if jt["markerType"] == "stitch":
        spacing = 25
        count = int(H / spacing)
        start_y = flap_offset + (H - count * spacing) / 2
        for i in range(count + 1):
            cy = oy + (start_y + i * spacing) * scale
            cx = ox + (tab * 0.6) * scale
            parts.append(_line(cx - 3, cy - 3, cx + 3, cy + 3,
                               _COLORS["stitch"], 1.5))
            parts.append(_line(cx + 3, cy - 3, cx - 3, cy + 3,
                               _COLORS["stitch"], 1.5))
    elif jt["markerType"] == "glue":
        for frac in (0.25, 0.5, 0.75):
            gy = oy + (flap_offset + H * frac) * scale
            parts.append(
                f'<line x1="{ox + (tab * 0.2) * scale:.1f}" y1="{gy:.1f}" '
                f'x2="{ox + (tab * 0.8) * scale:.1f}" y2="{gy:.1f}" '
                f'stroke="{_COLORS["glue"]}" stroke-width="2" '
                f'stroke-dasharray="3,2" opacity="0.6"/>'
            )
    return parts
