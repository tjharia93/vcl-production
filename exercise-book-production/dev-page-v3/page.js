/* Exercise Book Production v3 (preview) — /exercise-book-production-v3-dev
 *
 * Floor capture for exercise books: Covers -> Folds -> Inserts -> Packing -> Finished Goods.
 * Decided by Tanuj on 04/11/2026; target UX = the click-through "Capture v3" tab.
 *
 * SAFETY (Tanuj, 04/11/2026: every post is confirmed TWICE, then posts for real)
 * - The preview card always shows exactly what an entry will do.
 * - Post -> step 1 "Is this correct?" (every row, warnings) -> step 2 "Post to ERPNext now?"
 *   (totals, "Post now" not pre-focused, Enter does nothing) -> eb_capture.post_entry with
 *   confirmed=2. Undo (same user, 10 minutes) is confirmed twice the same way.
 * - If the server methods are not deployed, Post says "Server update needed" and posts nothing.
 * - Reads only through frappe.client.get_list (GET). No REST resource writes.
 *
 * RULES (mirror of production_floor/eb_capture_rules.py; keep the two in step)
 * - Covers, folds, inserts count in SETS with the same up-count (A4 2-up, A5 3-up, from
 *   the item name). 1 cover sheet + 1 fold set = 1 insert set. Only packing counts books.
 * - Covers: Material Receipt COV-x -> Stores - VCL (spoiled recorded, not added).
 * - Folds: Material Receipt FLD-x -> Stores - VCL (rejects recorded; opening count offered).
 * - Inserts: Repack, no BOM. Out COV-x and FLD-x x sets, in INS-x x sets. Blocked when short,
 *   unless the fold check is held off (logged on the entry).
 * - Packing: Manufacture -> Finished Goods - VCL. Books = cartons x books/carton + loose.
 *   Out INS-x = ceil((books + rejects) / ups) sets + empty cartons. Leftover books = rejects.
 *   Spot-weigh 1 carton in 20, flag > 5% from the others.
 * Known bugs fixed versus v2: cover capacity is sheets x ups; inserts read from Repack;
 * Finished Goods - VCL only; no 9-up / 4-up options.
 */
(function () {
  "use strict";
  var STORES = "Stores - VCL", FG = "Finished Goods - VCL";
  var M = "production_log.production_floor.eb_capture.";
  // P12 is open for Tanuj: one common carton per size + brand (PC proposal). Change here and in eb_capture_rules.CARTONS.
  var CARTONS = {
    "A4|Prince": "PNC-EMPTY-CARTON-A4-EXBK-COMMON-425 x 305 x 260",
    "A4|Swara": "SWR- COMMON CARTON 280 MM",
    "A5|Prince": "PNCSWR-EMPTY-CARTON-A5-PLAINF-DPL",
    "A5|Swara": "PNCSWR-EMPTY-CARTON-A5-PLAINF-DPL"
  };
  var RUL = { SL: "Single line", SQ: "Square line", GPH: "Graph", PLN: "Plain", IRS: "Irish", MSC: "Music", HSL: "Half-inch single", HSQ: "Half-inch square", SQ13: "1/3 inch square", FNB: "Field note" };
  var STEPS = [["covers", "Station 1", "Covers"], ["folds", "Station 2", "Folds"], ["inserts", "Station 3", "Inserts"], ["packing", "Station 4", "Packing"], ["fg", "Result", "Finished Goods"]];
  var TYPE = { covers: "Material Receipt", folds: "Material Receipt", inserts: "Repack", packing: "Manufacture" };
  var LS = "vcl.eb-v3.";

  var D = null;          // loaded data
  var S = { view: "capture", group: null, book: null, run: "", station: "covers", log: [], v: {} };
  var MODE = { checked: false, server: false, can_post: false, user: "" };
  var NEED = "Server update needed: deploy vcl-production feat/eb-capture-v3 and migrate. Nothing was posted.";

  /* ---------- helpers ---------- */
  function $(id) { return document.getElementById(id); }
  function esc(x) { return String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;"); }
  function f(n) { return Math.round(Number(n) || 0).toLocaleString("en-GB"); }
  function pg3(p) { return ("00" + p).slice(-3); }
  function lsGet(k, d) { try { var v = localStorage.getItem(LS + k); return v == null ? d : v; } catch (e) { return d; } }
  function lsSet(k, v) { try { localStorage.setItem(LS + k, v); } catch (e) { /* private window */ } }
  function csrf() { return (window.frappe && frappe.csrf_token) || ""; }
  function get(method, args) {
    var q = Object.keys(args || {}).map(function (k) { var v = args[k]; return encodeURIComponent(k) + "=" + encodeURIComponent(typeof v === "string" ? v : JSON.stringify(v)); }).join("&");
    return fetch("/api/method/" + method + (q ? "?" + q : ""), { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) throw new Error(serverMsg(j) || ("HTTP " + r.status)); return j.message; }); });
  }
  function post(method, args) {
    return fetch("/api/method/" + method, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", Accept: "application/json", "X-Frappe-CSRF-Token": csrf() }, body: JSON.stringify(args || {}) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) throw new Error(serverMsg(j) || ("HTTP " + r.status)); return j.message; }); });
  }
  function serverMsg(j) {
    try { if (j._server_messages) return JSON.parse(j._server_messages).map(function (m) { try { return JSON.parse(m).message; } catch (e) { return m; } }).join(" ").replace(/<br>/g, " "); } catch (e) { /* ignore */ }
    return j.exception || j.message || "";
  }
  function list(doctype, fields, filters) { return get("frappe.client.get_list", { doctype: doctype, fields: fields, filters: filters, limit_page_length: 0 }); }

  /* ---------- load (read-only) ---------- */
  function load() {
    var setGroups = ["Exercise Book Covers", "Folds", "Exercise Book Inserts"];
    var cartonCodes = Object.keys(CARTONS).map(function (k) { return CARTONS[k]; }).filter(function (v, i, a) { return a.indexOf(v) === i; });
    var openSO = [["docstatus", "=", 1], ["status", "in", ["To Deliver and Bill", "To Deliver"]]];
    var soFields = ["name", "customer", "delivery_date", "status", "`tabSales Order Item`.item_code as item_code", "`tabSales Order Item`.qty as qty", "`tabSales Order Item`.delivered_qty as delivered_qty", "`tabSales Order Item`.conversion_factor as cf"];
    return Promise.all([
      list("Item", ["name", "item_name", "item_group", "disabled"], [["item_group", "in", setGroups]]),
      list("Item", ["name", "item_name", "disabled"], [["name", "like", "PNCEB-%"]]),
      list("Item", ["name", "item_name", "disabled"], [["name", "like", "SWREB-%"]]),
      list("Item", ["name", "`tabUOM Conversion Detail`.conversion_factor as cf"], [["UOM Conversion Detail", "uom", "=", "Carton"], ["name", "like", "PNCEB-%"]]),
      list("Item", ["name", "`tabUOM Conversion Detail`.conversion_factor as cf"], [["UOM Conversion Detail", "uom", "=", "Carton"], ["name", "like", "SWREB-%"]]),
      list("Item", ["name", "disabled"], [["name", "in", cartonCodes]]),
      list("Bin", ["item_code", "actual_qty"], [["warehouse", "=", STORES], ["item_code", "like", "COV-%"]]),
      list("Bin", ["item_code", "actual_qty"], [["warehouse", "=", STORES], ["item_code", "like", "FLD-%"]]),
      list("Bin", ["item_code", "actual_qty"], [["warehouse", "=", STORES], ["item_code", "like", "INS-%"]]),
      list("Bin", ["item_code", "actual_qty"], [["warehouse", "=", STORES], ["item_code", "in", cartonCodes]]),
      list("Bin", ["item_code", "actual_qty"], [["warehouse", "=", FG]]),
      list("Sales Order", soFields, openSO.concat([["Sales Order Item", "item_code", "like", "PNCEB-%"]])),
      list("Sales Order", soFields, openSO.concat([["Sales Order Item", "item_code", "like", "SWREB-%"]]))
    ]).then(function (r) {
      var items = {}; r[0].forEach(function (i) { items[i.name] = i; });
      var books = r[1].concat(r[2]).filter(function (b) { return !b.disabled; });
      var cpc = {}; r[3].concat(r[4]).forEach(function (x) { cpc[x.name] = Number(x.cf) || 0; });
      var cartons = {}; r[5].forEach(function (c) { cartons[c.name] = { disabled: !!c.disabled, qty: 0 }; });
      var bin = {};
      r[6].concat(r[7], r[8]).forEach(function (b) { bin[b.item_code + "|" + STORES] = Number(b.actual_qty) || 0; });   // COV-/FLD-/INS- in Stores
      r[10].forEach(function (b) { bin[b.item_code + "|" + FG] = Number(b.actual_qty) || 0; });                       // books in Finished Goods only
      r[9].forEach(function (b) { if (cartons[b.item_code]) cartons[b.item_code].qty = Number(b.actual_qty) || 0; });
      var orders = r[11].concat(r[12]).map(function (o) { return { so: o.name, customer: o.customer, delivery: o.delivery_date, item: o.item_code, pending: Math.max(0, ((Number(o.qty) || 0) - (Number(o.delivered_qty) || 0)) * (Number(o.cf) || 1)) }; }).filter(function (o) { return o.pending > 0; });
      // groups from the COV items
      var groups = {};
      Object.keys(items).forEach(function (code) {
        var m = /^COV-(PNC|SWR)-(A4|A5)-(\d{3})PG-([A-Z0-9]+)$/.exec(code);
        if (!m) return;
        var brand = m[1] === "PNC" ? "Prince" : "Swara", size = m[2], pages = +m[3], ruling = m[4];
        var tail = m[1] + "-" + size + "-" + m[3] + "PG-" + ruling, k = brand + "|" + size + "|" + pages + "|" + ruling;
        var ins = items["INS-" + tail], fld = items["FLD-" + tail];
        if (!ins || !fld) return;
        var upm = /(\d+)\s*up\s*$/i.exec(ins.item_name || "");
        var prefix = brand === "Prince" ? "PNCEB" : "SWREB", paper = brand === "Prince" ? "BP" : "NP";
        var re = new RegExp("^" + prefix + "-" + size + "-" + pages + "PGS-([A-Z]+)-" + paper + "-" + ruling + "$");
        var bks = books.filter(function (b) { return re.test(b.name); }).map(function (b) { return { code: b.name, name: b.item_name, cover: re.exec(b.name)[1], cpc: cpc[b.name] || 0 }; })
          .sort(function (a, b) { return (a.cover === "CB" ? 0 : 1) - (b.cover === "CB" ? 0 : 1) || a.code.localeCompare(b.code); });
        var codes = bks.map(function (b) { return b.code; });
        var dem = orders.filter(function (o) { return codes.indexOf(o.item) >= 0; }).reduce(function (s, o) { return s + o.pending; }, 0);
        groups[k] = { k: k, brand: brand, size: size, pages: pages, ruling: ruling, ups: upm ? +upm[1] : (size === "A4" ? 2 : 3),
          cov: "COV-" + tail, fld: "FLD-" + tail, ins: "INS-" + tail, books: bks, carton: CARTONS[size + "|" + brand], dem: dem };
      });
      D = { items: items, groups: groups, bin: bin, cartons: cartons, orders: orders, loadedAt: new Date() };
    });
  }

  function loadMode() {
    return get(M + "get_mode", {}).then(function (m) {
      MODE = { checked: true, server: true, disabled: !!m.disabled, can_post: !!m.can_post, run_field: !!m.run_field, user: m.user || "" };
    }).catch(function () { MODE = { checked: true, server: false, can_post: false, user: "" }; });
  }

  /* ---------- model ---------- */
  function g() { return D.groups[S.group]; }
  function book() { var gg = g(); return gg.books.filter(function (b) { return b.code === S.book; })[0] || gg.books[0] || null; }
  function stock() {
    var gg = g(), bk = book(), ct = D.cartons[gg.carton] || { qty: 0, disabled: true };
    return { cov: D.bin[gg.cov + "|" + STORES] || 0, fld: D.bin[gg.fld + "|" + STORES] || 0, ins: D.bin[gg.ins + "|" + STORES] || 0,
      fg: bk ? (D.bin[bk.code + "|" + FG] || 0) : 0, carton: ct.qty, cartonEnabled: !ct.disabled };
  }
  function num(v) { var s = String(v == null ? "" : v).replace(/[,\s]/g, ""); if (s === "") return 0; var n = Number(s); return isFinite(n) && n >= 0 && Math.floor(n) === n ? n : NaN; }
  function median(a) { var s = a.slice().sort(function (x, y) { return x - y; }), m = Math.floor(s.length / 2); return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; }

  /* Mirror of eb_capture_rules.plan */
  function planEntry() {
    var gg = g(), s = stock(), bk = book(), u = gg.ups, st = S.station, V = S.v, P = { ok: true, rows: [], msgs: [], type: TYPE[st], extra: {} };
    function row(dir, key, item, wh, qty, before, unit) { P.rows.push({ dir: dir, key: key, item: item, wh: wh, qty: qty, before: before, after: before + qty, unit: unit }); }
    function bad(t) { P.ok = false; P.msgs.push(["bad", t]); }
    var fields = { covers: ["good", "spoiled"], folds: ["good", "rejects"], inserts: ["sets"], packing: ["cartons", "loose", "rejects"] }[st] || [];
    for (var i = 0; i < fields.length; i++) if (isNaN(num(V[fields[i]]))) { bad("Whole numbers only (0 or more)."); return P; }
    if (st === "covers") {
      var good = num(V.good), sp = num(V.spoiled);
      if (good <= 0) { P.ok = false; P.msgs.push(["info", "Enter the good printed sheets counted."]); }
      row("in", "cov", gg.cov, STORES, good, s.cov, "sheets");
      if (sp) P.msgs.push(["info", f(sp) + " spoiled sheets recorded for the run, not added to stock."]);
      P.msgs.push(["info", f(good) + " sheets = " + f(good * u) + " books (" + u + "-up)."]);
      P.extra = { good: good, spoiled: sp };
    } else if (st === "folds") {
      var fg = num(V.good), rj = num(V.rejects);
      if (fg <= 0) { P.ok = false; P.msgs.push(["info", "Enter the good fold sets counted."]); }
      row("in", "fld", gg.fld, STORES, fg, s.fld, "sets");
      if (rj) P.msgs.push(["info", f(rj) + " rejected fold sets recorded for the run, not added."]);
      if (V.opening) P.msgs.push(["info", "Opening count: this is the fold stock found on the floor, not new production."]);
      P.msgs.push(["info", f(fg) + " fold sets = " + f(fg * u) + " books' inners."]);
      P.extra = { good: fg, rejects: rj, opening: !!V.opening };
    } else if (st === "inserts") {
      var n = num(V.sets), hold = !!V.hold;
      if (n <= 0) { P.ok = false; P.msgs.push(["info", "Enter the insert sets made."]); }
      row("out", "cov", gg.cov, STORES, -n, s.cov, "sheets");
      if (!hold) row("out", "fld", gg.fld, STORES, -n, s.fld, "sets");
      row("in", "ins", gg.ins, STORES, n, s.ins, "sets");
      if (n > s.cov) bad("Not enough covers: " + f(s.cov) + " sheets on hand, " + f(n) + " needed. Print more covers first.");
      if (!hold && n > s.fld) bad("Not enough folds: " + f(s.fld) + " fold sets on hand, " + f(n) + " needed. Post the fold count on the Folds station first, or hold off the fold check.");
      if (hold) P.msgs.push(["info", "Fold check held off: folds are not taken out. Use only until the first fold count is posted; this is noted on the entry."]);
      P.msgs.push(["info", f(n) + " insert sets = " + f(n * u) + " books."]);
      P.extra = { sets: n, hold_fold_check: hold };
    } else if (st === "packing") {
      if (!bk) { bad("No book item exists for this group."); return P; }
      var cpc = bk.cpc;
      if (!cpc) { bad("This book has no Carton conversion (books per carton) in ERPNext, so it can't be packed yet."); return P; }
      var ct = num(V.cartons), lo = num(V.loose), rj2 = num(V.rejects), books = ct * cpc + lo, sets = books + rj2 ? Math.ceil((books + rj2) / u) : 0, over = sets * u - books - rj2;
      if (books <= 0) { P.ok = false; P.msgs.push(["info", "Enter the full cartons and any loose books."]); }
      row("out", "ins", gg.ins, STORES, -sets, s.ins, "sets");
      if (ct && s.cartonEnabled) row("out", "carton", gg.carton, STORES, -ct, s.carton, "cartons");
      row("in", "fg", bk.code, FG, books, s.fg, "books");
      if (sets > s.ins) bad("Not enough inserts: " + f(s.ins) + " sets on hand, " + f(sets) + " needed for " + f(books + rj2) + " books.");
      if (ct && s.cartonEnabled && ct > s.carton) bad("Not enough empty cartons for this book: " + f(s.carton) + " on hand.");
      if (ct && !s.cartonEnabled) P.msgs.push(["warn", "The carton item for this size (" + gg.carton + ") is disabled in ERPNext, so empty cartons are NOT taken out on this entry. Enable it to count cartons used."]);
      P.msgs.push(["info", f(ct) + " cartons × " + cpc + " + " + f(lo) + " loose = " + f(books) + " books."]);
      if (over > 0) P.msgs.push(["info", "The last insert set has " + over + " book" + (over > 1 ? "s" : "") + " over: recorded as rejects, so rejects = " + (rj2 + over) + "."]);
      var due = ct > 0 ? Math.max(1, Math.ceil(ct / 20)) : 0;
      var w = String(V.weights || "").split(/[;\s]+/).map(function (x) { return Number(x.replace(",", ".")); }).filter(function (x) { return x > 0; });
      if (due) {
        if (w.length < due) P.msgs.push(["info", "Spot-weigh " + due + " carton" + (due > 1 ? "s" : "") + " (1 in 20): " + (due - w.length) + " still to weigh."]);
        if (w.length >= 2) { var mid = median(w), off = w.filter(function (x) { return Math.abs(x - mid) / mid > 0.05; });
          if (off.length) P.msgs.push(["warn", off.map(function (x) { return x.toFixed(2) + " kg is " + Math.round(Math.abs(x - mid) / mid * 100) + "% " + (x > mid ? "over" : "under"); }).join("; ") + " the others (" + mid.toFixed(2) + " kg). Check the count in that carton."]); }
      }
      P.extra = { books: books, sets: sets, rejects: rj2 + over, cartons: ct, loose: lo, samples_due: due, weights: w.join("; ") };
    }
    return P;
  }

  /* ---------- render ---------- */
  function renderMode() {
    var b;
    if (!MODE.checked) b = '<div class="banner preview">Checking the server…</div>';
    else if (!MODE.server) b = '<div class="banner live">Server update needed: deploy vcl-production feat/eb-capture-v3 and migrate. Until then Post shows what it would do and posts nothing.</div>';
    else if (MODE.disabled) b = '<div class="banner live">Posting is switched off on this site (eb_capture_disabled).</div>';
    else if (!MODE.can_post) b = '<div class="banner live">Your login has no Stock or Manufacturing role, so Post is refused.</div>';
    else b = '<div class="banner preview">Posting changes stock in ERPNext. Every post asks you to confirm twice, and can be undone for 10 minutes.</div>';
    $("v3-banner").innerHTML = b;
    renderChart();
  }

  function renderChart() {
    var st = MODE.server ? "Ready" : "Server update needed";
    function node(x, y, w, n, t, s, cls, stt) { return '<g class="fn ' + cls + '"><rect x="' + x + '" y="' + y + '" width="' + w + '" height="76" rx="4"/><text x="' + (x + 12) + '" y="' + (y + 24) + '" class="fh">' + n + "  " + t + '</text><text x="' + (x + 12) + '" y="' + (y + 44) + '" class="fs">' + s + '</text><text x="' + (x + 12) + '" y="' + (y + 63) + '" class="fst">' + stt + "</text></g>"; }
    var wide = '<svg class="fchart fh-wide" viewBox="0 0 840 196" role="img" aria-label="Production flow: ruling to folds, and covers, both feed inserts, then packing into finished stock"><defs><marker id="v3a1" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" class="fah"/></marker></defs>' +
      '<path d="M132 48H172" class="fa" marker-end="url(#v3a1)"/><path d="M304 48H336V86H366" class="fa" marker-end="url(#v3a1)"/><path d="M218 152H336V114H366" class="fa" marker-end="url(#v3a1)"/><path d="M498 100H542" class="fa" marker-end="url(#v3a1)"/><path d="M674 100H714" class="fa" marker-end="url(#v3a1)"/>' +
      node(4, 10, 128, 1, "Ruling", "Inner papers", "grey", "Phase 2/3") + node(176, 10, 128, 3, "Folds", "Fold sets", "ok", st) + node(90, 114, 128, 2, "Covers", "Printed sheets", "ok", st) +
      node(370, 62, 128, 4, "Inserts", "Covers + folds", "ok", st) + node(546, 62, 128, 5, "Packing", "Cartons", "ok", st) +
      '<g class="fn end"><rect x="718" y="72" width="118" height="56" rx="28"/><text x="777" y="96" text-anchor="middle" class="fh">Finished stock</text><text x="777" y="114" text-anchor="middle" class="fs">Finished Goods - VCL</text></g></svg>';
    var narrow = '<svg class="fchart fh-narrow" viewBox="0 0 340 500" role="img" aria-label="Production flow"><defs><marker id="v3a2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" class="fah"/></marker></defs>' +
      '<path d="M85 86V110" class="fa" marker-end="url(#v3a2)"/><path d="M85 190V208H140V226" class="fa" marker-end="url(#v3a2)"/><path d="M255 190V208H200V226" class="fa" marker-end="url(#v3a2)"/><path d="M170 306V330" class="fa" marker-end="url(#v3a2)"/><path d="M170 410V434" class="fa" marker-end="url(#v3a2)"/>' +
      node(10, 10, 150, 1, "Ruling", "Inner papers", "grey", "Phase 2/3") + node(10, 114, 150, 3, "Folds", "Fold sets", "ok", st) + node(180, 114, 150, 2, "Covers", "Printed sheets", "ok", st) +
      node(95, 230, 150, 4, "Inserts", "Covers + folds", "ok", st) + node(95, 334, 150, 5, "Packing", "Cartons", "ok", st) +
      '<g class="fn end"><rect x="95" y="438" width="150" height="56" rx="28"/><text x="170" y="462" text-anchor="middle" class="fh">Finished stock</text><text x="170" y="480" text-anchor="middle" class="fs">Finished Goods - VCL</text></g></svg>';
    $("v3-chart").innerHTML = wide + narrow;
  }

  function gname(gg) { return gg.brand + " · " + gg.size + " · " + gg.pages + " pages · " + (RUL[gg.ruling] || gg.ruling); }

  function renderShell() {
    var keys = Object.keys(D.groups).sort(function (a, b) { var x = D.groups[a], y = D.groups[b]; return (y.dem > 0) - (x.dem > 0) || y.dem - x.dem || a.localeCompare(b); });
    if (!D.groups[S.group]) S.group = keys[0];
    var withOrders = keys.filter(function (k) { return D.groups[k].dem > 0; }), rest = keys.filter(function (k) { return !D.groups[k].dem; });
    function opt(k) { var gg = D.groups[k]; return '<option value="' + esc(k) + '"' + (k === S.group ? " selected" : "") + ">" + esc(gname(gg)) + (gg.dem ? "  (on order: " + (gcpc(gg) ? c1(gg.dem / gcpc(gg)) + " ctn" : f(gg.dem) + " books") + ")" : "") + "</option>"; }
    $("v3-app").innerHTML = '<div class="cap"><div class="cap-top">' +
      '<label class="cap-grp" for="v3-group"><span class="lb">Working on (brand · size · pages · ruling)</span><select id="v3-group">' +
      (withOrders.length ? '<optgroup label="With open orders">' + withOrders.map(opt).join("") + "</optgroup>" : "") + '<optgroup label="Other groups">' + rest.map(opt).join("") + "</optgroup></select></label>" +
      '<label class="cap-grp" for="v3-book" style="flex:1 1 200px"><span class="lb">Book (packing)</span><select id="v3-book"></select></label>' +
      '<label class="cap-grp" for="v3-run" style="flex:0 1 200px"><span class="lb">Run number</span><input id="v3-run" autocomplete="off" placeholder="e.g. EBR-0001" value="' + esc(S.run) + '"></label>' +
      '<div><button type="button" class="cap-sec" id="v3-reload">Reload stock</button></div></div>' +
      '<div class="cap-steps" id="v3-steps" role="tablist" aria-label="Stations"></div>' +
      '<div class="cap-grid"><div class="cap-card" id="v3-form"></div><div class="cap-card" id="v3-preview"></div></div>' +
      '<div class="cap-card"><div class="cap-h"><h3>Stock for this group</h3><span class="cap-note" id="v3-stocknote"></span></div><div class="cap-stock" id="v3-stock"></div></div>' +
      '<div class="cap-card"><div class="cap-h"><h3>Entries (this session)</h3><span class="cap-note" id="v3-lognote"></span></div><div class="tw"><table><thead><tr><th>#</th><th>Run</th><th>Station</th><th>Entry</th><th>Out</th><th>In</th><th></th></tr></thead><tbody id="v3-log"></tbody></table></div></div></div>' +
      '<p class="cap-note" style="margin-top:10px">Stock as read ' + D.loadedAt.toLocaleTimeString("en-GB") + ". Covers, folds and inserts are in sets (A4 2-up, A5 3-up); books = sets × up-count. Carton per size and brand is a proposal (P12, for Tanuj).</p>";
    var stepsEl = $("v3-steps");
    STEPS.forEach(function (s, i) {
      if (i) { var a = document.createElement("span"); a.className = "arr"; a.textContent = "→"; stepsEl.appendChild(a); }
      var b = document.createElement("button"); b.type = "button"; b.setAttribute("role", "tab"); b.dataset.s = s[0]; if (s[0] === "fg") b.className = "fg";
      b.innerHTML = '<span class="k">' + s[1] + '</span><span class="t">' + s[2] + "</span>";
      b.onclick = function () { S.station = s[0]; S.v = { hold: S.v.hold }; lsSet("station", S.station); renderStation(); };
      stepsEl.appendChild(b);
    });
    $("v3-group").onchange = function (e) { S.group = e.target.value; S.book = null; S.v = { hold: S.v.hold }; lsSet("group", S.group); renderStation(); };
    $("v3-run").oninput = function (e) { S.run = e.target.value; lsSet("run", S.run); renderPreview(); };
    $("v3-reload").onclick = function () { $("v3-reload").textContent = "Reloading…"; load().then(function () { renderShell(); renderStation(); }); };
    renderStation();
  }

  function renderBookPicker() {
    var gg = g(), el = $("v3-book");
    if (!gg.books.length) { el.innerHTML = "<option>No book item</option>"; el.disabled = true; return; }
    if (!S.book || !gg.books.some(function (b) { return b.code === S.book; })) S.book = gg.books[0].code;
    el.disabled = gg.books.length < 2;
    el.innerHTML = gg.books.map(function (b) { return '<option value="' + esc(b.code) + '"' + (b.code === S.book ? " selected" : "") + ">" + esc(b.code) + (b.cpc ? " · " + b.cpc + "/ctn" : " · no Carton UOM") + "</option>"; }).join("");
    el.onchange = function () { S.book = el.value; renderStation(); };
  }

  function renderStation() {
    [].forEach.call($("v3-steps").querySelectorAll("button"), function (b) { b.setAttribute("aria-selected", b.dataset.s === S.station ? "true" : "false"); });
    renderBookPicker(); renderForm(); renderPreview(); renderStock(); renderLog();
  }

  function field(key, label, help) { var id = "v3-" + key, val = S.v[key] == null ? "" : S.v[key]; return '<div class="cap-f"><label class="lb" for="' + id + '">' + label + '</label><input class="qty" id="' + id + '" data-k="' + key + '" inputmode="numeric" autocomplete="off" value="' + esc(val) + '">' + (help ? '<span class="cap-note">' + help + "</span>" : "") + "</div>"; }
  function ro(label, val, mono) { return '<div class="cap-f"><span class="lb">' + label + ' · auto</span><span class="cap-ro' + (mono ? " mono" : "") + '">' + val + "</span></div>"; }

  function renderForm() {
    var gg = g(), bk = book(), s = stock(), el = $("v3-form"), h = "";
    if (S.station === "covers") h = '<div class="cap-h"><h3>Covers: quick entry</h3><span class="chip">Material Receipt</span></div><div class="cap-fields">' + ro("Item", esc(gg.cov), 1) + ro("Sheet", "1 sheet = " + gg.ups + " covers") + field("good", "Good printed sheets", "Count of good sheets off the press") + field("spoiled", "Spoiled sheets", "Recorded, not added") + "</div>";
    if (S.station === "folds") h = '<div class="cap-h"><h3>Folds: entry</h3><span class="chip new">New station</span></div><div class="cap-fields">' + ro("Item", esc(gg.fld), 1) + ro("Unit", "1 fold set = " + gg.ups + " books' inners") + field("good", "Good fold sets") + field("rejects", "Rejected fold sets", "Recorded, not added") + "</div>" +
      '<label class="cap-check"><input type="checkbox" id="v3-opening"' + (S.v.opening ? " checked" : "") + "> This is the opening count of folds already on the floor" + (s.fld === 0 ? " (no fold stock yet)" : "") + "</label>";
    if (S.station === "inserts") h = '<div class="cap-h"><h3>Inserts: make sets</h3><span class="chip">Repack, no BOM</span></div><div class="cap-fields">' + ro("Makes", esc(gg.ins), 1) + ro("Uses", "1 cover sheet + 1 fold set per set") + field("sets", "Insert sets made") + "</div>" +
      '<label class="cap-check"><input type="checkbox" id="v3-hold"' + (S.v.hold ? " checked" : "") + "> Hold off the fold check (no fold count yet). Logged on the entry.</label>";
    if (S.station === "packing") h = '<div class="cap-h"><h3>Packing: receive finished books</h3><span class="chip">Manufacture</span></div><div class="cap-fields">' + ro("Book", bk ? esc(bk.code) : "none", 1) + ro("Books per carton", bk && bk.cpc ? bk.cpc : "not set") +
      field("cartons", "Full cartons") + field("loose", "Loose books") + field("rejects", "Rejected books") + "</div>" +
      '<div class="cap-f"><label class="lb" for="v3-weights">Spot weights, kg (1 carton in 20)</label><input id="v3-weights" data-k="weights" autocomplete="off" placeholder="e.g. 9.8; 9.9; 10.1" value="' + esc(S.v.weights || "") + '"></div>' +
      '<p class="cap-note">Empty carton: <code>' + esc(gg.carton) + "</code> · " + f(s.carton) + " in stock" + (s.cartonEnabled ? "" : " · <b>item disabled in ERPNext</b>") + "</p>";
    if (S.station === "fg") { renderFG(el); return; }
    h += '<button type="button" class="cap-post" id="v3-post">Post ' + (S.station === "packing" ? "and receive into Finished Goods" : "entry") + "</button>";
    el.innerHTML = h;
    [].forEach.call(el.querySelectorAll("input[data-k]"), function (x) { x.oninput = function () { S.v[x.dataset.k] = x.value; renderPreview(); }; });
    var hd = $("v3-hold"); if (hd) hd.onchange = function () { S.v.hold = hd.checked; renderPreview(); };
    var op = $("v3-opening"); if (op) op.onchange = function () { S.v.opening = op.checked; renderPreview(); };
    $("v3-post").onclick = doPost;
  }

  function renderFG(el) {
    var cpcOf = function (code) { var b = g().books.filter(function (x) { return x.code === code; })[0]; return b && b.cpc ? b.cpc : gcpc(g()); };
    var gg = g(), codes = gg.books.map(function (b) { return b.code; });
    var fgRows = gg.books.map(function (b) { var q = D.bin[b.code + "|" + FG] || 0; return { b: b, q: q }; });
    var have = fgRows.reduce(function (s, r) { return s + r.q; }, 0);
    var ord = D.orders.filter(function (o) { return codes.indexOf(o.item) >= 0; }).sort(function (a, b) { return String(a.delivery).localeCompare(String(b.delivery)); });
    var left = have, shortBy = Math.max(0, gg.dem - have);
    el.innerHTML = '<div class="cap-h"><h3>Finished Goods: where production meets sales</h3><span class="chip">Finished Goods - VCL only</span></div>' +
      '<div class="cap-fields">' + ro("In Finished Goods", ctnBooks(have)) + ro("On open orders", ctnBooks(gg.dem)) + ro(shortBy ? "Still short" : "Covered", shortBy ? ctnBooks(shortBy) : "All open orders") + "</div>" +
      '<div class="tw"><table><thead><tr><th>Book</th><th class="num">In stock</th><th class="num">Full cartons + loose</th></tr></thead><tbody>' + fgRows.map(function (r) { return "<tr><td><code>" + esc(r.b.code) + '</code></td><td class="num">' + cb(r.q, r.b.cpc) + '</td><td class="num">' + (r.b.cpc ? f(Math.floor(r.q / r.b.cpc)) + " + " + f(r.q % r.b.cpc) : "-") + "</td></tr>"; }).join("") + "</tbody></table></div>" +
      '<h3 style="margin:6px 0 0">Open orders, earliest delivery first</h3><div class="tw"><table><thead><tr><th>Order</th><th>Customer</th><th>Due</th><th>Book</th><th class="num">Pending</th><th>From stock</th></tr></thead><tbody>' +
      (ord.length ? ord.map(function (o) { var take = Math.min(left, o.pending); left -= take; return "<tr><td>" + esc(o.so) + "</td><td>" + esc(o.customer) + "</td><td>" + esc(o.delivery || "") + "</td><td><code>" + esc(o.item) + '</code></td><td class="num">' + cb(o.pending, cpcOf(o.item)) + "</td><td>" + (take >= o.pending ? "covered" : take ? ctnBooks(take, cpcOf(o.item)) + " of " + ctnBooks(o.pending, cpcOf(o.item)) : "short") + "</td></tr>"; }).join("") : '<tr><td colspan="6" class="cap-note">No open orders for this group.</td></tr>') +
      "</tbody></table></div>";
  }

  function renderPreview() {
    var el = $("v3-preview");
    if (S.station === "fg") {
      var gg = g(), s = stock(), u = gg.ups;
      el.innerHTML = '<div class="cap-h"><h3>The chain for this group</h3></div><div class="cap-rows">' + [["Covers", s.cov, "sheets", s.cov * u], ["Folds", s.fld, "sets", s.fld * u], ["Inserts", s.ins, "sets", s.ins * u], ["Finished Goods", s.fg, "books", s.fg]].map(function (r) { return '<div class="cap-row in"><span class="d">' + r[0].slice(0, 3).toUpperCase() + '</span><span class="it">' + r[0] + "<span>" + f(r[1]) + " " + r[2] + (r[2] === "books" ? "" : " × " + u) + " = " + f(r[3]) + ' books</span></span><span class="q"><b>' + (gcpc(gg) ? c1(r[3] / gcpc(gg)) + " ctn" : f(r[3]) + " books") + "</b><small>" + f(r[3]) + " books</small></span></div>"; }).join("") + "</div>";
      return;
    }
    var P = planEntry(), run = (S.run || "").trim();
    if (!run) { P.ok = false; P.msgs.unshift(["info", "Enter the run number (it goes on the entry)."]); }
    el.innerHTML = '<div class="cap-h"><h3>What this entry will do</h3><span class="cap-note">' + esc(P.type) + " · run " + esc(run || "-") + "</span></div>" +
      '<div class="cap-rows">' + P.rows.map(function (r) { return '<div class="cap-row ' + r.dir + '"><span class="d">' + (r.dir === "out" ? "OUT −" : "IN +") + '</span><span class="it"><code>' + esc(r.item) + "</code><span>" + (r.dir === "out" ? "from " : "into ") + esc(r.wh) + (r.unit !== "books" && r.unit !== "cartons" ? " · " + ctnBooks(Math.abs(r.qty) * g().ups) : "") + '</span></span><span class="q"><b>' + (r.qty > 0 ? "+" : "") + f(r.qty) + "</b><small>" + f(r.before) + " → " + f(r.after) + " " + r.unit + "</small></span></div>"; }).join("") + "</div>" +
      P.msgs.map(function (m) { return '<div class="cap-msg ' + m[0] + '">' + esc(m[1]) + "</div>"; }).join("") + '<div id="v3-result"></div>';
    var pb = $("v3-post"); if (pb) pb.disabled = !P.ok;
  }

  function renderStock() {
    var gg = g(), s = stock(), u = gg.ups;
    var cp = gcpc(gg);
    function asCtn(bk) { return cp ? c1(bk / cp) + " <small>ctn</small>" : f(bk) + " <small>books</small>"; }
    function t(n, v, sub) { return '<div><span class="n">' + n + '</span><span class="v">' + v + '</span><span class="s">' + sub + "</span></div>"; }
    $("v3-stock").innerHTML = t("Covers", asCtn(s.cov * u), f(s.cov) + " sheets × " + u + " = " + f(s.cov * u) + " books") + t("Folds", asCtn(s.fld * u), f(s.fld) + " sets × " + u + " = " + f(s.fld * u) + " books") +
      t("Inserts", asCtn(s.ins * u), f(s.ins) + " sets × " + u + " = " + f(s.ins * u) + " books") + t("Finished Goods", asCtn(s.fg), f(s.fg) + " books · " + (book() ? book().code : "-")) +
      t("Empty cartons", f(s.carton) + " <small>ctn</small>", s.cartonEnabled ? "empty, in Stores - VCL" : "item disabled in ERPNext");
    $("v3-stocknote").textContent = gname(gg) + " · " + u + "-up · " + (cp ? cp + " books/carton · on open orders " + c1(gg.dem / cp) + " ctn (" + f(gg.dem) + " books)" : "no Carton unit · on open orders " + f(gg.dem) + " books");
  }

  function renderLog() {
    var tb = $("v3-log");
    $("v3-lognote").textContent = "Each row is a submitted Stock Entry. Undo is open 10 minutes for the person who posted it.";
    if (!S.log.length) { tb.innerHTML = '<tr><td colspan="7" class="cap-note">Nothing yet. With no fold stock, start with a Folds opening count, then Inserts and Packing.</td></tr>'; return; }
    tb.innerHTML = S.log.slice().reverse().map(function (e) {
      var undo = e.live && e.name && !e.cancelled && (Date.now() - e.at) < 600000 ? '<button type="button" class="cap-sec" data-undo="' + esc(e.name) + '">Undo</button>' : (e.cancelled ? "cancelled" : "");
      return '<tr><td class="num">' + e.n + "</td><td><code>" + esc(e.run) + "</code></td><td>" + esc(e.station) + '<br><span class="cap-note">' + esc(e.grp) + "</span></td><td>" + "<b>" + (e.name ? '<a href="/app/stock-entry/' + encodeURIComponent(e.name) + '" target="_blank" rel="noopener">' + esc(e.name) + "</a>" : "") + "</b><br>" + esc(e.type) + "</td><td>" +
        (e.out.map(function (x) { return "<code>" + esc(x[0]) + "</code> −" + f(x[1]); }).join("<br>") || "-") + "</td><td>" + (e["in"].map(function (x) { return "<code>" + esc(x[0]) + "</code> +" + f(x[1]); }).join("<br>") || "-") + "</td><td>" + undo + "</td></tr>";
    }).join("");
    [].forEach.call(tb.querySelectorAll("[data-undo]"), function (b) { b.onclick = function () { doUndo(b.dataset.undo, b); }; });
  }

  /* ---------- post / undo ---------- */
  var seq = 0;
  function logEntry(P, live, name) {
    var e = { n: ++seq, run: (S.run || "").trim(), station: S.station, grp: gname(g()), type: P.type, live: live, name: name, at: Date.now(), out: [], "in": [] };
    P.rows.forEach(function (r) { if (r.qty) (r.qty < 0 ? e.out : e["in"]).push([r.item, Math.abs(r.qty)]); });
    S.log.push(e);
  }
  /* Two-step confirmation dialog. Buttons are never pre-focused, and Enter does nothing. */
  function dialog(title, bodyHtml, yesLabel, onYes, onBack) {
    var host = document.createElement("div");
    host.className = "dlg-scrim";
    host.innerHTML = '<div class="dlg" role="dialog" aria-modal="true" aria-label="' + esc(title) + '"><h3>' + esc(title) + '</h3><div class="dlg-b">' + bodyHtml +
      '</div><div class="dlg-f"><button type="button" class="cap-sec" data-a="back">Back</button><button type="button" class="cap-post" data-a="yes">' + esc(yesLabel) + "</button></div></div>";
    $("ebv3").appendChild(host);
    function close() { host.remove(); document.removeEventListener("keydown", keys, true); }
    function keys(e) { if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); } if (e.key === "Escape") { close(); if (onBack) onBack(); } }
    document.addEventListener("keydown", keys, true);
    host.querySelector('[data-a="back"]').onclick = function () { close(); if (onBack) onBack(); };
    host.querySelector('[data-a="yes"]').onclick = function () { close(); onYes(); };
  }
  function rowsHtml(P) {
    return '<div class="cap-rows">' + P.rows.filter(function (r) { return r.qty; }).map(function (r) { return '<div class="cap-row ' + r.dir + '"><span class="d">' + (r.dir === "out" ? "OUT −" : "IN +") + '</span><span class="it"><code>' + esc(r.item) + "</code><span>" + (r.dir === "out" ? "from " : "into ") + esc(r.wh) + (r.unit !== "books" && r.unit !== "cartons" ? " · " + ctnBooks(Math.abs(r.qty) * g().ups) : "") + '</span></span><span class="q"><b>' + (r.qty > 0 ? "+" : "") + f(r.qty) + "</b><small>" + f(r.before) + " → " + f(r.after) + " " + r.unit + "</small></span></div>"; }).join("") + "</div>";
  }
  function totals(P) {
    var out = P.rows.filter(function (r) { return r.qty < 0; }).map(function (r) { return f(-r.qty) + " " + r.unit + " of " + r.item; });
    var inn = P.rows.filter(function (r) { return r.qty > 0; }).map(function (r) { return f(r.qty) + " " + r.unit + " of " + r.item; });
    return (out.length ? "Takes out " + out.join(", ") + ". " : "") + (inn.length ? "Puts in " + inn.join(", ") + "." : "");
  }
  function doPost() {
    var P = planEntry(), run = (S.run || "").trim(); if (!P.ok || !run) return;
    if (!MODE.server) { $("v3-result").innerHTML = '<div class="cap-msg bad">' + esc(NEED) + "</div>"; return; }
    var warns = P.msgs.filter(function (m) { return m[0] === "warn" || m[0] === "bad"; });
    dialog("Step 1 of 2: is this correct?",
      "<p><b>" + esc(P.type) + "</b> · run <code>" + esc(run) + "</code> · " + esc(gname(g())) + "</p>" + rowsHtml(P) +
      warns.map(function (m) { return '<div class="cap-msg ' + m[0] + '">' + esc(m[1]) + "</div>"; }).join(""),
      "Yes, this is correct", function () {
        dialog("Step 2 of 2: post to ERPNext now?",
          '<p class="cap-msg warn">This changes stock in ERPNext.</p><p>' + esc(totals(P)) + '</p><p class="cap-note">' + esc(P.type) + " · run " + esc(run) + "</p>",
          "Post now", function () { send(P, run); });
      });
  }
  function send(P, run) {
    var btn = $("v3-post"); btn.disabled = true; btn.textContent = "Posting…";
    var bk = book();
    var payload = { station: S.station, group: S.group, book: bk ? bk.code : null, run: run, weights: P.extra.weights || "", confirmed: 2,
      inputs: { good: S.v.good, spoiled: S.v.spoiled, rejects: S.v.rejects, opening: !!S.v.opening, sets: S.v.sets, hold_fold_check: !!S.v.hold, cartons: S.v.cartons, loose: S.v.loose } };
    post(M + "post_entry", { payload: JSON.stringify(payload) }).then(function (m) {
      logEntry(P, true, m.name);
      return load().then(function () { S.v = { hold: S.v.hold }; renderStation();
        $("v3-result").innerHTML = '<div class="cap-msg ok">Posted ✓ <a href="/app/stock-entry/' + encodeURIComponent(m.name) + '" target="_blank" rel="noopener">' + esc(m.name) + "</a> (" + esc(m.type) + "). Undo is open for 10 minutes in the Entries table.</div>"; });
    }).catch(function (err) {
      btn.disabled = false; btn.textContent = "Post entry";
      var msg = /404|not found|has no attribute|No module|not whitelisted/i.test(err.message) ? NEED : "Not posted. " + err.message;
      $("v3-result").innerHTML = '<div class="cap-msg bad">' + esc(msg) + "</div>";
    });
  }
  function doUndo(name, btn) {
    dialog("Undo step 1 of 2: cancel " + name + "?", "<p>This cancels the Stock Entry and puts the stock back as it was.</p>", "Yes, cancel it", function () {
      dialog("Undo step 2 of 2: cancel in ERPNext now?", '<p class="cap-msg warn">This changes stock in ERPNext.</p><p>' + esc(name) + "</p>", "Cancel the entry now", function () {
        btn.disabled = true; btn.textContent = "Undoing…";
        post(M + "undo_entry", { name: name, confirmed: 2 }).then(function () {
          S.log.forEach(function (e) { if (e.name === name) e.cancelled = true; });
          return load().then(renderStation);
        }).catch(function (err) { btn.disabled = false; btn.textContent = "Undo"; var r = $("v3-result"); if (r) r.innerHTML = '<div class="cap-msg bad">Not undone. ' + esc(err.message) + "</div>"; });
      });
    });
  }

  /* ---------- Orders and Order & stock (ported from v1 /production-dev, 05/11/2026) ----------
   * Read-only. One get_list over Sales Order child rows (no per-order fetch).
   * Units (Tanuj, 05/11/2026): cartons first, books in small print. Cartons come from each item's
   * Carton UOM conversion. Covers/folds/inserts: sheets (or sets) x up-count = books, / books per carton.
   * Fixes from the v1 inventory: covers are SHEETS, inserts are read from Stores stock (so Repacks
   * count), finished stock is Finished Goods - VCL only. */
  var O = null;   // orders data
  var OV = { scope: lsGet("o.scope", "open"), brand: "", customer: "", size: "", pages: "", ruling: "", q: "" };
  var NOT_ORDER_GROUPS = /covers|inserts|folds/i;

  function c1(n) { return (Math.round((Number(n) || 0) * 10) / 10).toLocaleString("en-GB", { maximumFractionDigits: 1 }); }
  /* Cell: cartons big, books small. Without a Carton UOM: books big, flagged. */
  function cb(books, per) {
    return per ? '<b class="ct">' + c1(books / per) + " <span>ctn</span></b><small>" + f(books) + " books</small>"
      : '<b class="ct">' + f(books) + " <span>books</span></b><small>no carton unit</small>";
  }
  /* Sheets or sets -> cartons: n x up-count = books, / books per carton. */
  function cs(n, ups, per, unit) {
    var books = n * ups;
    return '<b class="ct">' + (per ? c1(books / per) + " <span>ctn</span>" : f(books) + " <span>books</span>") + "</b><small>" + f(n) + " " + unit + " × " + ups + "<br>= " + f(books) + " books</small>";
  }
  /* Books per carton for a capture group: the chosen book, else the first with a Carton UOM. */
  function gcpc(gg) { var bk = gg === g() ? book() : null; if (bk && bk.cpc) return bk.cpc; var x = gg.books.filter(function (b) { return b.cpc; })[0]; return x ? x.cpc : 0; }
  function ctnBooks(b, cp) { cp = cp == null ? gcpc(g()) : cp; return (cp ? c1(b / cp) + " ctn · " : "") + f(b) + " books"; }

  function dims(code, name, group) {
    var c = String(code || ""), n = String(name || ""), t = c + " " + n;
    var m = /^(PNCEB|SWREB|SCH-(?:BP|NP|WBP)-EB)-(A\d)-(\d+)PGS-([A-Z]+)-[A-Z]+-([A-Z0-9]+)$/.exec(c);
    var brand = /^PNC/.test(c) || /prince/i.test(t + " " + group) ? "Prince" : /^SWR/.test(c) || /swara/i.test(t + " " + group) ? "Swara" : /hi5/i.test(t + " " + group) ? "Hi5" : /^SCH-|school/i.test(c + " " + group) ? "School" : "Other";
    if (m) return { brand: brand, size: m[2], pages: +m[3], board: m[4], ruling: m[5] };
    var size = (/\b(A[3-6])\b/i.exec(t) || [])[1], pages = (/(\d+)\s*-?\s*(?:pages?|pgs?)\b/i.exec(t) || / - (\d{2,3})\b/.exec(t) || [])[1];
    var rul = /\bHSL\b/i.test(t) ? "HSL" : /\bHSQ\b/i.test(t) ? "HSQ" : /\b(?:Irish|IRS)\b/i.test(t) ? "IRS" : /\b(?:Graph|GPH)\b/i.test(t) ? "GPH" : /\b(?:Plain|PLN)\b/i.test(t) ? "PLN" : /square|\bS\/?Q\b/i.test(t) ? "SQ" : /single|\bS\/?L\b/i.test(t) ? "SL" : /music/i.test(t) ? "MSC" : "";
    var board = /chipboard|\bCB\b/i.test(t) ? "CB" : /manil+a|\bMNL\b/i.test(t) ? "MNL" : /\bMG\s*C(?:over)?\b|\bMGC\b/i.test(t) ? "MGC" : "";
    return { brand: brand, size: size ? size.toUpperCase() : "", pages: pages ? +pages : 0, board: board, ruling: rul };
  }
  function rulName(r) { return r ? (RUL[r] || r) : "Ruling not stated"; }
  function bucketKey(d) { return [d.brand, d.size || "?", d.pages || 0, d.ruling || "?"].join("|"); }

  function loadOrders() {
    return list("Item Group", ["name", "parent_item_group"], []).then(function (gs) {
      var sel = {}; gs.forEach(function (g0) { if (/exercise[\s-]*books?/i.test(g0.name)) sel[g0.name] = 1; });
      var ch = true; while (ch) { ch = false; gs.forEach(function (g0) { if (sel[g0.parent_item_group] && !sel[g0.name]) { sel[g0.name] = 1; ch = true; } }); }
      var groups = Object.keys(sel).filter(function (x) { return !NOT_ORDER_GROUPS.test(x); });
      var cols = ["name", "customer", "customer_name", "transaction_date", "delivery_date", "status", "docstatus",
        "`tabSales Order Item`.item_code as item_code", "`tabSales Order Item`.item_name as item_name", "`tabSales Order Item`.item_group as item_group",
        "`tabSales Order Item`.qty as qty", "`tabSales Order Item`.delivered_qty as delivered_qty", "`tabSales Order Item`.uom as uom",
        "`tabSales Order Item`.conversion_factor as cf", "`tabSales Order Item`.delivery_date as line_due", "`tabSales Order Item`.idx as idx"];
      return Promise.all([
        list("Sales Order", cols, [["Sales Order Item", "item_group", "in", groups], ["docstatus", "<", 2]]),
        list("Item", ["name", "`tabUOM Conversion Detail`.conversion_factor as cf"], [["UOM Conversion Detail", "uom", "=", "Carton"], ["item_group", "in", groups]])
      ]).then(function (r) {
        var cpc = {}; r[1].forEach(function (x) { cpc[x.name] = Number(x.cf) || 0; });
        var lines = r[0].map(function (l) {
          var cf = Number(l.cf) || 1, qty = Number(l.qty) || 0, del = Number(l.delivered_qty) || 0, carton = /^cartons?$/i.test(l.uom);
          var per = carton ? cf : (cpc[l.item_code] || 0);
          return { so: l.name, customer: l.customer_name || l.customer, date: l.transaction_date, due: l.line_due || l.delivery_date, status: l.status, ds: Number(l.docstatus),
            code: l.item_code, name: l.item_name, group: l.item_group, d: dims(l.item_code, l.item_name, l.item_group), per: per, uom: l.uom,
            books: qty * cf, delivered: del * cf, pending: Math.max(0, (qty - del) * cf) };
        });
        O = { lines: lines, cpc: cpc, loadedAt: new Date() };
      });
    });
  }
  function isOpen(l) { return l.ds === 1 && (l.status === "To Deliver and Bill" || l.status === "To Deliver") && l.pending > 0; }
  function isConfirmed(l) { return l.ds === 1 && l.status !== "Closed" && l.status !== "Cancelled"; }
  function passes(l) {
    var d = l.d, q = OV.q.trim().toLowerCase();
    return (!OV.brand || d.brand === OV.brand) && (!OV.customer || l.customer === OV.customer) && (!OV.size || d.size === OV.size) &&
      (!OV.pages || String(d.pages) === OV.pages) && (!OV.ruling || d.ruling === OV.ruling) &&
      (!q || [l.so, l.customer, l.code, l.name].join(" ").toLowerCase().indexOf(q) >= 0);
  }
  function uniq(a) { return a.filter(function (v, i) { return v !== "" && v != null && a.indexOf(v) === i; }); }
  function sel(id, label, cur, opts) {
    return '<label class="cap-grp of"><span class="lb">' + label + '</span><select id="' + id + '"><option value="">All</option>' +
      opts.map(function (o) { var v = Array.isArray(o) ? o[0] : o, t = Array.isArray(o) ? o[1] : o; return '<option value="' + esc(v) + '"' + (String(v) === String(cur) ? " selected" : "") + ">" + esc(t) + "</option>"; }).join("") + "</select></label>";
  }
  function tile(label, ctn, books, extra) { return '<div><span class="n">' + label + '</span><span class="v">' + c1(ctn) + ' <small>ctn</small></span><span class="s">' + f(books) + " books" + (extra || "") + "</span></div>"; }
  function filterBar(withScope) {
    var L = O.lines;
    return '<div class="cap-top">' +
      '<label class="cap-grp" style="flex:2 1 240px"><span class="lb">Search order, customer or item</span><input id="o-q" type="search" autocomplete="off" value="' + esc(OV.q) + '"></label>' +
      sel("o-brand", "Brand", OV.brand, uniq(L.map(function (l) { return l.d.brand; })).sort()) +
      sel("o-customer", "Customer", OV.customer, uniq(L.map(function (l) { return l.customer; })).sort()) +
      sel("o-size", "Size", OV.size, uniq(L.map(function (l) { return l.d.size; })).sort()) +
      sel("o-pages", "Pages", OV.pages, uniq(L.map(function (l) { return l.d.pages || ""; })).sort(function (a, b) { return a - b; })) +
      sel("o-ruling", "Ruling", OV.ruling, uniq(L.map(function (l) { return l.d.ruling; })).sort().map(function (r) { return [r, rulName(r)]; })) + "</div>" +
      '<div class="cap-top">' +
      (withScope ? '<div class="seg" role="group" aria-label="Which orders"><button type="button" data-scope="open" aria-pressed="' + (OV.scope === "open") + '">Open orders</button><button type="button" data-scope="all" aria-pressed="' + (OV.scope === "all") + '">All non-cancelled</button></div>' : "") +
      '<span class="cap-note">Cartons from each item\'s Carton unit; books below in small print.</span>' +
      '<span style="flex:1"></span><div class="btn-grp"><button type="button" class="cap-sec" id="o-xlsx">Download Excel</button><button type="button" class="cap-sec" id="o-pdf">Print / PDF</button><button type="button" class="cap-sec" id="o-reload">Reload</button></div></div>';
  }
  function wireBar(paint) {
    var a = $("v3-app");
    $("o-q").oninput = function (e) { OV.q = e.target.value; paint(true); };
    ["brand", "customer", "size", "pages", "ruling"].forEach(function (k) { $("o-" + k).onchange = function (e) { OV[k] = e.target.value; paint(); }; });
    [].forEach.call(a.querySelectorAll("[data-scope]"), function (b) { b.onclick = function () { OV.scope = b.dataset.scope; lsSet("o.scope", OV.scope); paint(); }; });
    $("o-reload").onclick = function () { this.textContent = "Reloading…"; Promise.all([loadOrders(), load()]).then(function () { paint(); }); };
    $("o-pdf").onclick = function () { window.print(); };
  }
  function keepSearchFocus(fn) { return function (fromSearch) { var pos = fromSearch ? $("o-q").selectionStart : null; fn(); if (fromSearch) { var i = $("o-q"); i.focus(); try { i.setSelectionRange(pos, pos); } catch (e) {} } }; }

  /* Orders: the v1 "Orders Pending" screen. */
  function renderOrders() {
    var paint = keepSearchFocus(function () {
      var conf = O.lines.filter(function (l) { return isConfirmed(l) && passes(l); });
      var shown = O.lines.filter(function (l) { return passes(l) && (OV.scope === "all" ? true : isOpen(l)); })
        .sort(function (a, b) { return String(a.due || "9").localeCompare(String(b.due || "9")) || a.so.localeCompare(b.so); });
      function z(d) { return { d: d, o: 0, dl: 0, p: 0, oc: 0, dc: 0, pc: 0, n: 0, np: 0 }; }
      var T = z(null), B = {};
      conf.forEach(function (l) {
        var k = bucketKey(l.d); B[k] = B[k] || z(l.d);
        [T, B[k]].forEach(function (t) { t.n++; t.o += l.books; t.dl += l.delivered; t.p += l.pending; if (l.per) { t.oc += l.books / l.per; t.dc += l.delivered / l.per; t.pc += l.pending / l.per; } else t.np++; });
      });
      function cell(t, w, cls) {
        var bk = t[w], ct = t[w === "dl" ? "dc" : w + "c"];
        if (t.np === t.n) return '<td class="num ' + cls + '"><b class="ct">' + f(bk) + " <span>books</span></b><small>no carton unit</small></td>";
        return '<td class="num ' + cls + '"><b class="ct">' + c1(ct) + "</b><small>" + f(bk) + (t.np ? " books*" : " books") + "</small></td>";
      }
      var brands = {}; Object.keys(B).forEach(function (k) { var b = B[k]; (brands[b.d.brand] = brands[b.d.brand] || []).push(b); });
      var h = filterBar(true) +
        '<div class="cap-stock">' + tile("Ordered", T.oc, T.o) + tile("Delivered", T.dc, T.dl) + tile("Still to deliver", T.pc, T.p) + "</div>" +
        (T.np ? '<div class="cap-msg warn">' + T.np + " order lines have no Carton unit on the item: their books are in the book figures but not in the cartons (marked *).</div>" : "");
      Object.keys(brands).sort().forEach(function (br) {
        var bs = brands[br], rul = uniq(bs.map(function (b) { return b.d.ruling || "?"; })).sort(function (a, b) { return Object.keys(RUL).indexOf(a) - Object.keys(RUL).indexOf(b); });
        var rows = {}; bs.forEach(function (b) { var k = (b.d.size || "?") + "|" + (b.d.pages || 0); (rows[k] = rows[k] || { size: b.d.size || "Not stated", pages: b.d.pages, by: {} }).by[b.d.ruling || "?"] = b; });
        var rk = Object.keys(rows).sort(function (a, b) { var x = rows[a], y = rows[b]; return x.size.localeCompare(y.size) || (x.pages || 9999) - (y.pages || 9999); });
        var pc = bs.reduce(function (s, b) { return s + b.pc; }, 0), pb = bs.reduce(function (s, b) { return s + b.p; }, 0);
        h += '<div class="cap-card"><div class="cap-h"><h3>' + esc(br) + '</h3><span class="cap-note"><b>' + c1(pc) + " ctn</b> (" + f(pb) + ' books) still to deliver</span></div><div class="tw"><table class="mx"><thead><tr><th rowspan="2">Size</th><th rowspan="2" class="num">Pages</th>' +
          rul.map(function (r) { return '<th colspan="3" class="grp">' + esc(r === "?" ? "Ruling not stated" : rulName(r)) + "</th>"; }).join("") + "</tr><tr>" +
          rul.map(function () { return '<th class="num st">Ordered</th><th class="num">Delivered</th><th class="num pend">Pending</th>'; }).join("") + "</tr></thead><tbody>" +
          rk.map(function (k) { var r = rows[k]; return "<tr><th>" + esc(r.size) + '</th><td class="num">' + (r.pages || "-") + "</td>" + rul.map(function (u) { var b = r.by[u]; return b ? cell(b, "o", "st") + cell(b, "dl", "") + cell(b, "p", "pend") : '<td class="num st empty">-</td><td class="num empty">-</td><td class="num empty">-</td>'; }).join("") + "</tr>"; }).join("") +
          "</tbody></table></div></div>";
      });
      if (!Object.keys(B).length) h += '<div class="cap-msg info">No confirmed orders match these filters.</div>';
      h += '<div class="cap-card"><div class="cap-h"><h3>' + (OV.scope === "open" ? "Open order lines" : "All non-cancelled order lines") + ', earliest delivery first</h3><span class="cap-note">' + shown.length + ' lines</span></div><div class="tw"><table><thead><tr><th>Due</th><th>Order</th><th>Customer</th><th>Item</th><th class="num">Ordered</th><th class="num">Delivered</th><th class="num">Pending</th><th>Status</th></tr></thead><tbody>' +
        (shown.length ? shown.map(function (l) { return '<tr><td class="dt">' + esc(l.due || "") + '</td><td><a href="/app/sales-order/' + encodeURIComponent(l.so) + '" target="_blank" rel="noopener">' + esc(l.so) + "</a></td><td>" + esc(l.customer) + "</td><td><code>" + esc(l.code) + '</code><br><span class="cap-note">' + esc(l.name) + (l.per ? " · " + l.per + " books/carton" : "") + '</span></td><td class="num">' + cb(l.books, l.per) + '</td><td class="num">' + cb(l.delivered, l.per) + '</td><td class="num pend">' + cb(l.pending, l.per) + "</td><td>" + esc(l.ds === 0 ? "Draft" : l.status) + "</td></tr>"; }).join("") : '<tr><td colspan="8" class="cap-note">No order lines match.</td></tr>') +
        "</tbody></table></div></div>" +
        '<p class="cap-note">Grid: confirmed orders, including delivered and on-hold; drafts, cancelled and closed left out. Cartons use each item\'s Carton unit (books per carton); books = order quantity × the line\'s unit conversion. Size, pages and ruling come from the item code, or from the item name for older items. Read ' + O.loadedAt.toLocaleTimeString("en-GB") + ".</p>";
      $("v3-app").innerHTML = '<div class="cap">' + h + "</div>";
      wireBar(paint);
      $("o-xlsx").onclick = function () {
        var q = function (b, p) { return p ? Math.round(b / p * 10) / 10 : ""; };
        download("EB orders " + today(), ["Due", "Order", "Customer", "Item code", "Item", "Brand", "Size", "Pages", "Ruling", "Books per carton", "Ordered (ctn)", "Delivered (ctn)", "Pending (ctn)", "Ordered (books)", "Delivered (books)", "Pending (books)", "Status"],
          shown.map(function (l) { return [l.due || "", l.so, l.customer, l.code, l.name, l.d.brand, l.d.size, l.d.pages || "", rulName(l.d.ruling), l.per || "", q(l.books, l.per), q(l.delivered, l.per), q(l.pending, l.per), l.books, l.delivered, l.pending, l.ds === 0 ? "Draft" : l.status]; }));
      };
    });
    paint();
  }

  /* Order & stock: the v1 comparison, rebuilt on the sheet/set model, in cartons. */
  function renderOrderStock() {
    var paint = keepSearchFocus(function () {
      var open = O.lines.filter(function (l) { return isOpen(l) && passes(l); }), R = {};
      open.forEach(function (l) {
        var k = bucketKey(l.d); R[k] = R[k] || { d: l.d, lines: [], codes: {}, pending: 0, per: 0 };
        R[k].lines.push(l); R[k].codes[l.code] = l.per; R[k].pending += l.pending; if (l.per && !R[k].per) R[k].per = l.per;
      });
      var rows = Object.keys(R).map(function (k) {
        var r = R[k], d = r.d, gk = d.brand + "|" + d.size + "|" + d.pages + "|" + d.ruling, gg = D && D.groups[gk];
        if (gg) gg.books.forEach(function (b) { if (!(b.code in r.codes)) r.codes[b.code] = b.cpc; if (!r.per && b.cpc) r.per = b.cpc; });
        r.fg = Object.keys(r.codes).reduce(function (s, c) { return s + (D.bin[c + "|" + FG] || 0); }, 0);
        r.need = Math.max(0, r.pending - r.fg);
        r.gg = gg || null;
        if (gg) {
          var u = gg.ups; r.cov = D.bin[gg.cov + "|" + STORES] || 0; r.fld = D.bin[gg.fld + "|" + STORES] || 0; r.ins = D.bin[gg.ins + "|" + STORES] || 0;
          r.pipe = (r.ins + r.cov) * u;                       // inserts ready + covers printed (each sheet makes `ups` books)
          r.short = Math.max(0, r.need - r.pipe);
          r.sheets = Math.ceil(r.short / u);
          var ct = gg.carton ? D.cartons[gg.carton] : null; r.ctn = ct ? ct.qty : null; r.ctnOff = ct ? ct.disabled : false;
          r.ctnNeed = r.per ? Math.ceil(r.need / r.per) : null;
        }
        return r;
      }).sort(function (a, b) { return (b.short || 0) - (a.short || 0) || b.need - a.need || bucketKey(a.d).localeCompare(bucketKey(b.d)); });
      function tot(k) { var t = { c: 0, b: 0, miss: 0 }; rows.forEach(function (r) { var v = r[k] || 0; t.b += v; if (r.per) t.c += v / r.per; else if (v) t.miss++; }); return t; }
      var tp = tot("pending"), tf = tot("fg"), tn = tot("need"), ts = tot("short");
      var h = filterBar(false) +
        '<div class="cap-stock">' + tile("On open orders", tp.c, tp.b) + tile("In Finished Goods", tf.c, tf.b, " (matched)") + tile("Still to make", tn.c, tn.b) + tile("Short after stock and pipeline", ts.c, ts.b) + "</div>" +
        (tp.miss ? '<div class="cap-msg warn">' + tp.miss + " book types have no Carton unit, so they are in the book figures but not the cartons.</div>" : "") +
        '<div class="cap-card"><div class="cap-h"><h3>Order & stock by book type</h3><span class="cap-note">' + rows.length + ' book types · biggest shortfall first</span></div><div class="tw"><table class="os"><thead><tr><th>Book type</th><th class="num">Pending</th><th class="num">Finished Goods</th><th class="num">Still to make</th><th class="num">Inserts</th><th class="num">Covers</th><th class="num">Folds</th><th class="num">Short</th><th class="num">Sheets to print</th><th class="num">Empty cartons</th><th></th></tr></thead><tbody>' +
        rows.map(function (r, i) {
          var d = r.d, p = r.per, gg = r.gg;
          return '<tr><th><b>' + esc(d.brand + " · " + (d.size || "?") + " · " + (d.pages || "?") + " pages") + "</b><br>" + esc(rulName(d.ruling)) + '<br><span class="cap-note">' + (p ? p + " books/carton" : "no Carton unit") + (gg ? " · " + gg.ups + "-up" : "") + "</span></th>" +
            '<td class="num">' + cb(r.pending, p) + '</td><td class="num">' + cb(r.fg, p) + '</td><td class="num pend">' + cb(r.need, p) + "</td>" +
            (gg ? '<td class="num">' + cs(r.ins, gg.ups, p, "sets") + '</td><td class="num">' + cs(r.cov, gg.ups, p, "sheets") + '</td><td class="num">' + cs(r.fld, gg.ups, p, "sets") + "</td>" +
              '<td class="num ' + (r.short ? "bad" : "ok") + '">' + (r.short ? cb(r.short, p) : "Covered") + '</td><td class="num">' + (r.sheets ? '<b class="ct">' + f(r.sheets) + " <span>sheets</span></b><small>" + esc(gg.cov) + "</small>" : "-") + "</td>" +
              '<td class="num ' + (r.ctnNeed != null && r.ctn != null && r.ctn < r.ctnNeed ? "bad" : "") + '">' + (r.ctn == null ? "-" : '<b class="ct">' + f(r.ctn) + " <span>ctn</span></b><small>" + (r.ctnOff ? "item disabled" : "shared pool · need " + (r.ctnNeed == null ? "?" : f(r.ctnNeed))) + "</small>") + "</td>"
              : '<td colspan="6" class="cap-note">No covers/folds/inserts items for this type yet (school and Hi5 are Phase 2/3). Only orders and Finished Goods are compared.</td>') +
            '<td><button type="button" class="cap-sec sm" data-det="' + i + '" aria-expanded="false">Details</button></td></tr>' +
            '<tr class="det" id="o-det-' + i + '" hidden><td colspan="11"><div class="detg"><section><b>Finished Goods - VCL by item</b>' + Object.keys(r.codes).map(function (c) { var q = D.bin[c + "|" + FG] || 0, cp = r.codes[c] || p; return "<div><code>" + esc(c) + "</code> · " + (cp ? c1(q / cp) + " ctn · " : "") + f(q) + " books</div>"; }).join("") + "</section>" +
            "<section><b>Open order lines</b>" + r.lines.map(function (l) { return "<div>" + esc(l.due || "") + " · " + esc(l.so) + " · " + esc(l.customer) + " · <b>" + (l.per ? c1(l.pending / l.per) + " ctn" : f(l.pending) + " books") + "</b>" + (l.per ? " (" + f(l.pending) + " books)" : "") + "</div>"; }).join("") + "</section>" +
            (gg ? "<section><b>Stores - VCL</b><div><code>" + esc(gg.cov) + "</code> · " + f(r.cov) + " sheets</div><div><code>" + esc(gg.fld) + "</code> · " + f(r.fld) + " sets</div><div><code>" + esc(gg.ins) + "</code> · " + f(r.ins) + " sets</div><div><code>" + esc(gg.carton || "no carton set") + "</code> · " + (r.ctn == null ? "-" : f(r.ctn)) + " empty cartons</div></section>" : "") + "</div></td></tr>";
        }).join("") + (rows.length ? "" : '<tr><td colspan="11" class="cap-note">No open orders match these filters.</td></tr>') + "</tbody></table></div></div>" +
        '<p class="cap-note">Cartons = books ÷ the book\'s Carton unit. Covers, folds and inserts: sheets (or sets) × up-count (A4 2-up, A5 3-up) = books, then ÷ books per carton. Finished Goods - VCL only. Short = still to make − (inserts + covers) × up-count; folds are shown but not yet counted in the pipeline until there is a fold count. Sheets to print = short ÷ up-count. Empty cartons use the size + brand carton (P12 proposal).</p>';
      $("v3-app").innerHTML = '<div class="cap">' + h + "</div>";
      wireBar(paint);
      [].forEach.call($("v3-app").querySelectorAll("[data-det]"), function (b) { b.onclick = function () { var row = $("o-det-" + b.dataset.det), op = row.hidden; row.hidden = !op; b.setAttribute("aria-expanded", String(op)); b.textContent = op ? "Close" : "Details"; }; });
      $("o-xlsx").onclick = function () {
        var q = function (b, p) { return p ? Math.round(b / p * 10) / 10 : ""; };
        download("EB order and stock " + today(), ["Brand", "Size", "Pages", "Ruling", "Books per carton", "Up-count", "Pending (ctn)", "Finished Goods (ctn)", "Still to make (ctn)", "Inserts (ctn)", "Covers (ctn)", "Folds (ctn)", "Short (ctn)", "Pending (books)", "Finished Goods (books)", "Still to make (books)", "Inserts (sets)", "Covers (sheets)", "Folds (sets)", "Short (books)", "Sheets to print", "Empty cartons", "Cartons needed"],
          rows.map(function (r) { var gg = r.gg, p = r.per, u = gg ? gg.ups : 0; return [r.d.brand, r.d.size, r.d.pages || "", rulName(r.d.ruling), p || "", u || "", q(r.pending, p), q(r.fg, p), q(r.need, p), gg ? q(r.ins * u, p) : "", gg ? q(r.cov * u, p) : "", gg ? q(r.fld * u, p) : "", gg ? q(r.short, p) : "", r.pending, r.fg, r.need, gg ? r.ins : "", gg ? r.cov : "", gg ? r.fld : "", gg ? r.short : "", gg ? r.sheets : "", r.ctn == null ? "" : r.ctn, r.ctnNeed == null ? "" : r.ctnNeed]; }));
      };
    });
    paint();
  }

  function today() { return new Date().toISOString().slice(0, 10); }
  /* Excel download: an .xlsx through the site's ExcelJS (/files/vcl-exceljs-4.4.0.js, used by v1); CSV if it can't load. */
  function download(title, head, rows) {
    function csv() {
      var s = [head].concat(rows).map(function (r) { return r.map(function (c) { c = String(c == null ? "" : c); return /[",\n]/.test(c) ? '"' + c.replace(/"/g, '""') + '"' : c; }).join(","); }).join("\r\n");
      save(new Blob(["﻿" + s], { type: "text/csv" }), title + ".csv");
    }
    function save(blob, name) { var a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500); }
    (window.ExcelJS ? Promise.resolve() : new Promise(function (ok, no) { var s = document.createElement("script"); s.src = "/files/vcl-exceljs-4.4.0.js"; s.onload = ok; s.onerror = no; document.head.appendChild(s); }))
      .then(function () {
        var wb = new ExcelJS.Workbook(), ws = wb.addWorksheet("Sheet1");
        ws.addRow([title + " · read " + new Date().toLocaleString("en-GB")]).font = { bold: true, size: 13 };
        var hr = ws.addRow(head); hr.font = { bold: true, color: { argb: "FFFFFFFF" } }; hr.eachCell(function (c) { c.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FF2B3990" } }; });
        rows.forEach(function (r) { ws.addRow(r); });
        ws.columns.forEach(function (c, i) { c.width = Math.min(40, Math.max(10, String(head[i] || "").length + 2)); });
        ws.views = [{ state: "frozen", ySplit: 2 }];
        return wb.xlsx.writeBuffer().then(function (buf) { save(new Blob([buf], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }), title + ".xlsx"); });
      }).catch(csv);
  }

  /* ---------- views: Capture | Orders | Order & stock ---------- */
  var VIEWS = [["capture", "Capture"], ["orders", "Orders"], ["orderstock", "Order & stock"]];
  function renderViews() {
    $("v3-mode").innerHTML = '<div class="seg views" role="tablist" aria-label="Screens">' + VIEWS.map(function (v) { return '<button type="button" role="tab" data-view="' + v[0] + '" aria-pressed="' + (S.view === v[0]) + '">' + v[1] + "</button>"; }).join("") + "</div>";
    [].forEach.call($("v3-mode").querySelectorAll("[data-view]"), function (b) { b.onclick = function () { showView(b.dataset.view); }; });
  }
  function showView(v) {
    S.view = v; lsSet("view", v);
    try { var u = new URL(location.href); u.searchParams.set("view", v); history.replaceState(null, "", u); } catch (e) {}
    renderViews();
    $("v3-chart").hidden = v !== "capture"; $("v3-banner").hidden = v !== "capture";
    if (v === "capture") { renderShell(); return; }
    var go = function () { if (S.view === v) (v === "orders" ? renderOrders : renderOrderStock)(); };
    if (O) { go(); return; }
    $("v3-app").innerHTML = '<div class="loading">Loading exercise book orders…</div>';
    loadOrders().then(go).catch(function (err) { $("v3-app").innerHTML = '<div class="cap-msg bad">Could not load orders: ' + esc(err.message) + "</div>"; });
  }

  /* ---------- start ---------- */
  function start() {
    S.group = lsGet("group", null); S.station = lsGet("station", "covers"); S.run = lsGet("run", "");
    if (STEPS.map(function (s) { return s[0]; }).indexOf(S.station) < 0) S.station = "covers";
    renderMode();
    var qv = null; try { qv = new URL(location.href).searchParams.get("view"); } catch (e) {}
    S.view = qv || lsGet("view", "capture"); if (!VIEWS.some(function (v) { return v[0] === S.view; })) S.view = "capture";
    Promise.all([loadMode(), load()]).then(function () { renderMode(); showView(S.view); })
      .catch(function (err) { $("v3-app").innerHTML = '<div class="cap-msg bad">Could not read stock from ERPNext: ' + esc(err.message) + ". Are you signed in?</div>"; });
  }
  if (window.frappe && frappe.session && frappe.session.user === "Guest") { location.href = "/login?redirect-to=" + encodeURIComponent(location.pathname + location.search); return; }
  if (window.frappe && typeof frappe.ready === "function") frappe.ready(start); else if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
