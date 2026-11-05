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
  var S = { group: null, book: null, run: "", station: "covers", log: [], v: {} };
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
    $("v3-mode").innerHTML = "";
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
    function opt(k) { var gg = D.groups[k]; return '<option value="' + esc(k) + '"' + (k === S.group ? " selected" : "") + ">" + esc(gname(gg)) + (gg.dem ? "  (on order: " + f(gg.dem) + " books)" : "") + "</option>"; }
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
    var gg = g(), codes = gg.books.map(function (b) { return b.code; });
    var fgRows = gg.books.map(function (b) { var q = D.bin[b.code + "|" + FG] || 0; return { b: b, q: q }; });
    var have = fgRows.reduce(function (s, r) { return s + r.q; }, 0);
    var ord = D.orders.filter(function (o) { return codes.indexOf(o.item) >= 0; }).sort(function (a, b) { return String(a.delivery).localeCompare(String(b.delivery)); });
    var left = have, shortBy = Math.max(0, gg.dem - have);
    el.innerHTML = '<div class="cap-h"><h3>Finished Goods: where production meets sales</h3><span class="chip">Finished Goods - VCL only</span></div>' +
      '<div class="cap-fields">' + ro("In Finished Goods", f(have) + " books") + ro("On open orders", f(gg.dem) + " books") + ro(shortBy ? "Still short" : "Covered", shortBy ? f(shortBy) + " books" : "All open orders") + "</div>" +
      '<div class="tw"><table><thead><tr><th>Book</th><th class="num">Books</th><th class="num">Cartons</th></tr></thead><tbody>' + fgRows.map(function (r) { return "<tr><td><code>" + esc(r.b.code) + '</code></td><td class="num">' + f(r.q) + '</td><td class="num">' + (r.b.cpc ? f(Math.floor(r.q / r.b.cpc)) + " + " + f(r.q % r.b.cpc) : "-") + "</td></tr>"; }).join("") + "</tbody></table></div>" +
      '<h3 style="margin:6px 0 0">Open orders, earliest delivery first</h3><div class="tw"><table><thead><tr><th>Order</th><th>Customer</th><th>Due</th><th>Book</th><th class="num">Books</th><th>From stock</th></tr></thead><tbody>' +
      (ord.length ? ord.map(function (o) { var take = Math.min(left, o.pending); left -= take; return "<tr><td>" + esc(o.so) + "</td><td>" + esc(o.customer) + "</td><td>" + esc(o.delivery || "") + "</td><td><code>" + esc(o.item) + '</code></td><td class="num">' + f(o.pending) + "</td><td>" + (take >= o.pending ? "covered" : take ? f(take) + " of " + f(o.pending) : "short") + "</td></tr>"; }).join("") : '<tr><td colspan="6" class="cap-note">No open orders for this group.</td></tr>') +
      "</tbody></table></div>";
  }

  function renderPreview() {
    var el = $("v3-preview");
    if (S.station === "fg") {
      var gg = g(), s = stock(), u = gg.ups;
      el.innerHTML = '<div class="cap-h"><h3>The chain for this group</h3></div><div class="cap-rows">' + [["Covers", s.cov, "sheets", s.cov * u], ["Folds", s.fld, "sets", s.fld * u], ["Inserts", s.ins, "sets", s.ins * u], ["Finished Goods", s.fg, "books", s.fg]].map(function (r) { return '<div class="cap-row in"><span class="d">' + r[0].slice(0, 3).toUpperCase() + '</span><span class="it">' + r[0] + "<span> = " + f(r[3]) + ' books</span></span><span class="q"><b>' + f(r[1]) + "</b><small>" + r[2] + "</small></span></div>"; }).join("") + "</div>";
      return;
    }
    var P = planEntry(), run = (S.run || "").trim();
    if (!run) { P.ok = false; P.msgs.unshift(["info", "Enter the run number (it goes on the entry)."]); }
    el.innerHTML = '<div class="cap-h"><h3>What this entry will do</h3><span class="cap-note">' + esc(P.type) + " · run " + esc(run || "-") + "</span></div>" +
      '<div class="cap-rows">' + P.rows.map(function (r) { return '<div class="cap-row ' + r.dir + '"><span class="d">' + (r.dir === "out" ? "OUT −" : "IN +") + '</span><span class="it"><code>' + esc(r.item) + "</code><span>" + (r.dir === "out" ? "from " : "into ") + esc(r.wh) + (r.unit !== "books" && r.unit !== "cartons" ? " · " + f(Math.abs(r.qty) * g().ups) + " books" : "") + '</span></span><span class="q"><b>' + (r.qty > 0 ? "+" : "") + f(r.qty) + "</b><small>" + f(r.before) + " → " + f(r.after) + " " + r.unit + "</small></span></div>"; }).join("") + "</div>" +
      P.msgs.map(function (m) { return '<div class="cap-msg ' + m[0] + '">' + esc(m[1]) + "</div>"; }).join("") + '<div id="v3-result"></div>';
    var pb = $("v3-post"); if (pb) pb.disabled = !P.ok;
  }

  function renderStock() {
    var gg = g(), s = stock(), u = gg.ups;
    $("v3-stock").innerHTML = [["Covers", s.cov, "sheets", s.cov * u], ["Folds", s.fld, "sets", s.fld * u], ["Inserts", s.ins, "sets", s.ins * u], ["Finished Goods", s.fg, "books (" + (book() ? book().code : "-") + ")", null], ["Empty cartons", s.carton, "cartons" + (s.cartonEnabled ? "" : " · item disabled"), null]]
      .map(function (it) { return '<div><span class="n">' + it[0] + '</span><span class="v">' + f(it[1]) + '</span><span class="s">' + it[2] + (it[3] != null ? " = " + f(it[3]) + " books" : "") + "</span></div>"; }).join("");
    $("v3-stocknote").textContent = gname(gg) + " · " + gg.ups + "-up · on open orders: " + f(gg.dem) + " books";
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
    return '<div class="cap-rows">' + P.rows.filter(function (r) { return r.qty; }).map(function (r) { return '<div class="cap-row ' + r.dir + '"><span class="d">' + (r.dir === "out" ? "OUT −" : "IN +") + '</span><span class="it"><code>' + esc(r.item) + "</code><span>" + (r.dir === "out" ? "from " : "into ") + esc(r.wh) + (r.unit !== "books" && r.unit !== "cartons" ? " · " + f(Math.abs(r.qty) * g().ups) + " books" : "") + '</span></span><span class="q"><b>' + (r.qty > 0 ? "+" : "") + f(r.qty) + "</b><small>" + f(r.before) + " → " + f(r.after) + " " + r.unit + "</small></span></div>"; }).join("") + "</div>";
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

  /* ---------- start ---------- */
  function start() {
    S.group = lsGet("group", null); S.station = lsGet("station", "covers"); S.run = lsGet("run", "");
    if (STEPS.map(function (s) { return s[0]; }).indexOf(S.station) < 0) S.station = "covers";
    renderMode();
    Promise.all([loadMode(), load()]).then(function () { renderMode(); renderShell(); })
      .catch(function (err) { $("v3-app").innerHTML = '<div class="cap-msg bad">Could not read stock from ERPNext: ' + esc(err.message) + ". Are you signed in?</div>"; });
  }
  if (window.frappe && frappe.session && frappe.session.user === "Guest") { location.href = "/login?redirect-to=" + encodeURIComponent(location.pathname + location.search); return; }
  if (window.frappe && typeof frappe.ready === "function") frappe.ready(start); else if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
