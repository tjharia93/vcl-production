"""First-order policy and SO-hook tests without a bench.

The DB double exercises the claim protocol, not InnoDB isolation. Real two-
connection submit/rollback checks remain a deployment acceptance requirement.
"""

import ast
import datetime
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch

from production_log.job_card_tracking import cps_first_order_price as claims
from production_log.job_card_tracking import cps_price_rules, cps_rules


class Record(dict):
	__getattr__ = dict.__getitem__
	__setattr__ = dict.__setitem__

	def set(self, key, value):
		self[key] = value


class ClaimDB:
	def __init__(self, **stored):
		self.stored = stored
		self.locks = []
		self.writes = []

	def sql(self, query, args, as_dict=False):
		assert "FOR UPDATE" in query
		assert "tabSales Order" not in query  # Never invert Release's lock order.
		name = args[0]
		self.locks.append(name)
		return [Record(name=name, modified="2026-11-10 10:00:00",
		               first_submitted_sales_order=self.stored[name])] if name in self.stored else []

	def set_value(self, doctype, name, field, value, update_modified):
		assert doctype == claims.DOCTYPE and field == claims.CLAIM_FIELD
		assert not update_modified
		self.stored[name] = value
		self.writes.append((name, value))


def price(**values):
	row = dict(name="price-draft", approval_status="Draft", valid_from="2026-11-01",
	           approved_on=None, currency="KES", uom="Carton", rate=3793.1034,
	           conversion_factor=1)
	row.update(values)
	return row


class TestClaims(unittest.TestCase):
	def test_locks_are_unique_sorted_and_read_current_claim(self):
		db = ClaimDB(B="SO-old", A=None)
		locked = claims.lock_specs(db, ["B", "A", "A", None])
		self.assertEqual(db.locks, ["A", "B"])
		self.assertEqual(locked["B"][claims.CLAIM_FIELD], "SO-old")

	def test_first_submit_claims_once_and_duplicate_lines_do_not_reclaim(self):
		db = ClaimDB(A=None, B=None)
		claims.claim_locked_specs(db, claims.lock_specs(db, ["A", "A", "B"]), "SO-1")
		claims.claim_locked_specs(db, claims.lock_specs(db, ["B", "A"]), "SO-2")
		self.assertEqual(db.stored, {"A": "SO-1", "B": "SO-1"})
		self.assertEqual(db.writes, [("A", "SO-1"), ("B", "SO-1")])
		self.assertFalse(claims.blocks_draft_price("SO-1", "SO-1"))
		self.assertTrue(claims.blocks_draft_price("SO-1", "SO-2"))

	def test_stale_and_forged_cps_edits_cannot_clear_or_replace_claim(self):
		for supplied in (None, "SO-fake", "SO-before-cancellation"):
			db = ClaimDB(A="SO-1")
			doc = Record(name="A", first_submitted_sales_order=supplied)
			doc.is_new = lambda: False
			claims.preserve_claim(doc, db)
			self.assertEqual(doc[claims.CLAIM_FIELD], "SO-1")

	def test_new_spec_cannot_import_a_claim(self):
		doc = Record(name="new", first_submitted_sales_order="SO-fake")
		doc.is_new = lambda: True
		claims.preserve_claim(doc, ClaimDB())
		self.assertIsNone(doc[claims.CLAIM_FIELD])

	def test_schema_keeps_claim_hidden_uncopied_and_off_prints(self):
		base = Path(__file__).parent
		meta = json.loads((base / "doctype/customer_product_specification/customer_product_specification.json").read_text())
		field = next(f for f in meta["fields"] if f["fieldname"] == claims.CLAIM_FIELD)
		for key in ("hidden", "read_only", "no_copy", "print_hide", "allow_on_submit"):
			self.assertEqual(field[key], 1)

	def test_backfill_preserves_existing_use_and_is_idempotent(self):
		db = ClaimDB(A=None, B="SO-claimed")
		original_sql = db.sql
		queries = []

		def sql(query, args=None, as_dict=False):
			queries.append(query)
			if "INNER JOIN" in query:
				return [Record(cps="A", sales_order="SO-first"),
				        Record(cps="A", sales_order="SO-second"),
				        Record(cps="B", sales_order="SO-history")]
			return original_sql(query, args, as_dict)

		db.sql = sql
		db.has_column = lambda *args: True
		with patch.dict(sys.modules, {"frappe": SimpleNamespace(db=db)}):
			claims.after_migrate()
			claims.after_migrate()
		self.assertEqual(db.stored, {"A": "SO-first", "B": "SO-claimed"})
		self.assertEqual(db.writes, [("A", "SO-first")])
		self.assertIn("so.docstatus IN (1, 2)", queries[0])

	def test_claim_protection_runs_for_save_update_and_cancel(self):
		base = Path(__file__).parent
		tree = ast.parse((base / "doctype/customer_product_specification/customer_product_specification.py").read_text(encoding="utf-8"))
		cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
		for name in ("validate", "before_update_after_submit", "before_cancel"):
			method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name)
			calls = [node.func.attr for node in ast.walk(method) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
			self.assertIn("preserve_first_order_claim", calls)


class TestDraftSelection(unittest.TestCase):
	def test_selection_is_separate_from_normal_approved_path(self):
		draft = price()
		rows = [draft]
		self.assertIsNone(cps_price_rules.select_price_row(rows, "KES", "2026-11-10"))
		self.assertIs(cps_price_rules.select_draft_price_row(rows, "KES", "2026-11-10"), draft)
		self.assertEqual(draft["approval_status"], "Draft")

	def test_no_price_rejected_future_and_other_currency_are_not_draft_allowances(self):
		for rows in ([], [price(approval_status="Rejected")], [price(valid_from="2026-11-11")], [price(currency="USD")]):
			self.assertIsNone(cps_price_rules.select_draft_price_row(rows, "KES", "2026-11-10"))

	def test_draft_selection_is_deterministic_and_allows_zero(self):
		rows = [price(name="a"), price(name="b", rate=0), price(name="older", valid_from="2026-10-31")]
		self.assertEqual(cps_price_rules.select_draft_price_row(rows, "KES", "2026-11-10")["name"], "b")

	def test_submit_price_read_is_current_locked_and_parent_scoped(self):
		path = Path(__file__).with_name("cps_pricing.py")
		tree = ast.parse(path.read_text(encoding="utf-8"))
		function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "get_order_price_candidates")
		rows = [price(), price(name="approved", approval_status="Approved")]
		sql = Mock(return_value=rows)
		scope = dict(frappe=SimpleNamespace(db=SimpleNamespace(sql=sql)),
		             _row_fields=lambda: list(rows[0]), cps_price_rules=cps_price_rules)
		exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), scope)
		approved, draft = scope["get_order_price_candidates"]("A", "2026-11-10", "KES", lock=True)
		self.assertEqual(approved["name"], "approved")
		self.assertEqual(draft["name"], "price-draft")
		query, params = sql.call_args.args
		self.assertIn("ORDER BY name FOR UPDATE", query)
		self.assertEqual(params, ("A", "Customer Product Specification", "pricing"))


class TestSalesOrderHook(unittest.TestCase):
	def setUp(self):
		# Execute the actual hook functions with explicit dependencies, without
		# importing a fake global frappe module into other test suites.
		path = Path(__file__).with_name("so_spec_control.py")
		tree = ast.parse(path.read_text(encoding="utf-8"))
		functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
		             and node.name in ("validate", "_validate_line", "on_submit")]
		self.db = ClaimDB(A=None)
		self.rows = [price()]
		self.warnings = []
		self.spec = Record(name="A", modified="2026-11-10 10:00:00", first_submitted_sales_order=None)
		self.doc = Record(name="SO-1", docstatus=1, transaction_date="2026-11-10", currency="KES",
		                  items=[Record(item_code="ITEM", custom_cps="A")])
		self.stamp = Mock()
		self.check = Mock()
		self.clear = Mock()
		self.ledger_ready = True
		self.mode = cps_rules.QUOTE_MODE_ENFORCE

		def throwing(*args):
			raise ValueError(str(args[-1]))

		def candidates(cps, on_date, currency, lock=False):
			return (cps_price_rules.select_price_row(self.rows, currency, on_date),
			        cps_price_rules.select_draft_price_row(self.rows, currency, on_date))

		self.scope = dict(
			frappe=SimpleNamespace(db=self.db, flags=SimpleNamespace(), throw=throwing,
			                       utils=SimpleNamespace(get_datetime=datetime.datetime.fromisoformat, formatdate=str)),
			_=lambda text: text, cps_rules=cps_rules, cps_first_order_price=claims,
			cps_pricing=SimpleNamespace(get_order_price_candidates=candidates,
			                           get_eligible_price=lambda *args: cps_price_rules.select_price_row(self.rows, args[2], args[1])),
			so_mode=lambda: self.mode, control_enabled=lambda: self.mode != cps_rules.QUOTE_MODE_OFF,
			_has_field=lambda dt, field: self.ledger_ready if field == claims.CLAIM_FIELD else True,
			rounding_allowance_settings=lambda: (1, 1),
			resolve_item_control=lambda item: SimpleNamespace(controlled=True),
			_load_and_validate_spec=lambda doc, line: self.spec,
			_validate_price=self.check, _stamp_snapshot=self.stamp,
			_clear_snapshot=self.clear, _validate_qty_against_job_cards=Mock(),
			_throw=throwing, _warn=lambda line, message: self.warnings.append(message),
		)
		exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), "exec"), self.scope)

	def validate(self):
		self.scope["validate"](self.doc)

	def submit(self):
		self.validate()
		self.scope["on_submit"](self.doc)

	def test_first_order_submits_with_draft_price_and_second_is_blocked(self):
		self.submit()
		self.check.assert_called_once()
		self.assertEqual(self.db.stored["A"], "SO-1")
		self.assertEqual(self.rows[0]["approval_status"], "Draft")
		self.doc.name = "SO-2"
		with self.assertRaisesRegex(ValueError, "already used by SO-1"):
			self.submit()

	def test_repeated_lines_share_one_order_and_revalidation_is_idempotent(self):
		self.doc.items = self.doc["items"] * 2  # Record attribute avoids dict.items.
		self.submit()
		self.submit()
		self.assertEqual(self.db.writes, [("A", "SO-1")])
		self.assertEqual(self.stamp.call_count, 4)

	def test_draft_save_does_not_consume_or_stamp(self):
		self.doc.docstatus = 0
		self.validate()
		self.assertEqual(self.db.writes, [])
		self.assertEqual(self.db.locks, [])
		self.stamp.assert_not_called()

	def test_approved_price_allows_later_orders_without_resetting_claim(self):
		self.submit()
		self.doc.name = "SO-2"
		self.rows.append(price(name="approved", approval_status="Approved"))
		self.submit()
		self.assertEqual(self.db.stored["A"], "SO-1")
		self.assertEqual(self.stamp.call_args.args[3]["name"], "approved")

	def test_no_price_is_not_an_allowance(self):
		self.rows = []
		with self.assertRaisesRegex(ValueError, "No eligible CPS price"):
			self.submit()
		self.assertEqual(self.db.writes, [])

	def test_price_revision_and_cancelled_first_order_do_not_reset_claim(self):
		self.db.stored["A"] = "SO-cancelled"
		self.rows = [price(name="replacement-draft")]
		with self.assertRaisesRegex(ValueError, "already used by SO-cancelled"):
			self.submit()

	def test_validate_failure_does_not_claim_any_cps(self):
		self.check.side_effect = ValueError("invalid UOM or unexplained variance")
		with self.assertRaises(ValueError):
			self.submit()
		self.assertEqual(self.db.writes, [])

	def test_stale_spec_snapshot_refuses_submit(self):
		self.spec.modified = "2026-11-10 09:00:00"
		with self.assertRaisesRegex(ValueError, "Reload and try again"):
			self.submit()
		self.assertEqual(self.db.writes, [])

	def test_before_migrate_draft_allowance_is_disabled(self):
		self.ledger_ready = False
		with self.assertRaisesRegex(ValueError, "No eligible CPS price"):
			self.submit()
		self.assertEqual(self.db.writes, [])

	def test_off_mode_does_not_change_existing_behaviour(self):
		self.mode = cps_rules.QUOTE_MODE_OFF
		self.submit()
		self.assertEqual(self.db.writes, [])
		self.assertEqual(self.db.locks, [])

	def test_draft_snapshot_records_the_exception_without_approving_price(self):
		path = Path(__file__).with_name("so_spec_control.py")
		function = next(node for node in ast.parse(path.read_text(encoding="utf-8")).body
		                if isinstance(node, ast.FunctionDef) and node.name == "_stamp_snapshot")
		self.scope.update(json=json, cps_price_rules=cps_price_rules,
		                  _price_check=lambda *args: cps_price_rules.check_line_rate(3793.1034, 1, "KES", self.rows[0]))
		self.scope["frappe"].utils.now = lambda: "2026-11-10 10:00:00"
		self.scope["frappe"].session = SimpleNamespace(user="rep@example.test")
		self.spec.specification_name = "Invoice paper"
		self.spec.product_type = "Computer Paper"
		exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), self.scope)
		line = self.doc["items"][0]
		self.scope["_stamp_snapshot"](self.doc, line, self.spec, self.rows[0], (1, 1))
		snapshot = json.loads(line.custom_spec_snapshot)
		self.assertEqual(snapshot["_draft_price_first_order"], {"sales_order": "SO-1", "price_row": "price-draft"})
		self.assertEqual(line.custom_cps_rate, 3793.1034)
		self.assertEqual(self.rows[0]["approval_status"], "Draft")
		self.assertNotIn("memo", line.custom_spec_snapshot.lower())


if __name__ == "__main__":
	unittest.main()
