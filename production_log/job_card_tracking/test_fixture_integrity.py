"""Static checks on the exported fixtures, against the faults that have actually
stopped a migrate.

Every assertion below is a deploy that failed. `bench migrate` imports each
fixture row as a document, and a fixture is the one artefact nobody reads before
pushing — it is generated, it is 169 records long, and the failure it causes
lands in `import_file_by_path` with no clue which record is at fault.

Three faults, three checks:

  1. **A row without `doctype`** — `KeyError: 'doctype'` aborts fixture sync for
     every app. Fixed once, then reintroduced by a later merge whose branch
     predated the fix; that recurrence is why these run in CI-less repo tests.
  2. **A Custom Field on a fieldname the app's own DocType already declares** —
     `import_doc` sets `__islocal`, so every fixture record is is_new(), and
     CustomField.validate refuses a new field whose fieldname is already in the
     assembled meta: `ValidationError: A field with the name X already exists`.
  3. **A Custom Field a patch has deliberately retired** — the fixture
     resurrects it on every migrate, quietly undoing the patch.

Checks 2 and 3 are the same assertion from opposite ends: a fieldname must be
owned by the DocType JSON or by the fixture, never by both.
"""
import json
from pathlib import Path


FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
APP_DIR = Path(__file__).resolve().parents[1]


def test_every_exported_fixture_row_has_doctype_and_name():
	"""Frappe imports fixture rows as documents and requires both identity keys."""
	for fixture_path in sorted(FIXTURES_DIR.glob("*.json")):
		rows = json.loads(fixture_path.read_text(encoding="utf-8"))
		assert isinstance(rows, list), f"{fixture_path.name} must contain a JSON list"
		for index, row in enumerate(rows):
			assert row.get("doctype"), (
				f"{fixture_path.name} row {index} ({row.get('name', 'unnamed')}) "
				"is missing doctype"
			)
			assert row.get("name"), (
				f"{fixture_path.name} row {index} is missing name"
			)


def test_custom_field_fixture_rows_identify_their_doctype():
	rows = json.loads(
		(FIXTURES_DIR / "custom_field.json").read_text(encoding="utf-8")
	)
	assert rows
	assert all(row["doctype"] == "Custom Field" for row in rows)


def _native_fieldnames():
	"""Fieldnames each app-owned DocType declares in its own JSON."""
	owned = {}
	for path in sorted(APP_DIR.glob("*/doctype/*/*.json")):
		doc = json.loads(path.read_text(encoding="utf-8"))
		if doc.get("doctype") != "DocType":
			continue
		owned[doc["name"]] = {
			f["fieldname"] for f in doc.get("fields", []) if f.get("fieldname")
		}
	return owned


def test_no_custom_field_collides_with_an_app_docfield():
	"""A fieldname belongs to the DocType JSON or to the fixture — never both.

	Two live deploys died here. `Job Card ETR.print_type` was declared by both,
	with different option lists; `Job Card Label.sales_order` and
	`.sales_order_item` were retired into DocFields by patches/v8_2 and then
	resurrected by the fixture on every migrate, undoing the patch each time.

	Both read identically at import: ValidationError, "A field with the name X
	already exists in Y", after the patches have already run.
	"""
	native = _native_fieldnames()
	assert native, "no app DocType JSON found — the glob is wrong, not the fixture"

	rows = json.loads((FIXTURES_DIR / "custom_field.json").read_text(encoding="utf-8"))
	collisions = [
		f"{row['dt']}.{row['fieldname']} (fixture row {row.get('name')})"
		for row in rows
		if row.get("dt") in native and row.get("fieldname") in native[row["dt"]]
	]
	assert not collisions, (
		"these fieldnames are declared by BOTH the DocType JSON and the Custom "
		"Field fixture, which fails migrate at fixture sync: " + ", ".join(collisions)
	)
