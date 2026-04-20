import frappe
from frappe.model.document import Document


class PantoneColour(Document):
	def validate(self):
		for f in ("default_cmyk_c", "default_cmyk_m", "default_cmyk_y", "default_cmyk_k"):
			v = getattr(self, f) or 0
			if v < 0 or v > 100:
				frappe.throw(f"{self.meta.get_label(f)} must be between 0 and 100.")


@frappe.whitelist()
def find_nearest(hex_value, limit=5):
	"""
	Return up to `limit` Pantone Colour records whose hex_value is closest to
	the supplied hex, sorted by Delta-E (LAB-space) distance.
	Used by the Spot Colour child-row "Find nearest Pantones" dialog.
	"""
	target = _hex_to_lab(hex_value)
	if target is None:
		return []

	candidates = frappe.get_all(
		"Pantone Colour",
		fields=["name", "code", "display_name", "hex_value", "category",
				"default_cmyk_c", "default_cmyk_m", "default_cmyk_y", "default_cmyk_k"],
	)

	scored = []
	for c in candidates:
		lab = _hex_to_lab(c.get("hex_value"))
		if lab is None:
			continue
		c["_distance"] = _delta_e(target, lab)
		scored.append(c)

	scored.sort(key=lambda x: x["_distance"])
	return scored[: int(limit)]


def _hex_to_lab(hex_str):
	rgb = _hex_to_rgb(hex_str)
	if rgb is None:
		return None
	return _rgb_to_lab(rgb)


def _hex_to_rgb(hex_str):
	if not hex_str:
		return None
	h = hex_str.strip().lstrip("#")
	if len(h) == 3:
		h = "".join(ch * 2 for ch in h)
	if len(h) != 6:
		return None
	try:
		return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
	except ValueError:
		return None


def _rgb_to_lab(rgb):
	# sRGB -> linear
	def linearize(v):
		v = v / 255.0
		return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

	r, g, b = (linearize(v) for v in rgb)

	# linear RGB -> XYZ (D65)
	x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
	y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
	z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041

	# normalise by D65 reference white
	x /= 0.95047
	z /= 1.08883

	def f(t):
		return t ** (1 / 3) if t > 0.008856 else (7.787 * t) + (16 / 116)

	fx, fy, fz = f(x), f(y), f(z)
	L = 116 * fy - 16
	a = 500 * (fx - fy)
	bb = 200 * (fy - fz)
	return (L, a, bb)


def _delta_e(lab1, lab2):
	return sum((a - b) ** 2 for a, b in zip(lab1, lab2)) ** 0.5
