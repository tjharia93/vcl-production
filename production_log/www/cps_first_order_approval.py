from urllib.parse import quote

import frappe


def get_context(context):
	context.no_cache = 1
	context.title = "CPS and price approval"
	if frappe.session.user == "Guest":
		request = frappe.local.request
		target = request.path + ("?" + request.query_string.decode() if request.query_string else "")
		frappe.local.flags.redirect_location = "/login?redirect-to=" + quote(target, safe="")
		raise frappe.Redirect
