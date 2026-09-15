# Copyright (c) 2026, Vimit Converters Ltd and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class JobCardLabelRun(Document):
	"""One design run on the flexo press — a row of the Job Card Label Run Log.

	Filled by the floor after the card is submitted. The minute fields and the
	card's rollups are computed by the parent, in ``JobCardLabel``, because a
	child controller's ``validate`` is not called when the parent saves.
	"""

	pass
