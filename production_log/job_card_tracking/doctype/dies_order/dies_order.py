import frappe
from frappe.model.document import Document


class DiesOrder(Document):
	"""
	Dies Order DocType - Child table for tracking orders placed for printing dies.

	This table stores order information for each die including order date, 
	order number, quantity, and status (active or discarded).
	"""
	pass
