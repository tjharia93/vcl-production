import frappe


def after_install():
	"""Run after app installation."""
	frappe.msgprint(
		"Production Log installed. "
		"Open the VCL Production workspace to start creating Customer "
		"Product Specifications and Job Cards."
	)
