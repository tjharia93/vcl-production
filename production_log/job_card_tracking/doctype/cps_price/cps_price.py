from frappe.model.document import Document


class CPSPrice(Document):
	"""One effective-dated, approvable rate on a Customer Product Specification.

	Row-level rules (duplicate effective dates, approval revocation on edit)
	need the whole table to be visible, so they live on the parent controller in
	``customer_product_specification.py`` rather than here.
	"""

	pass
