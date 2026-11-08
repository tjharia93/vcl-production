"""Offline browser checks for the actual deployed V3 assets. Every API call is intercepted.

Run with a Python environment containing Playwright:
    python scripts/test_eb_stock_recon.py
No ERPNext records are read or written by this test.
"""
import json
import pathlib
import unittest
import urllib.parse

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "exercise-book-production" / "dev-page-v3"
COVER = "COV-SWR-A4-120PG-SL"
FOLD = "FLD-SWR-A4-120PG-SL"
INSERT = "INS-SWR-A4-120PG-SL"
BOOK = "SWREB-A4-120PGS-CB-NP-SL"
OTHER_BOOK = "SWREB-A4-120PGS-MGC-NP-SL"
STORES, FG = "Stores - VCL", "Finished Goods - VCL"


class StockReconBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 1000})
        self.page = self.context.new_page()
        self.errors, self.posts = [], []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.fail_comment = self.fail_insert = self.drop_insert = self.bad_response = False
        self.fail_submit = self.drop_submit = False
        self.draft = None
        groups = ["Exercise Books", "Exercise Book Covers", "Exercise Book Inserts", "Folds", "Swara Exercise Books"]
        self.groups = [{"name": n, "parent_item_group": "Exercise Books" if n != "Exercise Books" else "All Item Groups"} for n in groups]
        def item(code, name, group, **extra):
            return dict(name=code, item_name=name, item_group=group, disabled=0, is_stock_item=1, stock_uom="Nos", has_serial_no=0, has_batch_no=0, **extra)
        self.items = [item(COVER, "Swara A4 120PG Single Line - 2 up", "Exercise Book Covers"),
                      item(FOLD, "Swara A4 120PG Fold - 2 up", "Folds"),
                      item(INSERT, "Swara A4 120PG Insert - 2 up", "Exercise Book Inserts"),
                      item(BOOK, "Swara A4 120PG CB Single Line", "Swara Exercise Books", cf=100),
                      item(OTHER_BOOK, "Swara A4 120PG MG Single Line", "Swara Exercise Books", cf=100)]
        self.bins = [dict(name=f"BIN-{i}", item_code=code, warehouse=wh, actual_qty=qty, valuation_rate=rate, modified="2026-11-07 10:00:00")
                     for i, (code, wh, qty, rate) in enumerate([(COVER, STORES, 120, 2), (FOLD, STORES, 30, 0), (INSERT, STORES, 70, 3), (BOOK, FG, 123, 5), (OTHER_BOOK, FG, 90, 6)])]
        self.page.route("**/*", self.route)

    def tearDown(self):
        self.assertEqual(self.errors, [])
        self.context.close()

    @staticmethod
    def matches(row, filters):
        for condition in filters:
            if len(condition) == 4:  # Child join: only UOM Carton is used here.
                if condition[0] == "UOM Conversion Detail" and not row.get("cf"):
                    return False
                continue
            key, op, value = condition
            actual = row.get(key)
            if op == "=" and actual != value: return False
            if op == "in" and actual not in value: return False
            if op == "like" and not str(actual).startswith(value.rstrip("%")): return False
        return True

    def route(self, route):
        req = route.request
        url = urllib.parse.urlsplit(req.url)
        if url.path == "/":
            body = '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' + (ASSETS / "index.html").read_text() + "<style>" + (ASSETS / "page.css").read_text() + "</style>"
            body += '<script>window.frappe={session:{user:"test@vimit.com"},csrf_token:"test",ready:f=>f()};</script><script>' + (ASSETS / "page.js").read_text() + "</script>"
            route.fulfill(body=body, content_type="text/html")
            return
        if "/api/method/" not in url.path:
            route.fulfill(body="", status=200)
            return
        method = url.path.split("/api/method/")[1]
        args = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        if method == "frappe.client.get_list" and req.method == "POST":
            args = req.post_data_json
            args["filters"] = json.dumps(args["filters"])
        if req.method == "POST" and method != "frappe.client.get_list":
            data = req.post_data_json
            self.posts.append((method, data))
            if method not in ("frappe.client.insert", "frappe.client.submit"):
                self.fail(f"Unexpected write method: {method}")
            doc = data["doc"]
            if method == "frappe.client.submit":
                self.assertEqual(doc["name"], self.draft["name"])
                self.assertEqual(doc["docstatus"], 0)
                if self.fail_submit:
                    route.fulfill(status=403, json={"exception": "Submit permission denied"}); return
                self.draft["docstatus"] = 1
                for row in self.draft["items"]:
                    for b in self.bins:
                        if b["item_code"] == row["item_code"] and b["warehouse"] == row["warehouse"]:
                            b["actual_qty"] = row["qty"]
                            b["modified"] = "2026-11-07 12:00:00"
                if self.drop_submit:
                    route.abort("failed"); return
                result = self.draft
            elif doc["doctype"] == "Stock Reconciliation":
                if self.drop_insert:
                    route.abort("failed"); return
                if self.bad_response:
                    route.fulfill(body="Upstream response unavailable", content_type="text/html"); return
                if self.fail_insert:
                    route.fulfill(status=403, json={"exception": "Permission denied"}); return
                result = dict(json.loads(json.dumps(doc)), name="MAT-RECO-TEST-001", docstatus=0,
                              posting_date="2026-11-07", posting_time="11:00:00", expense_account="Stock Adjustment - VCL", cost_center="Main - VCL", difference_amount=0)
                for row in result["items"]:
                    b = next((b for b in self.bins if b["item_code"] == row["item_code"] and b["warehouse"] == row["warehouse"]), {})
                    row["current_qty"] = b.get("actual_qty", 0)
                    row["valuation_rate"] = b.get("valuation_rate", 0)
                    result["difference_amount"] += (row["qty"] - row["current_qty"]) * row["valuation_rate"]
                self.draft = result
            elif doc["doctype"] == "Comment":
                if self.fail_comment:
                    route.fulfill(status=403, json={"exception": "Comment refused"}); return
                result = dict(doc, name="COMMENT-TEST")
            else:
                self.fail(f"Unexpected doctype write: {doc['doctype']}")
        elif method.endswith("get_mode"):
            result = dict(can_post=True, user="test@vimit.com", shifts=["Day Shift", "Night Shift"])
        elif method == "frappe.client.get_list":
            doctype = args["doctype"]
            data = {"Item Group": self.groups, "Item": self.items, "Bin": self.bins}.get(doctype, [])
            filters = json.loads(args.get("filters", "[]"))
            result = [x for x in data if self.matches(x, filters)]
            start, limit = int(args.get("limit_start", 0)), int(args.get("limit_page_length", 0))
            result = result[start:start + limit] if limit else result[start:]
        elif method == "frappe.client.get" and args["doctype"] == "Stock Reconciliation":
            result = self.draft
        else:
            self.fail(f"Unexpected read method: {method}")
        route.fulfill(json={"message": result})

    def open(self):
        self.page.goto("https://recon.test/?view=recon")
        self.page.locator("#rc-brands").wait_for()
        self.assertEqual(self.page.locator("#v3-title").inner_text(), "Stock recon")
        self.assertEqual(self.page.locator("[data-rc]").count(), 0)
        self.page.locator('[data-rc-brand="Swara"]').click()

    def row(self, code):
        return self.page.locator(".rc tbody tr").filter(has=self.page.locator("code", has_text=code))

    def enter(self, code, qty):
        self.row(code).locator('input[data-field="qty"]').fill(qty)

    def review(self):
        self.page.locator("#rc-reason").fill("Physical floor count by Peter")
        self.page.locator("#rc-create").click()

    def accept(self):
        self.page.locator('.dlg button[data-a="yes"]').click()
        self.page.wait_for_function("document.querySelector('#rc-result').innerText.includes('Draft created')")
        self.page.wait_for_function("!document.querySelector('#rc-reset').disabled")

    def test_blank_zero_invalid_and_absolute_qty(self):
        self.open()
        self.assertTrue(self.page.locator("#rc-create").is_disabled())
        self.enter(COVER, "-2")
        self.assertIn("Whole numbers", self.row(COVER).inner_text())
        self.assertTrue(self.page.locator("#rc-create").is_disabled())
        self.enter(COVER, "1.5")
        self.assertTrue(self.page.locator("#rc-create").is_disabled())
        self.enter(COVER, "0")
        self.review()
        self.assertEqual(self.posts, [])  # Review does not create anything.
        self.accept()
        doc = self.posts[0][1]["doc"]
        self.assertEqual(doc["items"], [{"item_code": COVER, "warehouse": STORES, "qty": 0, "stock_uom": "Nos", "valuation_rate": None}])
        self.assertNotIn("allow_zero_valuation_rate", doc["items"][0])
        self.assertEqual(self.posts[1][1]["doc"]["reference_name"], "MAT-RECO-TEST-001")
        self.assertEqual(self.page.locator("#rc-create").count(), 0)
        self.assertFalse(self.page.locator("#rc-submit").is_disabled())

    def test_cartons_exact_variant_and_counts_survive_filters(self):
        self.open()
        self.enter(COVER, "110")
        self.page.locator("#rc-stage").select_option("fg")
        self.enter(BOOK, "2")
        self.row(BOOK).locator('[data-field="loose"]').fill("3")
        self.assertIn("+80 books", self.row(BOOK).inner_text())
        self.assertIn("Not counted", self.row(OTHER_BOOK).inner_text())
        self.review()
        self.assertIn("2 items", self.page.locator(".dlg h3").inner_text())
        self.accept()
        rows = self.posts[0][1]["doc"]["items"]
        self.assertEqual({r["item_code"]: r["qty"] for r in rows}, {COVER: 110, BOOK: 203})
        self.assertEqual({r["warehouse"] for r in rows}, {STORES, FG})

    def test_movement_requires_another_review_and_back_does_not_write(self):
        self.open()
        self.enter(COVER, "100")
        self.bins[0]["actual_qty"] = 119
        self.bins[0]["modified"] = "2026-11-07 10:10:00"
        self.review()
        self.page.wait_for_function("document.querySelector('#rc-result').innerText.includes('ERP stock changed')")
        self.assertEqual(self.page.locator(".dlg").count(), 0)
        self.assertIn("-19 sheets", self.row(COVER).inner_text())
        self.review()
        self.page.locator('.dlg [data-a="back"]').click()
        self.assertEqual(self.posts, [])
        self.assertFalse(self.page.locator("#rc-create").is_disabled())

    def test_zero_valuation_requires_opt_in_and_comment_failure_keeps_draft(self):
        self.fail_comment = True
        self.open()
        self.page.locator("#rc-stage").select_option("folds")
        self.enter(FOLD, "35")
        self.page.locator("#rc-zero").check()
        self.review()
        self.assertIn("zero value", self.page.locator(".dlg").inner_text())
        self.accept()
        self.page.wait_for_function("document.querySelector('#rc-result').innerText.includes('count note could not be saved')")
        self.assertEqual(self.posts[0][1]["doc"]["items"][0]["allow_zero_valuation_rate"], 1)
        self.assertTrue(self.page.locator("#rc-submit").is_disabled())
        self.assertTrue(self.page.locator("#rc-note").is_visible())

    def test_lost_response_blocks_duplicate_retry(self):
        self.drop_insert = True
        self.open()
        self.enter(COVER, "100")
        self.review()
        self.page.locator('.dlg [data-a="yes"]').click()
        self.page.wait_for_function("document.querySelector('#rc-result').innerText.includes('response was lost')")
        self.assertTrue(self.page.locator("#rc-create").is_disabled())
        self.assertTrue(self.page.locator("#rc-reset").is_disabled())
        self.assertEqual(len(self.posts), 1)

    def test_permission_refusal_is_shown(self):
        self.fail_insert = True
        self.open()
        self.enter(COVER, "100")
        self.review()
        self.page.locator('.dlg [data-a="yes"]').click()
        self.page.wait_for_function("document.querySelector('#rc-result').innerText.includes('Permission denied')")
        self.assertFalse(self.page.locator("#rc-create").is_disabled())

    def test_cleared_count_is_blank_and_matching_counts_are_omitted(self):
        self.open()
        self.enter(COVER, "0")
        self.enter(COVER, "")
        self.assertIn("Not counted", self.row(COVER).inner_text())
        self.enter(COVER, "120")
        self.assertTrue(self.page.locator("#rc-create").is_disabled())
        self.page.locator("#rc-stage").select_option("inserts")
        self.enter(INSERT, "60")
        self.review()
        self.accept()
        self.assertEqual([r["item_code"] for r in self.posts[0][1]["doc"]["items"]], [INSERT])

    def test_malformed_success_response_blocks_duplicate_retry(self):
        self.bad_response = True
        self.open()
        self.enter(COVER, "100")
        self.review()
        self.page.locator('.dlg [data-a="yes"]').click()
        self.page.wait_for_function("document.querySelector('#rc-result').innerText.includes('response was lost')")
        self.assertTrue(self.page.locator("#rc-create").is_disabled())

    def test_catalog_paginates_beyond_500_items(self):
        for i in range(501):
            self.items.append(dict(self.items[0], name=f"COV-SWR-A5-{i:03}PG-SL", item_name=f"Swara A5 {i} pages - 3 up"))
        self.open()
        self.page.locator("#rc-q").fill("COV-SWR-A5-500PG-SL")
        self.assertEqual(self.page.locator(".rc tbody tr").count(), 1)
        self.assertIn("COV-SWR-A5-500PG-SL", self.page.locator(".rc tbody").inner_text())

    def test_phone_layout_and_navigation(self):
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.open()
        self.enter(COVER, "100")
        self.assertEqual(self.page.evaluate("document.documentElement.scrollWidth > innerWidth"), False)
        self.assertGreaterEqual(self.row(COVER).locator("input").bounding_box()["height"], 44)
        self.page.screenshot(path="/tmp/eb-stock-recon-phone.png", full_page=True)
        self.page.locator('#v3-mode [data-view="capture"]').click()
        self.page.locator('#v3-mode [data-view="recon"]').click()
        self.assertEqual(self.row(COVER).locator("input").input_value(), "100")

    def prepare_draft(self):
        self.open()
        self.enter(COVER, "100")
        self.review()
        self.accept()

    def submit_confirmations(self):
        self.page.locator("#rc-submit").click()
        self.page.locator('.dlg [data-a="yes"]').click()
        self.assertIn("Step 2 of 2", self.page.locator(".dlg h3").inner_text())
        self.page.locator('.dlg [data-a="yes"]').click()

    def test_submits_on_screen_only_after_both_confirmations(self):
        self.prepare_draft()
        self.page.locator("#rc-submit").click()
        self.assertIn("Stock Adjustment - VCL", self.page.locator(".dlg").inner_text())
        self.assertIn("-40.00", self.page.locator(".dlg").inner_text())
        self.assertFalse(any(m == "frappe.client.submit" for m, _ in self.posts))
        self.page.locator('.dlg [data-a="yes"]').click()
        self.assertFalse(any(m == "frappe.client.submit" for m, _ in self.posts))
        self.page.locator('.dlg [data-a="yes"]').click()
        self.page.wait_for_function("document.querySelector('#rc-result').innerText.includes('Stock true-up applied')")
        self.assertEqual(sum(m == "frappe.client.submit" for m, _ in self.posts), 1)
        self.assertEqual(self.page.locator("#rc-submit").count(), 0)
        self.assertEqual(self.bins[0]["actual_qty"], 100)

    def test_second_submission_confirmation_can_be_cancelled(self):
        self.prepare_draft()
        self.page.locator("#rc-submit").click()
        self.page.locator('.dlg [data-a="yes"]').click()
        self.page.locator('.dlg [data-a="back"]').click()
        self.assertFalse(any(m == "frappe.client.submit" for m, _ in self.posts))
        self.assertFalse(self.page.locator("#rc-submit").is_disabled())

    def test_submit_permission_refusal_preserves_draft(self):
        self.fail_submit = True
        self.prepare_draft()
        self.submit_confirmations()
        self.page.wait_for_function("document.querySelector('#rc-result').innerText.includes('Submit permission denied')")
        self.assertEqual(self.draft["docstatus"], 0)
        self.assertFalse(self.page.locator("#rc-submit").is_disabled())

    def test_stock_movement_after_draft_blocks_submission(self):
        self.prepare_draft()
        self.bins[0]["actual_qty"] = 119
        self.page.locator("#rc-submit").click()
        self.page.wait_for_function("document.querySelector('#rc-result').innerText.includes('ERP stock moved')")
        self.assertFalse(any(m == "frappe.client.submit" for m, _ in self.posts))

    def test_changed_draft_quantities_block_submission(self):
        self.prepare_draft()
        self.draft["items"][0]["qty"] = 999
        self.page.locator("#rc-submit").click()
        self.page.wait_for_function("document.querySelector('#rc-result').innerText.includes('reconciliation changed')")
        self.assertFalse(any(m == "frappe.client.submit" for m, _ in self.posts))

    def test_lost_submit_response_is_checked_without_resubmitting(self):
        self.drop_submit = True
        self.prepare_draft()
        self.submit_confirmations()
        self.page.wait_for_function("document.querySelector('#rc-result').innerText.includes('Submission response was lost')")
        self.assertTrue(self.page.locator("#rc-submit").is_disabled())
        self.page.locator("#rc-check").click()
        self.page.wait_for_function("document.querySelector('#rc-result').innerText.includes('Stock true-up applied')")
        self.assertEqual(sum(m == "frappe.client.submit" for m, _ in self.posts), 1)

    def test_failed_count_note_can_be_saved_without_desk(self):
        self.fail_comment = True
        self.prepare_draft()
        self.assertTrue(self.page.locator("#rc-submit").is_disabled())
        self.fail_comment = False
        self.page.locator("#rc-note").click()
        self.page.wait_for_function("document.querySelector('#rc-submit') && !document.querySelector('#rc-submit').disabled")
        self.submit_confirmations()
        self.page.wait_for_function("document.querySelector('#rc-result').innerText.includes('Stock true-up applied')")

    def test_brand_buttons_use_existing_colours_and_keep_counts(self):
        self.items.append(dict(self.items[0], name="COV-PNC-A4-120PG-SL", item_name="Prince A4 120PG - 2 up"))
        self.open()
        swara = self.page.locator('[data-rc-brand="Swara"]')
        prince = self.page.locator('[data-rc-brand="Prince"]')
        self.assertEqual(swara.get_attribute("aria-pressed"), "true")
        self.assertEqual(swara.evaluate("b=>getComputedStyle(b).backgroundColor"), "rgb(227, 218, 246)")
        self.assertEqual(prince.evaluate("b=>getComputedStyle(b).backgroundColor"), "rgb(211, 235, 220)")
        self.enter(COVER, "100")
        prince.click()
        self.assertEqual(prince.get_attribute("aria-pressed"), "true")
        self.assertEqual(self.page.locator(".rc tbody tr").count(), 1)
        swara.click()
        self.assertEqual(self.row(COVER).locator("input").input_value(), "100")


if __name__ == "__main__":
    unittest.main(verbosity=2)
