"""A job card's route, and where each of its stages can actually run.

Two jobs, both pure so they can be tested without a bench:

  DERIVE    - turn a card into an ordered list of stage names
  TRANSLATE - turn a stage name into the Workstation Types that serve it

The translation exists because the two vocabularies are genuinely different
and neither is wrong. A card names a step in ITS product's route - "Printing".
A machine names the kind of work its station does - "Reel to Reel Printing",
"Carton Printing". The same word means a Miyakoshi on one card and a flexo
press on another, so renaming either side would collide. It is a many-to-one
mapping per product type, which makes it data.
"""

# A stage that happens, but never on a machine board. Design and film work are
# steps on the traveller; nobody records production against them.
OFFICE = "office"

# A real floor stage with no station type yet. Shown, unticked, so the gap is
# visible - never dropped, which would make the route look shorter than it is.
UNSTAFFED = ()


STAGE_MAP = {
	"Job Card Computer Paper": {
		"Design": OFFICE,
		"Pending Films": OFFICE,
		# Reel-FED printing. Says nothing about whether the press can produce a
		# finished reel - M4 and Roland cannot. Never infer route capability
		# from a station type.
		"Printing": ("Reel to Reel Printing", "Sheet to Sheet Printing"),
		"Collation": ("Collation",),
		# Should be the collator that numbers. Only one Collator exists in the
		# machine master today, so it cannot be narrowed yet.
		"Numbering": ("Collation",),
		# A real step. Tanuj decided against adding a packing machine, so it
		# stays visible and unplannable rather than invented.
		"Pack": UNSTAFFED,
	},
	"Job Card Carton": {
		"Corrugated": ("Corrugation",),
		# Sheeting and Creasing have Workstation Types but NO machines, so they
		# resolve and then show unticked. That is the honest outcome.
		"Sheeting": ("Sheeting",),
		"Pasting": ("Carton Pasting",),
		"Creasing and Slitting": ("Creasing",),
		"Printing": ("Carton Printing",),
		"Die-cutting and Stripping": ("Die Cutting",),
		"Slotting": ("Slotting",),
		"Stitching": ("Carton Stitching",),
		"Gluing": ("Carton Gluing",),
		"Bundling": ("Bundling",),
	},
}


def resolve_stage(doctype, stage):
	"""Where this stage can run, and whether it belongs on the floor at all.

	An unmapped stage - or an unmapped card type - resolves to an unstaffed
	FLOOR stage rather than raising. One stage nobody has mapped must not hide
	a whole route.
	"""
	stage = (stage or "").strip()
	mapped = STAGE_MAP.get(doctype, {}).get(stage)

	if mapped == OFFICE:
		return {"stage": stage, "office": True, "types": ()}
	return {"stage": stage, "office": False, "types": tuple(mapped or ())}
