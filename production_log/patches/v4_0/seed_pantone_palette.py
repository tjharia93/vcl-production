"""
Patch v4_0: Seed the Pantone Colour master with a starter palette.

Ships ~60 common Pantone codes with friendly display names, approximate
sRGB hex values, and default CMYK mixing percentages. The friendly name
is what users and printed travellers will see ("Warm Red · 186 C"
instead of the bare code "186 C").

Hex + CMYK values are publicly-sourced approximations. Press operators
must still verify against physical Pantone chips.

Idempotent: existing records get their display_name refreshed (so palette
updates on re-seed) but any edits to hex or CMYK a designer has made are
preserved.
"""

import frappe


# (code, friendly_name, hex, c%, m%, y%, k%, category)
PALETTE = [
	# Process
	("Process Cyan C",    "Process Cyan",    "#00B2E3", 100,  0,  0,  0, "Solid"),
	("Process Magenta C", "Process Magenta", "#E6007E",   0, 100,  0,  0, "Solid"),
	("Process Yellow C",  "Process Yellow",  "#FFDE00",   0,   0, 100, 0, "Solid"),
	("Process Black C",   "Process Black",   "#1D1D1B",   0,   0,  0, 100, "Solid"),
	("Black C",           "Solid Black",     "#2D2926",  70,  50, 30, 100, "Solid"),
	# Reds / pinks
	("Warm Red C",   "Warm Red",    "#F9423A",   0, 85,  85,  0, "Solid"),
	("Red 032 C",    "Bright Red",  "#EF3340",   0, 90,  75,  0, "Solid"),
	("186 C",        "Classic Red", "#C8102E",   2, 100, 85,  6, "Solid"),
	("200 C",        "Deep Red",    "#BA0C2F",   3, 100, 70, 12, "Solid"),
	("485 C",        "Fire Red",    "#DA291C",   0, 95,  100, 0, "Solid"),
	("Rubine Red C", "Rubine",      "#CE0058",   0, 100, 18,  2, "Solid"),
	("Rhodamine Red C", "Hot Pink", "#E10098",   0, 96,   0,  0, "Solid"),
	("Pink C",       "Bright Pink", "#D62598",   0, 87,   3,  0, "Solid"),
	# Oranges / yellows
	("Orange 021 C", "Bright Orange", "#FE5000",   0,  67, 100, 0, "Solid"),
	("165 C",        "Tangerine",     "#FF6A13",   0,  70,  95, 0, "Solid"),
	("Yellow C",     "Pure Yellow",   "#FEDD00",   0,   0, 100, 0, "Solid"),
	("Yellow 012 C", "Gold Yellow",   "#FFD700",   0,   4, 100, 0, "Solid"),
	("116 C",        "Sunflower",     "#FFCD00",   0,  16, 100, 0, "Solid"),
	("7548 C",       "Amber",         "#FFC600",   0,  22, 100, 0, "Solid"),
	# Greens
	("Green C",      "Emerald Green", "#00AB84", 100,   0,  60, 0, "Solid"),
	("354 C",        "Bright Green",  "#00B140",  78,   0, 100, 0, "Solid"),
	("347 C",        "Kelly Green",   "#009739",  95,   0, 100, 0, "Solid"),
	("363 C",        "Forest Green",  "#4C8C2B",  75,   0, 100, 30, "Solid"),
	("376 C",        "Lime Green",    "#84BD00",  55,   0, 100, 0, "Solid"),
	# Blues
	("Process Blue C", "Sky Blue",    "#0085CA", 100, 13, 1, 3, "Solid"),
	("Reflex Blue C",  "Reflex Blue", "#001489", 100, 82, 0, 2, "Solid"),
	("286 C",        "Royal Blue",    "#0033A0", 100,  72,  0, 2, "Solid"),
	("072 C",        "Deep Blue",     "#10069F", 100,  88,  0, 5, "Solid"),
	("2728 C",       "True Blue",     "#0047BB", 100,  65,  0, 0, "Solid"),
	("299 C",        "Azure",         "#00A3E0",  85,  19,   0, 0, "Solid"),
	("2995 C",       "Cyan Blue",     "#00A9E0",  87,   8,   0, 0, "Solid"),
	# Purples / violets
	("Violet C",     "Violet",        "#440099",  92,  98,   0, 0, "Solid"),
	("Purple C",     "Royal Purple",  "#BB29BB",  36, 100,   0, 0, "Solid"),
	("266 C",        "Deep Purple",   "#5F249F",  80, 100,   0, 0, "Solid"),
	# Browns / warm neutrals
	("Warm Gray 1 C",  "Light Warm Gray", "#D7D2CB",   4,   5,  8, 10, "Solid"),
	("Warm Gray 5 C",  "Mid Warm Gray",   "#ADA49A",  10,  12, 18, 30, "Solid"),
	("Warm Gray 9 C",  "Dark Warm Gray",  "#83786F",  14,  24, 28, 50, "Solid"),
	("464 C",          "Mustard",         "#AD841F",  26,  44, 100, 11, "Solid"),
	("469 C",          "Chocolate Brown", "#693F23",  30,  68,  90, 48, "Solid"),
	# Cool neutrals
	("Cool Gray 1 C",  "Light Cool Gray", "#D9D9D6",   4,   2,  4, 10, "Solid"),
	("Cool Gray 3 C",  "Pale Gray",       "#C8C9C7",   6,   4,  6, 15, "Solid"),
	("Cool Gray 5 C",  "Mid Cool Gray",   "#B1B3B3",  10,   5,  8, 25, "Solid"),
	("Cool Gray 7 C",  "Steel Gray",      "#97999B",  20,  14, 12, 40, "Solid"),
	("Cool Gray 9 C",  "Slate Gray",      "#75787B",  30,  22, 17, 57, "Solid"),
	("Cool Gray 11 C", "Charcoal Gray",   "#53565A",  44,  34, 22, 77, "Solid"),
	# Metallics
	("Silver 877 C",   "Silver",          "#8A8D8F",  20,  15,  14, 40, "Metallic"),
	("Gold 871 C",     "Gold",            "#85754E",  26,  38,  80, 30, "Metallic"),
	("Copper 876 C",   "Copper",          "#955F3B",  26,  62,  80, 20, "Metallic"),
	# Fluorescents
	("806 C",          "Neon Pink",       "#FF3EB5",   0,  76,   0,  0, "Fluorescent"),
	("811 C",          "Neon Orange",     "#FF5A36",   0,  76,  90, 0, "Fluorescent"),
	("803 C",          "Neon Yellow",     "#FFF200",   0,   0, 100, 0, "Fluorescent"),
	("802 C",          "Neon Green",      "#44D62C",  60,   0, 100, 0, "Fluorescent"),
]


def _display_name(friendly, code):
	"""Friendly-first format so the grid and traveller show human-readable names."""
	return f"{friendly} \u00b7 {code}"  # e.g. "Warm Red · 186 C"


def execute():
	for code, friendly, hex_value, c, m, y, k, category in PALETTE:
		display_name = _display_name(friendly, code)

		if frappe.db.exists("Pantone Colour", code):
			# Refresh display_name on re-seed (palette naming may improve over time)
			# but leave hex + CMYK alone in case a designer has tweaked them.
			frappe.db.set_value(
				"Pantone Colour", code,
				"display_name", display_name,
				update_modified=False,
			)
			continue

		frappe.get_doc({
			"doctype":          "Pantone Colour",
			"code":             code,
			"display_name":     display_name,
			"hex_value":        hex_value,
			"default_cmyk_c":   c,
			"default_cmyk_m":   m,
			"default_cmyk_y":   y,
			"default_cmyk_k":   k,
			"category":         category,
		}).insert(ignore_permissions=True)

	frappe.db.commit()
