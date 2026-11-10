"""Approval/notification boundary tests; normal Frappe transactions need a bench."""

import ast
import hashlib
import html
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode
import unittest
from unittest.mock import Mock

from production_log.job_card_tracking import cps_approval_rules, cps_lifecycle_rules, cps_rules

try:
	import jinja2
except ImportError:
	jinja2 = None


class TestApprovalTemplate(unittest.TestCase):
	@unittest.skipIf(jinja2 is None, "Jinja2 is supplied by Frappe; install it for the standalone template check")
	def test_real_jinja_template_renders_css_and_approval_controls(self):
		path = Path(__file__).parents[1] / "www/cps_first_order_approval.html"
		source = path.read_text(encoding="utf-8")
		env = jinja2.Environment(loader=jinja2.DictLoader({
			"approval.html": source,
			"templates/web.html": '<html><meta charset="utf-8">{% block page_content %}{% endblock %}</html>',
		}))
		rendered = env.get_template("approval.html").render()
		self.assertIn("@media(max-width:600px){#cps-first-review", rendered)
		self.assertIn("Approve CPS + price", rendered)
		self.assertNotIn("{% raw %}", rendered)


class Doc(dict):
	__getattr__ = dict.get
	__setattr__ = dict.__setitem__

	def as_dict(self):
		return {k: v for k, v in self.items() if k not in ("meta", "steps")}

	def check_permission(self, permission):
		self.steps.append("permission:" + permission)

	def save(self):
		self.steps.append("save")

	def submit(self):
		self.steps.append("submit")
		self.docstatus = 1


def scope():
	def whitelist(methods):
		def decorator(fn):
			fn.methods = methods
			return fn
		return decorator

	def refusing(message, *args):
		raise ValueError(message)

	frappe = SimpleNamespace(whitelist=whitelist, throw=refusing, PermissionError=ValueError,
	                         session=SimpleNamespace(user="manager@example.test"),
	                         get_roles=lambda user=None: ["VCL Management Team"],
	                         utils=SimpleNamespace(get_url=lambda path: "https://example.test" + path),
	                         db=SimpleNamespace(exists=Mock(return_value=False)),
	                         sendmail=Mock(), log_error=Mock(), get_traceback=lambda: "test failure", msgprint=Mock())
	s = dict(frappe=frappe, _=lambda text: text, CPS="Customer Product Specification",
	         PACKING_ROLES={"VCL Management Team", "System Manager"},
	         cps_approval_rules=cps_approval_rules, cps_lifecycle_rules=cps_lifecycle_rules,
	         cps_rules=cps_rules, cps_first_order_price=SimpleNamespace(CLAIM_FIELD="first_submitted_sales_order"),
	         hashlib=hashlib, html=html, json=json, urlencode=urlencode)
	tree = ast.parse(Path(__file__).with_name("cps_first_order_approval.py").read_text(encoding="utf-8"))
	functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
	exec(compile(ast.Module(body=functions, type_ignores=[]), "cps_first_order_approval.py", "exec"), s)
	return s


class TestCombinedApproval(unittest.TestCase):
	def setUp(self):
		self.s = scope()
		self.steps = []
		self.spec = Doc(name="CPS-1", specification_name="Invoice", docstatus=0, customer="Customer",
		                owner="rep@example.test", product_type="Computer Paper", steps=self.steps,
		                vcl_revision=1, vcl_approved_rev=0, vcl_approval_state="Awaiting approval")
		self.row = Doc(name="price-1", approval_status="Draft", rate=20, owner="rep@example.test")
		self.line = Doc(name="line1", rate=20)
		self.order = Doc(name="SO-1", docstatus=1)
		self.s["_load"] = Mock(return_value=(self.order, self.line, self.spec, self.row))
		self.s["_authority"] = Mock()
		self.tech = Mock(side_effect=lambda *a, **kw: self.steps.append("approve technical"))
		self.price = Mock(side_effect=lambda *a, **kw: self.steps.append("approve price"))
		self.s["cps_approval"] = SimpleNamespace(approve_technical=self.tech)
		self.s["cps_pricing"] = SimpleNamespace(approve_cps_price=self.price)

	def version(self):
		return self.s["_version"](self.order, self.line, self.spec)

	def approve(self, **args):
		return self.s["approve"]("SO-1", "CPS-1", self.version(), **args)

	def test_get_is_review_only_and_approval_is_post_only(self):
		self.assertEqual(self.s["review"].methods, ["GET"])
		self.assertEqual(self.s["approve"].methods, ["POST"])

	def test_one_action_submits_and_approves_spec_then_price(self):
		result = self.approve()
		self.assertTrue(result["approved"])
		self.assertEqual(self.steps, ["submit", "approve technical", "approve price"])
		self.s["_load"].assert_called_once_with("SO-1", "CPS-1", lock=True)

	def test_stale_review_cannot_approve_anything(self):
		version = self.version()
		self.row.rate = 30
		self.spec.pricing = [self.row]
		with self.assertRaisesRegex(ValueError, "Reload and review"):
			self.s["approve"]("SO-1", "CPS-1", version)
		self.assertEqual(self.steps, [])

	def test_both_authorities_checked_before_submit_or_approval(self):
		self.s["_authority"].side_effect = ValueError("No price approval authority")
		with self.assertRaises(ValueError):
			self.approve()
		self.assertEqual(self.steps, [])

	def test_normal_submit_failure_prevents_both_approvals(self):
		class BadSpec(Doc):
			def submit(self):
				raise ValueError("Incomplete construction")
		self.spec = BadSpec(self.spec)
		self.s["_load"].return_value = (self.order, self.line, self.spec, self.row)
		with self.assertRaisesRegex(ValueError, "Incomplete construction"):
			self.approve()
		self.tech.assert_not_called()
		self.price.assert_not_called()

	def test_already_approved_documents_do_not_reapprove(self):
		self.spec.docstatus = 1
		self.spec.vcl_approved_rev = 1
		self.spec.vcl_approval_state = "Approved"
		self.row.approval_status = "Approved"
		self.approve()
		self.assertEqual(self.steps, [])

	def test_management_may_enter_first_run_packing(self):
		self.approve(sets_per_carton="500", carton_tare="0.3")
		self.assertEqual(self.spec.sets_per_carton, 500)
		self.assertEqual(self.spec.packing_carton_tare_kg, 0.3)
		self.assertEqual(self.steps[0], "save")

	def test_packing_is_optional_and_not_invented(self):
		self.approve()
		self.assertIsNone(self.spec.sets_per_carton)
		self.assertIsNone(self.spec.packing_carton_tare_kg)

	def test_rep_cannot_write_packing_through_approval(self):
		self.s["frappe"].get_roles = lambda: ["Sales Manager"]
		with self.assertRaisesRegex(ValueError, "Only management"):
			self.approve(sets_per_carton="500")
		self.assertEqual(self.steps, [])

	def test_non_finite_and_fractional_packing_refused(self):
		for args in ({"sets_per_carton": "nan"}, {"sets_per_carton": "0"},
		             {"sets_per_carton": "1.5"}, {"carton_tare": "inf"}):
			with self.assertRaises(ValueError):
				self.approve(**args)
		self.assertEqual(self.steps, [])


class TestApprovalBinding(unittest.TestCase):
	def setUp(self):
		self.s = scope()
		self.line = Doc(custom_cps="CPS-1", custom_cps_price_row="price-1",
		                custom_spec_snapshot=json.dumps({"_first_order_exception": {"sales_order": "SO-1", "price_row": "price-1"}}))
		self.order = Doc(name="SO-1", docstatus=1, items=[self.line])

	def test_email_only_binds_the_order_cps_and_exact_price_row(self):
		self.assertIs(self.s["_pending_line"](self.order, "CPS-1"), self.line)
		for changes in ({"custom_cps": "CPS-other"}, {"custom_cps_price_row": "price-other"},
		                {"custom_spec_snapshot": "{}"}):
			original = Doc(self.line)
			self.line.update(changes)
			with self.assertRaisesRegex(ValueError, "not bound"):
				self.s["_pending_line"](self.order, "CPS-1")
			self.line.clear(); self.line.update(original)

	def test_normal_orders_are_not_pending_requests(self):
		self.line.custom_spec_snapshot = "{}"
		self.assertIsNone(self.s["_pending_line"](self.order, "CPS-1", required=False))

	def test_draft_order_never_queues_an_approval_email(self):
		self.order.docstatus = 0
		self.s["request_for_order"](self.order)
		self.s["frappe"].sendmail.assert_not_called()

	def test_email_queues_only_after_submit_without_immediate_smtp(self):
		row = Doc(name="price-1", rate=20, uom="Carton", currency="KES")
		spec = Doc(name="CPS-1", specification_name="Invoice <script>", customer="Customer", pricing=[row])
		self.s["frappe"].get_doc = lambda *args: spec
		self.s["_recipients"] = Mock(return_value=["manager@example.test"])
		self.s["request_for_order"](self.order)
		call = self.s["frappe"].sendmail.call_args.kwargs
		self.assertFalse(call["now"])
		self.assertEqual(call["reference_name"], "SO-1")
		self.assertIn("/sales-crm-v2/approve-cps?", call["message"])
		self.assertNotIn("<script>", call["message"])
		self.assertIn("Opening this link does not approve", call["message"])

	def test_duplicate_notifications_are_not_queued(self):
		row = Doc(name="price-1")
		self.s["frappe"].get_doc = lambda *args: Doc(pricing=[row], specification_name="Invoice")
		self.s["frappe"].db.exists.return_value = True
		self.s["request_for_order"](self.order)
		self.s["frappe"].sendmail.assert_not_called()

	def test_missing_recipient_is_reported_without_auto_approval(self):
		row = Doc(name="price-1")
		self.s["frappe"].get_doc = lambda *args: Doc(pricing=[row], specification_name="Invoice")
		self.s["_recipients"] = Mock(return_value=[])
		self.s["request_for_order"](self.order)
		self.s["frappe"].sendmail.assert_not_called()
		self.s["frappe"].msgprint.assert_called_once()


class TestApprovalAccess(unittest.TestCase):
	def setUp(self):
		self.s = scope()
		self.line = Doc(name="line1", item_code="ITEM", custom_cps="CPS-1", custom_cps_price_row="price-1",
		                custom_spec_snapshot=json.dumps({"_first_order_exception": {"sales_order": "SO-1", "price_row": "price-1"}}))
		self.order = Doc(name="SO-1", docstatus=1, customer="Customer", items=[self.line], steps=[])
		self.row = Doc(name="price-1", approval_status="Draft", owner="rep@example.test")
		self.spec = Doc(name="CPS-1", owner="rep@example.test", docstatus=0, status="Active", steps=[],
		                customer="Customer", linked_item="ITEM", first_submitted_sales_order="SO-1", pricing=[self.row])
		self.s["frappe"].get_doc = lambda dt, name: self.order if dt == "Sales Order" else self.spec

	def test_guest_cannot_load_approval_data(self):
		self.s["frappe"].session.user = "Guest"
		with self.assertRaisesRegex(ValueError, "Sign in"):
			self.s["_load"]("SO-1", "CPS-1")
		self.assertEqual(self.spec.steps, [])

	def test_order_and_cps_must_still_match(self):
		self.s["_load"]("SO-1", "CPS-1")
		for changes in ({"customer": "Other"}, {"linked_item": "OTHER"},
		                {"status": "Inactive"}, {"docstatus": 2},
		                {"first_submitted_sales_order": "SO-other"}):
			before = dict(self.spec)
			self.spec.update(changes)
			with self.assertRaisesRegex(ValueError, "no longer matches"):
				self.s["_load"]("SO-1", "CPS-1")
			self.spec.clear(); self.spec.update(before)

	def test_cancelled_order_and_rejected_price_cannot_be_approved(self):
		self.order.docstatus = 2
		with self.assertRaisesRegex(ValueError, "still be submitted"):
			self.s["_load"]("SO-1", "CPS-1")
		self.order.docstatus = 1
		self.row.approval_status = "Rejected"
		with self.assertRaisesRegex(ValueError, "missing or rejected"):
			self.s["_load"]("SO-1", "CPS-1")

	def test_routing_requires_authority_for_both_spec_and_price(self):
		decision = SimpleNamespace(approver_role=None, approver_user="tech@example.test",
		                           management_role="VCL Management Team", outcome=cps_approval_rules.OUTCOME_ROUTE,
		                           allow_self_approval=False)
		pricing = SimpleNamespace(**dict(vars(decision), approver_user="price@example.test"))
		self.s["cps_approval"] = SimpleNamespace(resolve_technical=lambda doc: decision,
		                                         resolve_price=lambda doc, row: pricing)
		users = ["manager@example.test", "tech@example.test", "price@example.test", "disabled@example.test", "blind@example.test"]
		self.s["frappe"].get_all = lambda *a, **kw: users
		self.s["frappe"].get_roles = lambda user: ["VCL Management Team"] if user in (users[0], users[3], users[4]) else []
		self.s["frappe"].db.get_value = lambda dt, user, field: user != "disabled@example.test" if field == "enabled" else user
		self.s["frappe"].has_permission = lambda *a, **kw: kw["user"] != "blind@example.test"
		self.assertEqual(self.s["_recipients"](self.spec, self.row), ["manager@example.test"])

	def test_review_does_not_leak_packing_or_password_fields(self):
		def field(name, level=0, kind="Data"):
			return SimpleNamespace(fieldname=name, permlevel=level, fieldtype=kind, label=name, hidden=0)
		self.spec.update(packing=500, public="Invoice", password="secret", admin_only="private")
		self.spec.meta = SimpleNamespace(fields=[field("public"), field("packing", 1), field("password", kind="Password"), field("admin_only", 2)])
		self.assertEqual([x["label"] for x in self.s["_fields"](self.spec)], ["public"])
		self.assertEqual([x["label"] for x in self.s["_fields"](self.spec, packing=True)], ["public", "packing"])


if __name__ == "__main__":
	unittest.main()
