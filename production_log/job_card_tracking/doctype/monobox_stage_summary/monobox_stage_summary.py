from frappe.model.document import Document


class MonoboxStageSummary(Document):
	"""One row of the Monobox job card close-out: what a stage actually cost.

	Summary level by design. The per-run detail stays on the paper traveller
	until digital floor capture exists — see the iteration-two list in
	docs/superpowers/specs/2026-08-05-monobox-job-card-design.md.
	"""

	pass
