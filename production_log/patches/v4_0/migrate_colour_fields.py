"""
Patch v4_0: Migrate pre-existing colour data into the new shared Print Colours model.

Old fields being removed:
  - Customer Product Specification:
      no_of_colours_carton       (Select 0-4)
      colours_details            (Data, free text)
      label_number_of_colours    (Int)
  - Job Card Label:
      label_number_of_colours    (Int)
      job_colours                (Data, free text)
  - Job Card Carton:
      no_of_colours              (Select 0-4, mirrored from spec)
      colours_details            (Data, mirrored from spec)

Strategy:
  1. For each row, copy any surviving old free-text values into colour_notes
     (appending with a prefix so the original source is traceable).
  2. For each row with a numeric old value (no_of_colours_carton or
     label_number_of_colours), set number_of_colours to that value so
     existing jobs keep a sensible count until the designer restructures them.
  3. Drop the old columns once data has been migrated.

Not attempted: reverse-engineering free-text strings into structured
spot_colours rows. Users need to re-enter any spec they want structured
(usually faster than parsing heuristics and always correct).

Safe to run multiple times (idempotent).
"""

import frappe


# (table_name, old_column, copy_into_number_of_colours_if_numeric)
OLD_COLUMNS = [
	("tabCustomer Product Specification", "no_of_colours_carton",    True),
	("tabCustomer Product Specification", "colours_details",         False),
	("tabCustomer Product Specification", "label_number_of_colours", True),
	("tabJob Card Label",                 "label_number_of_colours", True),
	("tabJob Card Label",                 "job_colours",             False),
	("tabJob Card Carton",                "no_of_colours",           True),
	("tabJob Card Carton",                "colours_details",         False),
]


def execute():
	for table, column, is_numeric in OLD_COLUMNS:
		if not frappe.db.table_exists(table):
			continue

		existing_cols = {
			row[0] for row in frappe.db.sql(f"SHOW COLUMNS FROM `{table}`")
		}
		if column not in existing_cols:
			continue

		_migrate_column(table, column, is_numeric)

		frappe.db.commit()
		frappe.db.sql_ddl(f"ALTER TABLE `{table}` DROP COLUMN `{column}`")

	_remove_custom_fields_if_any()
	frappe.clear_cache()
	frappe.db.commit()


def _migrate_column(table, column, is_numeric):
	# Fetch all non-empty values
	rows = frappe.db.sql(
		f"SELECT name, `{column}` FROM `{table}` WHERE `{column}` IS NOT NULL AND `{column}` != ''",
		as_dict=True,
	)

	for row in rows:
		val = row.get(column)
		if val in (None, "", "0"):
			continue

		# Numeric → also populate number_of_colours (only if currently empty/zero)
		if is_numeric:
			try:
				n = int(str(val).strip())
			except (TypeError, ValueError):
				n = None
			if n:
				current = frappe.db.get_value(
					_doctype_from_table(table), row["name"], "number_of_colours"
				)
				if not current:
					frappe.db.set_value(
						_doctype_from_table(table), row["name"],
						"number_of_colours", n,
						update_modified=False,
					)

		# Append human-readable note to colour_notes
		current_notes = frappe.db.get_value(
			_doctype_from_table(table), row["name"], "colour_notes"
		) or ""
		prefix = f"[migrated {column}] "
		if prefix in current_notes:
			continue
		new_notes = (current_notes + ("\n" if current_notes else "") + prefix + str(val)).strip()
		frappe.db.set_value(
			_doctype_from_table(table), row["name"],
			"colour_notes", new_notes,
			update_modified=False,
		)


def _doctype_from_table(table):
	return table[3:] if table.startswith("tab") else table


def _remove_custom_fields_if_any():
	# Safety: if any of these ever became Custom Fields on the live site, drop them.
	targets = [
		("Customer Product Specification", "no_of_colours_carton"),
		("Customer Product Specification", "colours_details"),
		("Customer Product Specification", "label_number_of_colours"),
		("Job Card Label",                 "label_number_of_colours"),
		("Job Card Label",                 "job_colours"),
		("Job Card Carton",                "no_of_colours"),
		("Job Card Carton",                "colours_details"),
	]
	for dt, fieldname in targets:
		cf = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": fieldname})
		if cf:
			frappe.delete_doc("Custom Field", cf, force=True, ignore_permissions=True)
