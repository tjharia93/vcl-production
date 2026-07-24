import json
from pathlib import Path


FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


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
