"""post_backfill_packing with a stand-in frappe: who may post, the closing date, and all-or-nothing."""
import datetime
import importlib
import json
import sys
import types
import unittest
from unittest import mock


class Refused(Exception):
	pass


def fake_frappe(roles, fail_on=None):
	f = types.ModuleType("frappe")
	f.conf = {}
	f.session = types.SimpleNamespace(user="tanuj@vimit.com")
	f.PermissionError = Refused
	f.written, f.rolled = [], []
	f.get_roles = lambda: roles
	def throw(msg, exc=Refused):
		raise exc(msg)
	f.throw = throw
	f.whitelist = lambda **k: (lambda fn: fn)
	f.db = types.SimpleNamespace(rollback=lambda: f.rolled.append(1), get_value=lambda *a, **k: 0, exists=lambda *a: True)
	f.get_meta = lambda dt: types.SimpleNamespace(has_field=lambda n: False)
	def new_doc(dt):
		d = types.SimpleNamespace(items=[], meta=types.SimpleNamespace(has_field=lambda n: False), name=f"STE-{len(f.written) + 1}")
		d.append = lambda t, line: d.items.append(line)
		d.set = lambda k, v: None
		d.insert = lambda: None
		def submit():
			if fail_on == len(f.written) + 1:
				raise RuntimeError("stock error")
			f.written.append(d)
		d.submit = submit
		return d
	f.new_doc = new_doc
	u = types.ModuleType("frappe.utils")
	u.cint = lambda v: int(v or 0)
	u.format_datetime = lambda *a: "05-11-2026 21:00"
	u.getdate = lambda v: datetime.date.fromisoformat(v)
	u.now_datetime = datetime.datetime.now
	u.nowdate = lambda: "2026-11-05"
	u.nowtime = lambda: "21:00:00"
	u.time_diff_in_seconds = lambda a, b: 0
	f.utils = u
	return f, u


class TestBackfillEndpoint(unittest.TestCase):
	PAYLOAD = {"confirmed": 2, "group": "Swara|A4|120|SL", "run": "Miller", "date": "2026-11-05", "shift": "Day Shift", "inputs": {"cartons": 2}}

	def load(self, roles, fail_on=None, today="2026-11-05"):
		f, u = fake_frappe(roles, fail_on)
		u.nowdate = lambda: today
		patch = mock.patch.dict(sys.modules, {"frappe": f, "frappe.utils": u})
		patch.start()
		self.addCleanup(patch.stop)
		sys.modules.pop("production_log.production_floor.eb_capture", None)
		m = importlib.import_module("production_log.production_floor.eb_capture")
		m._machines = lambda: {}
		m._group_context = lambda group, book=None: (None, m.rules.codes(group), 2, 102, True, {"cov": 1000, "fld": 0, "ins": 10, "fg": 0, "carton": 50})
		self.addCleanup(lambda: sys.modules.pop("production_log.production_floor.eb_capture", None))
		return m, f

	def test_writes_inserts_then_packing(self):
		m, f = self.load(["System Manager"])
		out = m.post_backfill_packing(json.dumps(self.PAYLOAD))
		self.assertEqual(out["need"], 92)  # 204 books = 102 inserts, 10 on hand
		self.assertEqual([d.stock_entry_type for d in f.written], ["Repack", "Manufacture"])
		self.assertIn("BACK-POSTED FROM PACKING by tanuj@vimit.com", f.written[0].remarks)
		self.assertIn("FOLD CHECK HELD OFF", f.written[0].remarks)
		self.assertIn("back-posted inserts (STE-1)", f.written[1].remarks)

	def test_stock_manager_is_refused(self):
		m, f = self.load(["Stock Manager", "Manufacturing Manager"])
		with self.assertRaisesRegex(Refused, "System Manager"):
			m.post_backfill_packing(self.PAYLOAD)
		self.assertEqual(f.written, [])

	def test_closed_after_the_date(self):
		m, f = self.load(["System Manager"], today="2026-11-27")
		with self.assertRaisesRegex(Refused, "closed on 26/11/2026"):
			m.post_backfill_packing(self.PAYLOAD)
		self.assertEqual(f.written, [])

	def test_needs_both_confirmations(self):
		m, f = self.load(["System Manager"])
		with self.assertRaisesRegex(Refused, "confirmed twice"):
			m.post_backfill_packing(dict(self.PAYLOAD, confirmed=1))

	def test_second_entry_failing_rolls_both_back(self):
		m, f = self.load(["System Manager"], fail_on=2)
		with self.assertRaises(RuntimeError):
			m.post_backfill_packing(self.PAYLOAD)
		self.assertEqual(f.rolled, [1])

	def test_mode_tells_the_page(self):
		m, f = self.load(["System Manager"])
		mode = m.get_mode()
		self.assertTrue(mode["can_backfill"])
		self.assertEqual(mode["backfill_until"], "2026-11-26")
		m, f = self.load(["Stock User"])
		self.assertFalse(m.get_mode()["can_backfill"])

	def test_ordinary_entry_still_writes_one(self):
		m, f = self.load(["Stock User"])
		out = m.post_entry(dict(self.PAYLOAD, station="covers", inputs={"good": 5}))
		self.assertEqual(out["type"], "Material Receipt")
		self.assertEqual(len(f.written), 1)
