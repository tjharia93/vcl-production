"""
Patch v4_0: Seed the Pantone Colour master with a starter palette.

Ships ~60 common Pantone codes with approximate sRGB hex values and default
CMYK mixing percentages, sourced from publicly-available references. These
are approximations only — press operators must still verify against physical
Pantone chips.

Safe to run multiple times (idempotent): existing records are left untouched.
Admins can edit, add, or remove entries anytime via Desk.
"""

import frappe


# (code, display_name, hex, c%, m%, y%, k%, category)
PALETTE = [
	# Process
	("Process Cyan C",    "Pantone Process Cyan C",    "#00B2E3", 100,  0,  0,  0, "Solid"),
	("Process Magenta C", "Pantone Process Magenta C", "#E6007E",   0, 100,  0,  0, "Solid"),
	("Process Yellow C",  "Pantone Process Yellow C",  "#FFDE00",   0,   0, 100, 0, "Solid"),
	("Process Black C",   "Pantone Process Black C",   "#1D1D1B",   0,   0,  0, 100, "Solid"),
	("Black C",           "Pantone Black C",           "#2D2926",  70,  50,  30, 100, "Solid"),
	# Reds / pinks
	("Warm Red C",   "Pantone Warm Red C",   "#F9423A",   0, 85,  85,  0, "Solid"),
	("Red 032 C",    "Pantone Red 032 C",    "#EF3340",   0, 90,  75,  0, "Solid"),
	("186 C",        "Pantone 186 C",        "#C8102E",   2, 100, 85,  6, "Solid"),
	("200 C",        "Pantone 200 C",        "#BA0C2F",   3, 100, 70,  12, "Solid"),
	("485 C",        "Pantone 485 C",        "#DA291C",   0, 95,  100, 0, "Solid"),
	("Rubine Red C", "Pantone Rubine Red C", "#CE0058",   0, 100, 18,  2, "Solid"),
	("Rhodamine Red C", "Pantone Rhodamine Red C", "#E10098", 0, 96, 0,   0, "Solid"),
	("Pink C",       "Pantone Pink C",       "#D62598",   0, 87,   3,  0, "Solid"),
	# Oranges / yellows
	("Orange 021 C", "Pantone Orange 021 C", "#FE5000",   0,  67, 100, 0, "Solid"),
	("165 C",        "Pantone 165 C",        "#FF6A13",   0,  70,  95, 0, "Solid"),
	("Yellow C",     "Pantone Yellow C",     "#FEDD00",   0,   0, 100, 0, "Solid"),
	("Yellow 012 C", "Pantone Yellow 012 C", "#FFD700",   0,   4, 100, 0, "Solid"),
	("116 C",        "Pantone 116 C",        "#FFCD00",   0,  16, 100, 0, "Solid"),
	("7548 C",       "Pantone 7548 C",       "#FFC600",   0,  22, 100, 0, "Solid"),
	# Greens
	("Green C",      "Pantone Green C",      "#00AB84", 100,   0,  60, 0, "Solid"),
	("354 C",        "Pantone 354 C",        "#00B140",  78,   0, 100, 0, "Solid"),
	("347 C",        "Pantone 347 C",        "#009739",  95,   0, 100, 0, "Solid"),
	("363 C",        "Pantone 363 C",        "#4C8C2B",  75,   0, 100, 30, "Solid"),
	("376 C",        "Pantone 376 C",        "#84BD00",  55,   0, 100, 0, "Solid"),
	# Blues
	("Process Blue C", "Pantone Process Blue C", "#0085CA", 100, 13, 1, 3, "Solid"),
	("Reflex Blue C",  "Pantone Reflex Blue C",  "#001489", 100, 82,  0, 2, "Solid"),
	("286 C",        "Pantone 286 C",        "#0033A0", 100,  72,  0, 2, "Solid"),
	("072 C",        "Pantone 072 C",        "#10069F", 100,  88,  0, 5, "Solid"),
	("2728 C",       "Pantone 2728 C",       "#0047BB", 100,  65,  0, 0, "Solid"),
	("299 C",        "Pantone 299 C",        "#00A3E0",  85,  19,   0, 0, "Solid"),
	("2995 C",       "Pantone 2995 C",       "#00A9E0",  87,   8,   0, 0, "Solid"),
	# Purples / violets
	("Violet C",     "Pantone Violet C",     "#440099",  92,  98,   0, 0, "Solid"),
	("Purple C",     "Pantone Purple C",     "#BB29BB",  36, 100,   0, 0, "Solid"),
	("266 C",        "Pantone 266 C",        "#5F249F",  80, 100,   0, 0, "Solid"),
	# Browns / warm neutrals
	("Warm Gray 1 C",  "Pantone Warm Gray 1 C",  "#D7D2CB",   4,   5,  8, 10, "Solid"),
	("Warm Gray 5 C",  "Pantone Warm Gray 5 C",  "#ADA49A",  10,  12, 18, 30, "Solid"),
	("Warm Gray 9 C",  "Pantone Warm Gray 9 C",  "#83786F",  14,  24, 28, 50, "Solid"),
	("464 C",          "Pantone 464 C",          "#AD841F",  26,  44,  100, 11, "Solid"),
	("469 C",          "Pantone 469 C",          "#693F23",  30,  68,  90, 48, "Solid"),
	# Cool neutrals
	("Cool Gray 1 C",  "Pantone Cool Gray 1 C",  "#D9D9D6",   4,   2,  4, 10, "Solid"),
	("Cool Gray 3 C",  "Pantone Cool Gray 3 C",  "#C8C9C7",   6,   4,  6, 15, "Solid"),
	("Cool Gray 5 C",  "Pantone Cool Gray 5 C",  "#B1B3B3",  10,   5,  8, 25, "Solid"),
	("Cool Gray 7 C",  "Pantone Cool Gray 7 C",  "#97999B",  20,  14, 12, 40, "Solid"),
	("Cool Gray 9 C",  "Pantone Cool Gray 9 C",  "#75787B",  30,  22, 17, 57, "Solid"),
	("Cool Gray 11 C", "Pantone Cool Gray 11 C", "#53565A",  44,  34, 22, 77, "Solid"),
	# Metallics
	("Silver 877 C",   "Pantone Silver 877 C",   "#8A8D8F",  20,  15,  14, 40, "Metallic"),
	("Gold 871 C",     "Pantone Gold 871 C",     "#85754E",  26,  38,  80, 30, "Metallic"),
	("Copper 876 C",   "Pantone Copper 876 C",   "#955F3B",  26,  62,  80, 20, "Metallic"),
	# Fluorescents
	("Neon Pink 806 C",   "Pantone 806 C",    "#FF3EB5",   0,  76,  0,  0, "Fluorescent"),
	("Neon Orange 811 C", "Pantone 811 C",    "#FF5A36",   0,  76,  90, 0, "Fluorescent"),
	("Neon Yellow 803 C", "Pantone 803 C",    "#FFF200",   0,   0, 100, 0, "Fluorescent"),
	("Neon Green 802 C",  "Pantone 802 C",    "#44D62C",  60,   0, 100, 0, "Fluorescent"),
]


def execute():
	for code, display_name, hex_value, c, m, y, k, category in PALETTE:
		if frappe.db.exists("Pantone Colour", code):
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
