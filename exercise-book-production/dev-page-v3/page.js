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
 * - Reads only through frappe.client.get_list (GET). No REST resource writes for stock.
 *   The one exception is the Priority tab, which writes VCL EB Priority rows only (no stock).
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
  function PHONE() { return window.matchMedia && window.matchMedia("(max-width:700px)").matches; }
  var PLAIN = { covers: "Adds printed cover sheets to stock", folds: "Adds folds to stock", inserts: "Turns cover sheets and folds into inserts", packing: "Packs books into Finished Goods" };
  var RL = { cov: "Cover sheets", fld: "Folds", ins: "Inserts", carton: "Empty cartons", fg: "Finished books" };

  var D = null;          // loaded data
  var S = { view: "capture", group: null, book: null, run: "", date: "", shift: "Day Shift", station: "covers", log: [], v: {} };
  var MODE = { checked: false, server: false, can_post: false, user: "" };
  /* Production date and shift (Tanuj, 05/11/2026). Same shifts as PPC; mirrors eb_capture_rules.check_when. */
  var SHIFTS = ["Day Shift", "Night Shift"], BACKDATE_DAYS = 7;
  function iso(d) { return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2); }
  function todayIso() { return iso(new Date()); }
  function minIso() { var d = new Date(); d.setDate(d.getDate() - BACKDATE_DAYS); return iso(d); }
  function dmy(v) { var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v || ""); return m ? m[3] + "/" + m[2] + "/" + m[1] : v; }
  function whenText() { var m = machine(); return dmy(S.date) + " · " + S.shift + (m ? " · " + m.name : ""); }
  /* Machines come from VCL Production Machine through get_mode, so a new one needs no change here. A station with none set up, or a server without them, shows nothing. */
  function stationMachines() { return (MODE.machines || {})[S.station] || []; }
  function machine() {
    var ms = stationMachines(), name = ms.length === 1 ? ms[0].name : lsGet("machine." + S.station, "");
    return ms.filter(function (m) { return m.name === name; })[0] || null;
  }
  function renderMachines() {
    var ms = stationMachines(), el = $("v3-mach"), cur = machine(); if (!el) return;
    el.hidden = !ms.length;
    el.innerHTML = '<span class="lb">Machine</span><div class="mach-row">' + ms.map(function (m) { return '<button type="button" class="mach" data-m="' + esc(m.name) + '" aria-pressed="' + !!(cur && cur.name === m.name) + '">' + esc(m.name) + "</button>"; }).join("") + "</div>";
  }
  function checkWhen() {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(S.date || "")) return "Pick the production date.";
    if (S.date > todayIso()) return "The production date can't be in the future.";
    if (S.date < minIso()) return "The production date can only go back " + BACKDATE_DAYS + " days. Older entries: ask a Stock Manager.";
    if (SHIFTS.indexOf(S.shift) < 0) return "Pick the shift.";
    return "";
  }
  var OLD_SERVER = "Back-dating needs the server update. Until vcl-production is deployed on Frappe Cloud, entries can only post today.";
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
      MODE = { checked: true, server: true, disabled: !!m.disabled, can_post: !!m.can_post, can_backfill: !!m.can_backfill, backfill_until: m.backfill_until || "", run_field: !!m.run_field, dated: Array.isArray(m.shifts), machines: m.machines || {}, user: m.user || "" };
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
    var wErr = checkWhen(), oldServer = MODE.server && !MODE.dated; /* an older server ignores date and shift, so never promise them */
    if (stationMachines().length && !machine()) bad("Pick the machine.");
    if (wErr) bad(wErr);
    else if (S.date !== todayIso()) { if (oldServer) bad(OLD_SERVER); else P.msgs.push(["warn", "Back-dated: this entry will post on " + dmy(S.date) + " (" + S.shift + "), not today."]); }
    else if (oldServer) P.msgs.push(["warn", "The shift won't be saved on this entry until the server is updated. It will post today."]);
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
      if (fg <= 0) { P.ok = false; P.msgs.push(["info", "Enter the good folds counted."]); }
      row("in", "fld", gg.fld, STORES, fg, s.fld, "folds");
      if (rj) P.msgs.push(["info", f(rj) + " rejected folds recorded for the run, not added."]);
      if (V.opening) P.msgs.push(["info", "Opening count: this is the fold stock found on the floor, not new production."]);
      P.msgs.push(["info", f(fg) + " folds = " + f(fg * u) + " books' inners."]);
      P.extra = { good: fg, rejects: rj, opening: !!V.opening };
    } else if (st === "inserts") {
      var n = num(V.sets), hold = !!V.hold;
      if (n <= 0) { P.ok = false; P.msgs.push(["info", "Enter the inserts made."]); }
      row("out", "cov", gg.cov, STORES, -n, s.cov, "sheets");
      if (!hold) row("out", "fld", gg.fld, STORES, -n, s.fld, "folds");
      row("in", "ins", gg.ins, STORES, n, s.ins, "inserts");
      if (n > s.cov) bad("Not enough covers: " + f(s.cov) + " sheets on hand, " + f(n) + " needed. Print more covers first.");
      if (!hold && n > s.fld) bad("Not enough folds: " + f(s.fld) + " folds on hand, " + f(n) + " needed. Post the fold count on the Folds station first.");
      if (hold) P.msgs.push(["warn", "Folds will NOT be deducted for this entry. Use this only until the first fold count is posted. It is noted on the entry."]);
      P.msgs.push(["info", f(n) + " inserts = " + f(n * u) + " books."]);
      P.extra = { sets: n, hold_fold_check: hold };
    } else if (st === "packing") {
      if (!bk) { bad("No book item exists for this group."); return P; }
      var cpc = bk.cpc;
      if (!cpc) { bad("This book has no Carton conversion (books per carton) in ERPNext, so it can't be packed yet."); return P; }
      var ct = num(V.cartons), lo = num(V.loose), rj2 = num(V.rejects), books = ct * cpc + lo, sets = books + rj2 ? Math.ceil((books + rj2) / u) : 0, over = sets * u - books - rj2;
      if (books <= 0) { P.ok = false; P.msgs.push(["info", "Enter the full cartons and any loose books."]); }
      row("out", "ins", gg.ins, STORES, -sets, s.ins, "inserts");
      if (ct && s.cartonEnabled) row("out", "carton", gg.carton, STORES, -ct, s.carton, "cartons");
      row("in", "fg", bk.code, FG, books, s.fg, "books");
      if (sets > s.ins) bad("Not enough inserts: " + f(s.ins) + " on hand, " + f(sets) + " needed for " + f(books + rj2) + " books.");
      if (ct && s.cartonEnabled && ct > s.carton) bad("Not enough empty cartons for this book: " + f(s.carton) + " on hand.");
      if (ct && !s.cartonEnabled) P.msgs.push(["warn", "The carton item for this size (" + gg.carton + ") is disabled in ERPNext, so empty cartons are NOT taken out on this entry. Enable it to count cartons used."]);
      P.msgs.push(["info", f(ct) + " cartons × " + cpc + " + " + f(lo) + " loose = " + f(books) + " books."]);
      if (over > 0) P.msgs.push(["info", "The last insert has " + over + " book" + (over > 1 ? "s" : "") + " over: recorded as rejects, so rejects = " + (rj2 + over) + "."]);
      var due = ct > 0 ? Math.max(1, Math.ceil(ct / 20)) : 0;
      var w = String(V.weights || "").split(/[;\s]+/).map(function (x) { return Number(x.replace(",", ".")); }).filter(function (x) { return x > 0; });
      if (due) {
        if (w.length < due) P.msgs.push(["info", "Spot-weigh " + due + " carton" + (due > 1 ? "s" : "") + " (1 in 20): " + (due - w.length) + " still to weigh."]);
        if (w.length >= 2) { var mid = median(w), off = w.filter(function (x) { return Math.abs(x - mid) / mid > 0.05; });
          if (off.length) P.msgs.push(["warn", off.map(function (x) { return x.toFixed(2) + " kg is " + Math.round(Math.abs(x - mid) / mid * 100) + "% " + (x > mid ? "over" : "under"); }).join("; ") + " the others (" + mid.toFixed(2) + " kg). Check the count in that carton."]); }
      }
      P.extra = { books: books, sets: sets, rejects: rj2 + over, cartons: ct, loose: lo, samples_due: due, weights: w.join("; ") };
    }
    dupWarn(P);
    return P;
  }

  /* ---------- render ---------- */
  function renderMode() {
    var b;
    if (!MODE.checked) b = "";
    else if (!MODE.server) b = '<div class="banner live">Server update needed: deploy vcl-production feat/eb-capture-v3 and migrate. Until then Post shows what it would do and posts nothing.</div>';
    else if (MODE.disabled) b = '<div class="banner live">Posting is switched off on this site (eb_capture_disabled).</div>';
    else if (!MODE.can_post) b = '<div class="banner live">Your login has no Stock or Manufacturing role, so Post is refused.</div>';
    else b = "";
    $("v3-banner").innerHTML = b;
  }

  function gname(gg) { return gg.brand + " · " + gg.size + " · " + gg.pages + " pages · " + (RUL[gg.ruling] || gg.ruling); }
  function bdot(brand) { return '<i class="bdot" data-b="' + esc(brand) + '" aria-hidden="true"></i>'; }

  function renderShell() {
    if (!D.groups[S.group]) S.group = groupKeys()[0];
    $("v3-app").innerHTML = '<div class="cap" id="v3-cap"><div class="cap-card pick-card"><div class="pick-top">' +
      '<label class="cap-grp pick-q" for="v3-pickq"><span class="lb">1. Search for the book type</span><input id="v3-pickq" type="search" autocomplete="off" placeholder="e.g. prince 96 square"></label>' +
      '<div class="pick-now"><span class="lb">Working on</span><small id="v3-picks"></small></div></div>' +
      '<p class="pick-or">Or click through: <b>Brand</b> → <b>Pages</b> → <b>Size</b> → <b>Ruling</b></p><div class="pick-l" id="v3-pickl"></div></div>' +
      '<div class="cap-steps" id="v3-steps" role="tablist" aria-label="Stations"></div><div class="cap-top">' +
      '<label class="cap-grp" for="v3-run" style="flex:0 1 190px"><span class="lb">Run or press (required)</span><input id="v3-run" autocomplete="off" required aria-required="true" placeholder="e.g. Miller" value="' + esc(S.run) + '"></label>' +
      '<label class="cap-grp" for="v3-date" style="flex:0 1 170px"><span class="lb">Production date</span><input id="v3-date" type="date" min="' + minIso() + '" max="' + todayIso() + '" value="' + esc(S.date) + '"></label>' +
      '<label class="cap-grp" for="v3-shift" style="flex:0 1 150px"><span class="lb">Shift</span><select id="v3-shift">' + SHIFTS.map(function (x) { return '<option' + (x === S.shift ? " selected" : "") + ">" + x + "</option>"; }).join("") + "</select></label>" +
      '<div class="cap-grp mach-w" id="v3-mach" hidden></div></div>' +
      '<div class="cap-grid"><div class="cap-card" id="v3-form"></div><div class="cap-card" id="v3-preview"></div></div>' +
      '<div class="cap-card" id="v3-today"></div>' +
      '<div class="cap-card" id="v3-logcard" hidden><div class="cap-h"><h3>Posted from this screen</h3><span class="cap-note" id="v3-lognote"></span></div><div class="tw"><table><thead><tr><th>#</th><th>Run · date · shift</th><th>Station</th><th>Entry</th><th>Out</th><th>In</th><th></th></tr></thead><tbody id="v3-log"></tbody></table></div></div>' +
      '<details class="cap-card fold" id="v3-stockcard"' + (PHONE() ? "" : " open") + '><summary class="cap-h"><div><h3>Stock for this item</h3><span class="cap-note" id="v3-stocknote"></span></div><span class="fold-i" aria-hidden="true"></span></summary><div class="fold-b"><div class="cap-stock" id="v3-stock"></div><button type="button" class="cap-sec" id="v3-reload">Reload stock</button></div></details>' +
      '<p class="cap-note">Stock as read ' + D.loadedAt.toLocaleTimeString("en-GB") + ". Each cover sheet, fold or insert makes 2 A4 books or 3 A5 books.</p>" +
      '<div class="cap-bar" id="v3-bar"><div class="t"><b id="v3-barsum"></b><small>Every post is confirmed twice, and can be undone for 10 minutes.</small></div><button type="button" class="cap-post" id="v3-post">Post entry</button></div></div>';
    var stepsEl = $("v3-steps");
    STEPS.forEach(function (s, i) {
      if (i) { var a = document.createElement("span"); a.className = "arr"; a.textContent = "→"; stepsEl.appendChild(a); }
      var b = document.createElement("button"); b.type = "button"; b.setAttribute("role", "tab"); b.dataset.s = s[0]; if (s[0] === "fg") b.className = "fg";
      b.innerHTML = '<span class="k">' + s[1] + '</span><span class="t">' + s[2] + "</span>";
      b.onclick = function () { S.station = s[0]; S.v = {}; lsSet("station", S.station); renderStation(); };
      stepsEl.appendChild(b);
    });
    $("v3-pickq").oninput = function (e) { renderPick(e.target.value); };
    $("v3-pickq").parentNode.parentNode.onkeydown = function (e) { if (e.key === "Escape") pickCancel(); };
    $("v3-pickl").onclick = function (e) {
      var b = e.target.closest("button"); if (!b || b.disabled) return;
      if (b.dataset.cancel) return pickCancel();
      if (b.dataset.k) return pickChoose(b.dataset.k);
      $("v3-pickq").value = "";
      if (b.dataset.back) pickBack(b.dataset.back);
      else if (b.dataset.f) PK[b.dataset.f] = b.dataset.f === "pages" ? +b.dataset.v : b.dataset.v;
      else return;
      renderPick(""); pickFocus();
    };
    $("v3-mach").onclick = function (e) { var b = e.target.closest("[data-m]"); if (!b) return; lsSet("machine." + S.station, b.dataset.m); renderMachines(); renderPreview(); };
    $("v3-run").oninput = function (e) { S.run = e.target.value; lsSet("run", S.run); renderPreview(); };
    $("v3-date").onchange = $("v3-date").oninput = function (e) { S.date = e.target.value; renderPreview(); renderToday(); };
    $("v3-shift").onchange = function (e) { S.shift = e.target.value; lsSet("shift", S.shift); renderPreview(); };
    $("v3-reload").onclick = function () { $("v3-reload").textContent = "Reloading…"; clearProduction(); load().then(function () { renderShell(); }); };
    $("v3-post").onclick = doPost;
    pickSync(); if (!S.chosen) PK = {}; renderPick(""); renderStation();
  }

  /* Item choice: part of the Capture screen, at the top. Brand, pages, size, ruling as chips; tap a chip to change from there, or type to search.
     S.group only changes once all four are set. Until then #v3-cap has data-picking and the count, preview and Post are hidden, so nothing can post against a half-picked item. */
  var PK = {};
  var PICK_BRANDS = ["Prince", "Swara", "Hi5", "School"], PICK_ORDER = ["brand", "pages", "size", "ruling"];
  function pickSync() { var gg = g(); PK = { brand: gg.brand, pages: gg.pages, size: gg.size, ruling: gg.ruling }; }
  function pickBusy() { return PICK_ORDER.some(function (f) { return PK[f] == null; }); }
  function pickCancel() { if (!S.chosen) return; $("v3-pickq").value = ""; pickSync(); renderPick(""); }
  function pickBack(f) { PICK_ORDER.slice(PICK_ORDER.indexOf(f)).forEach(function (x) { delete PK[x]; }); }
  function pickMatches() { return groupKeys().filter(function (k) { var gg = D.groups[k]; return PICK_ORDER.every(function (f) { return PK[f] == null || gg[f] === PK[f]; }); }); }
  function pickVals(f) { return uniq(pickMatches().map(function (k) { return D.groups[k][f]; })).sort(function (a, b) { return f === "pages" ? a - b : String(a).localeCompare(String(b)); }); }
  function pickFocus() { var l = $("v3-pickl"), b = l.querySelector(".pick-o button:not(:disabled)") || l.querySelector(".pick-c button"); if (b) b.focus(); }
  function pickMatchesFor(f, v) { return pickMatches().filter(function (k) { return D.groups[k][f] === v; }); }
  function pickTile(f, v, label) {
    var ks = pickMatchesFor(f, v), open = ks.some(function (k) { return D.groups[k].dem > 0; });
    var note = f === "ruling" ? onOrder(D.groups[ks[0]]) : open ? "On order" : "No open orders";
    return '<button type="button" data-f="' + f + '" data-v="' + esc(v) + '"' + (f === "brand" ? ' data-b="' + esc(v) + '"' : "") + "><b>" + esc(label) + "</b><small>" + esc(note) + "</small></button>";
  }
  function groupKeys() { return Object.keys(D.groups).sort(function (a, b) { var x = D.groups[a], y = D.groups[b]; return (y.dem > 0) - (x.dem > 0) || y.dem - x.dem || a.localeCompare(b); }); }
  function onOrder(gg) { return gg.dem ? "On order " + (gcpc(gg) ? c1(gg.dem / gcpc(gg)) + " ctn" : f(gg.dem) + " books") : "No open orders"; }
  function recents() { try { return JSON.parse(lsGet("recent", "[]")).filter(function (k) { return D.groups[k]; }); } catch (e) { return []; } }
  function pickLabel() { $("v3-picks").textContent = pickBusy() ? (S.chosen ? "Choosing. Cancel keeps " + gname(g()) : "Nothing chosen yet") : onOrder(g()); }
  function pickChipText(f) { return f === "pages" ? PK[f] + " pages" : f === "ruling" ? (RUL[PK[f]] || PK[f]) : PK[f]; }
  function renderPick(q) {
    var keys = groupKeys(), toks = String(q || "").toLowerCase().split(/\s+/).filter(Boolean);
    function row(k) { var gg = D.groups[k]; return '<button type="button" data-k="' + esc(k) + '"' + (k === S.group ? ' aria-current="true"' : "") + "><b>" + esc(gname(gg)) + "</b><small>" + esc(onOrder(gg)) + "</small></button>"; }
    if (!toks.length) {
      if (PK.brand && PK.pages && PK.size == null) { var sz = pickVals("size"); if (sz.length === 1) PK.size = sz[0]; }        // e.g. 100 pages is A5 only
      if (PK.size && PK.ruling == null) { var ru = pickVals("ruling"); if (ru.length === 1) PK.ruling = ru[0]; }
      if (!pickBusy()) { var done = pickMatches()[0]; if (done !== S.group) return pickChoose(done); }
    }
    var head = '<div class="pick-c">' + PICK_ORDER.filter(function (f) { return PK[f] != null; }).map(function (f) { return '<button type="button" data-back="' + f + '"' + (f === "brand" ? ' data-b="' + esc(PK.brand) + '"' : "") + ' aria-label="Change ' + f + '">' + esc(pickChipText(f)) + "</button>"; }).join("") +
      (pickBusy() && S.chosen ? '<button type="button" class="pick-x" data-cancel="1">Cancel</button>' : "") + "</div>", body = "";
    function tiles(t, html) { return '<p class="pick-h">' + t + '</p><div class="pick-o">' + html + "</div>"; }
    if (toks.length) {
      var hit = keys.filter(function (k) { var gg = D.groups[k], hay = (gname(gg) + " " + gg.ruling + " " + gg.cov).toLowerCase(); return toks.every(function (t) { return hay.indexOf(t) >= 0; }); });
      body = hit.length ? '<div class="pick-hits">' + hit.map(row).join("") + "</div>" : '<p class="pick-h">No items match.</p>';
    } else if (!PK.brand) {
      body = tiles("Brand or school", PICK_BRANDS.map(function (b) {
        return keys.some(function (k) { return D.groups[k].brand === b; }) ? pickTile("brand", b, b) : '<button type="button" data-b="' + b + '" disabled><b>' + b + "</b><small>No cover, fold or insert items yet</small></button>";
      }).join(""));
    } else if (!PK.pages) {
      var rec = recents().filter(function (k) { return D.groups[k].brand === PK.brand; });
      body = tiles("Pages", pickVals("pages").map(function (p) { return pickTile("pages", p, p + " pages"); }).join("")) + (rec.length ? '<p class="pick-h">Recent ' + esc(PK.brand) + '</p><div class="pick-hits">' + rec.map(row).join("") + "</div>" : "");
    }
    else if (!PK.size) body = tiles("Size", pickVals("size").map(function (s) { return pickTile("size", s, s); }).join(""));
    else if (!PK.ruling) body = tiles("Ruling", pickVals("ruling").map(function (r) { return pickTile("ruling", r, RUL[r] || r); }).join(""));
    $("v3-pickl").innerHTML = head + body;
    $("v3-cap").dataset.picking = pickBusy() ? "1" : "";
    pickLabel();
  }
  function pickChoose(k) {
    var changed = k !== S.group;
    S.chosen = true;
    if (changed) { S.group = k; S.book = null; S.v = {}; lsSet("group", k); }
    lsSet("recent", JSON.stringify([k].concat(recents().filter(function (x) { return x !== k; })).slice(0, 4)));
    $("v3-pickq").value = ""; pickSync(); renderPick("");
    if (changed) renderStation();
  }

  function renderBookPicker() {
    var gg = g(), el = $("v3-book");
    if (gg.books.length && (!S.book || !gg.books.some(function (b) { return b.code === S.book; }))) S.book = gg.books[0].code;
    if (!el) return;
    if (!gg.books.length) { el.innerHTML = "<option>No book item</option>"; el.disabled = true; return; }
    el.disabled = gg.books.length < 2;
    el.innerHTML = gg.books.map(function (b) { return '<option value="' + esc(b.code) + '"' + (b.code === S.book ? " selected" : "") + ">" + esc(b.name || b.code) + (b.cpc ? " · " + b.cpc + " per carton" : " · no carton size") + "</option>"; }).join("");
    el.onchange = function () { S.book = el.value; renderStation(); };
  }

  function renderStation() {
    [].forEach.call($("v3-steps").querySelectorAll("button"), function (b) { b.setAttribute("aria-selected", b.dataset.s === S.station ? "true" : "false"); });
    pickLabel(); renderMachines(); renderBookPicker(); renderForm(); renderBookPicker(); renderPreview(); renderToday(); renderStock(); renderLog();
  }

  function field(key, label, help, big) { var id = "v3-" + key, val = S.v[key] == null ? "" : S.v[key]; return '<div class="cap-f"><label class="lb" for="' + id + '">' + label + '</label><input class="qty' + (big ? " big" : "") + '" id="' + id + '" data-k="' + key + '" inputmode="numeric" autocomplete="off" value="' + esc(val) + '">' + (help ? '<span class="cap-note">' + help + "</span>" : "") + "</div>"; }
  function ro(label, val, mono) { return '<div class="cap-f"><span class="lb">' + label + ' · auto</span><span class="cap-ro' + (mono ? " mono" : "") + '">' + val + "</span></div>"; }
  function formHead(title, code, note) { return '<div class="cap-h"><div><h3>' + title + '</h3><span class="cap-note" title="' + esc(code) + '">' + note + "</span></div></div>"; }

  function renderForm() {
    var gg = g(), bk = book(), s = stock(), el = $("v3-form"), h = "";
    if (S.station === "covers") h = formHead("Covers", gg.cov, "1 sheet = " + gg.ups + " covers") + field("good", "Good printed sheets", "", 1) + '<div class="cap-fields">' + field("spoiled", "Spoiled sheets", "Recorded, not added") + "</div>";
    if (S.station === "folds") h = formHead("Folds", gg.fld, "1 fold = " + gg.ups + " books") + field("good", "Good folds", "", 1) + '<div class="cap-fields">' + field("rejects", "Rejected folds", "Recorded, not added") + "</div>" +
      '<label class="cap-check"><input type="checkbox" id="v3-opening"' + (S.v.opening ? " checked" : "") + "> This is the opening count of folds already on the floor" + (s.fld === 0 ? " (no fold stock yet)" : "") + "</label>";
    if (S.station === "inserts") h = formHead("Inserts", gg.ins, "1 cover sheet + 1 fold = 1 insert") + field("sets", "Inserts made", "", 1) +
      (s.fld === 0 ? '<label class="cap-check"><input type="checkbox" id="v3-hold"' + (S.v.hold ? " checked" : "") + "> Opening period only: do not deduct folds for this entry. Noted on the entry.</label>" : "");
    if (S.station === "packing") h = '<div class="cap-h"><div><h3>Packing</h3><span class="cap-note">' + (bk && bk.cpc ? bk.cpc + " books per carton" : "Books per carton not set") + '</span></div></div><label class="cap-f" for="v3-book"><span class="lb">Book</span><select id="v3-book"></select></label>' +
      field("cartons", "Full cartons", "", 1) + '<div class="cap-fields">' + field("loose", "Loose books") + field("rejects", "Rejected books") + "</div>" +
      '<div class="cap-f"><label class="lb" for="v3-weights">Spot weights, kg (1 carton in 20)</label><input id="v3-weights" data-k="weights" autocomplete="off" placeholder="e.g. 9.8; 9.9; 10.1" value="' + esc(S.v.weights || "") + '"></div>' +
      '<p class="cap-note">Empty carton: <code>' + esc(gg.carton) + "</code> · " + f(s.carton) + " in stock" + (s.cartonEnabled ? "" : " · <b>item disabled in ERPNext</b>") + "</p>";
    if (S.station === "fg") { renderFG(el); return; }
    el.innerHTML = h;
    [].forEach.call(el.querySelectorAll("input[data-k]"), function (x) { x.oninput = function () { S.v[x.dataset.k] = x.value; renderPreview(); }; });
    var hd = $("v3-hold"); if (hd) hd.onchange = function () { S.v.hold = hd.checked; renderPreview(); };
    var op = $("v3-opening"); if (op) op.onchange = function () { S.v.opening = op.checked; renderPreview(); };
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

  /* Back-post (Tanuj, 05/11/2026): System Manager only, until the server's date. The server decides;
   * this only offers it when eb_capture.post_backfill_packing would accept. Mirrors rules.backfill_plan. */
  function backfillNeed(P) {
    if (S.station !== "packing" || !MODE.can_backfill || !(S.run || "").trim() || S.posting) return 0;
    var s = stock(), need = (P.extra.sets || 0) - s.ins;
    if (need <= 0 || !P.extra.books || need > s.cov || (s.fld > 0 && s.fld < need)) return 0;
    if (P.msgs.some(function (m) { return m[0] === "bad" && !/^Not enough inserts/.test(m[1]); })) return 0;
    return need;
  }
  function backfillBox(need) {
    return '<div class="cap-msg warn">Short by ' + f(need) + " inserts. As System Manager you can post them with this packing while past days are being entered" + (MODE.backfill_until ? " (open until " + esc(dmy(MODE.backfill_until)) + ")" : "") + '.</div><button type="button" class="cap-sec" id="v3-bf" data-need="' + need + '">Post ' + f(need) + " inserts, then pack</button>";
  }
  function renderPreview() {
    var el = $("v3-preview");
    $("v3-bar").hidden = S.station === "fg";
    if (S.station === "fg") {
      var gg = g(), s = stock(), u = gg.ups;
      el.innerHTML = '<div class="cap-h"><h3>The chain for this group</h3></div><div class="cap-rows">' + [["Covers", s.cov, "sheets", s.cov * u], ["Folds", s.fld, "folds", s.fld * u], ["Inserts", s.ins, "inserts", s.ins * u], ["Finished Goods", s.fg, "books", s.fg]].map(function (r) { return '<div class="cap-row in"><span class="d">' + r[0].slice(0, 3).toUpperCase() + '</span><span class="it">' + r[0] + "<span>" + f(r[1]) + " " + r[2] + (r[2] === "books" ? "" : " × " + u) + " = " + f(r[3]) + ' books</span></span><span class="q"><b>' + (gcpc(gg) ? c1(r[3] / gcpc(gg)) + " ctn" : f(r[3]) + " books") + "</b><small>" + f(r[3]) + " books</small></span></div>"; }).join("") + "</div>";
      return;
    }
    var P = planEntry(), run = (S.run || "").trim(), has = P.rows.some(function (r) { return r.qty; });
    if (!run) P.ok = false;
    var msgs = P.msgs.filter(function (m) { return has || m[0] !== "info"; });
    el.innerHTML = '<div class="cap-h"><h3>What this entry will do</h3><span class="cap-note">' + esc(PLAIN[S.station] || P.type) + " · run " + esc(run || "-") + " · " + esc(whenText()) + "</span></div>" +
      (has ? '<div class="cap-rows">' + P.rows.map(function (r) { return '<div class="cap-row ' + r.dir + '"><span class="d">' + (r.dir === "out" ? "OUT −" : "IN +") + '</span><span class="it"><b title="' + esc(r.item) + '">' + esc(RL[r.key] || r.item) + "</b><span>" + (r.dir === "out" ? "from " : "into ") + esc(r.wh) + (r.unit !== "books" && r.unit !== "cartons" ? " · " + ctnBooks(Math.abs(r.qty) * g().ups) : "") + '</span></span><span class="q"><b>' + (r.qty > 0 ? "+" : "") + f(r.qty) + "</b><small>" + f(r.before) + " → " + f(r.after) + " " + r.unit + "</small></span></div>"; }).join("") + "</div>"
        : '<p class="cap-empty">Enter a count to see exactly what will post.</p>') +
      msgs.map(function (m) { return '<div class="cap-msg ' + m[0] + '">' + esc(m[1]) + "</div>"; }).join("") + (backfillNeed(P) ? backfillBox(backfillNeed(P)) : "") + '<div id="v3-result"></div>';
    var bf = $("v3-bf"); if (bf) bf.onclick = function () { doBackfill(+bf.dataset.need); };
    $("v3-run").classList.toggle("need", has && !run);
    var pb = $("v3-post");
    pb.disabled = !!S.posting || !P.ok;
    pb.textContent = S.posting ? "Posting…" : (S.station === "packing" ? "Post and receive" : "Post entry");
    $("v3-barsum").textContent = barText(P, run, has);
  }
  function barText(P, run, has) {
    var ask = P.msgs.filter(function (m) { return m[0] === "info" && /^Enter/.test(m[1]); })[0];
    if (P.msgs.some(function (m) { return m[0] === "bad"; })) return "Can't post yet. See the notes above.";
    if (ask) return ask[1];
    if (!run) return "Enter the run or press.";
    var r = P.rows.filter(function (x) { return x.qty > 0; })[0];
    if (!r || !has) return "";
    var cp = gcpc(g()), books = r.unit === "books" ? r.qty : r.qty * g().ups;
    return "+" + f(r.qty) + " " + r.unit + (cp ? " · " + c1(books / cp) + " ctn" : "") + " · " + (RL[r.key] || r.item);
  }

  /* What is already in ERPNext for this station on the chosen date (other tablets included). */
  var PROC_OF = { covers: "cov", folds: "fld", inserts: "ins", packing: "pack" };
  function validDate() { return /^\d{4}-\d{2}-\d{2}$/.test(S.date || ""); }
  function stationRows() {
    if (!validDate()) return [];
    return (PC[mondayOf(S.date)] || []).filter(function (r) { return r.date === S.date && r.proc === PROC_OF[S.station]; });
  }
  function dupWarn(P) {
    var r = P.rows.filter(function (x) { return x.qty > 0; })[0]; if (!r) return;
    var hit = stationRows().filter(function (x) { return x.k === S.group && x.qty === r.qty; })[0];
    if (hit) P.msgs.push(["warn", "Possible duplicate: " + f(hit.qty) + " " + r.unit + " already posted for this item on " + dmy(S.date) + " (" + hit.se + (hit.run ? ", run " + hit.run : "") + "). Check before posting."]);
  }
  function renderToday() {
    var el = $("v3-today"); if (!el) return;
    el.hidden = S.station === "fg" || !validDate(); if (el.hidden) return;
    var w = mondayOf(S.date), when = S.date === todayIso() ? "today" : "on " + dmy(S.date);
    var head = '<div class="cap-h"><div><h3>Already posted ' + when + "</h3>";
    if (!PC[w] || Date.now() - (PCat[w] || 0) > 60000) {
      if (!PC[w]) el.innerHTML = head + '</div></div><p class="cap-note">Reading ERPNext…</p>';
      var again = function () { if (S.view === "capture") { renderToday(); renderPreview(); } };
      loadWeek(w).then(again).catch(function () { PC[w] = PC[w] || []; PCat[w] = Date.now(); PCerr[w] = true; again(); });
      if (!PC[w]) return;
    }
    var unit = PROCS.filter(function (p) { return p[0] === PROC_OF[S.station]; })[0][2], all = stationRows(), mine = all.filter(function (r) { return r.k === S.group; });
    var name = STEPS.filter(function (s) { return s[0] === S.station; })[0][2], entries = {};
    all.forEach(function (r) { entries[r.se] = 1; });
    el.innerHTML = head + '<span class="cap-note">' + esc(name) + " · all items: " + (all.length ? f(sum(all).q) + " " + unit + " in " + Object.keys(entries).length + (Object.keys(entries).length === 1 ? " entry" : " entries") : "nothing yet") + "</span></div></div>" +
      (PCerr[w] ? '<div class="cap-msg warn">Could not read ERPNext, so this list and the duplicate check may be incomplete.</div>' : "") +
      (mine.length ? '<div class="tw"><table><thead><tr><th>Time</th><th>Run</th><th class="num">This item</th><th>By</th><th>Entry</th></tr></thead><tbody>' +
        mine.slice().sort(function (a, b) { return String(b.at).localeCompare(String(a.at)); }).map(function (r) { return '<tr><td class="dt">' + esc(String(r.at).slice(11, 16)) + "</td><td>" + esc(r.run || "-") + '</td><td class="num">' + pcell([r], unit) + "</td><td>" + esc(String(r.by || "").split("@")[0]) + '</td><td><a href="/app/stock-entry/' + encodeURIComponent(r.se) + '" target="_blank" rel="noopener">' + esc(r.se) + "</a></td></tr>"; }).join("") + "</tbody></table></div>"
        : '<p class="cap-note">Nothing posted for this item ' + when + ".</p>");
  }

  function renderStock() {
    var gg = g(), s = stock(), u = gg.ups;
    var cp = gcpc(gg);
    function asCtn(bk) { return cp ? c1(bk / cp) + " <small>ctn</small>" : f(bk) + " <small>books</small>"; }
    function eq(bk) { return f(bk) + " books" + (cp ? " · about " + c1(bk / cp) + " ctn" : ""); }
    function t(n, v, sub) { return '<div><span class="n">' + n + '</span><span class="v">' + v + '</span><span class="s">' + sub + "</span></div>"; }
    $("v3-stock").innerHTML = t("Cover sheets", f(s.cov) + " <small>sheets</small>", eq(s.cov * u)) + t("Folds", f(s.fld) + " <small>folds</small>", eq(s.fld * u)) +
      t("Inserts", f(s.ins) + " <small>inserts</small>", eq(s.ins * u)) + t("Finished Goods", asCtn(s.fg), f(s.fg) + " books") +
      t("Empty cartons", f(s.carton) + " <small>ctn</small>", s.cartonEnabled ? "empty, in Stores - VCL" : "item disabled in ERPNext");
    $("v3-stocknote").textContent = gname(gg) + " · " + u + "-up · " + (cp ? cp + " books/carton · on open orders " + c1(gg.dem / cp) + " ctn (" + f(gg.dem) + " books)" : "no Carton unit · on open orders " + f(gg.dem) + " books");
  }

  function renderLog() {
    var tb = $("v3-log");
    $("v3-lognote").textContent = "Each row is a submitted Stock Entry. Undo is open 10 minutes for the person who posted it.";
    $("v3-logcard").hidden = !S.log.length;
    if (!S.log.length) return;
    tb.innerHTML = S.log.slice().reverse().map(function (e) {
      var undo = e.live && e.name && !e.cancelled && (Date.now() - e.at) < 600000 ? '<button type="button" class="cap-sec" data-undo="' + esc(e.name) + '">Undo</button>' : (e.cancelled ? "cancelled" : "");
      return '<tr><td class="num">' + e.n + "</td><td><code>" + esc(e.run) + '</code><br><span class="cap-note">' + esc(e.when || "") + "</span></td><td>" + esc(e.station) + '<br><span class="cap-note">' + esc(e.grp) + "</span></td><td>" + "<b>" + (e.name ? '<a href="/app/stock-entry/' + encodeURIComponent(e.name) + '" target="_blank" rel="noopener">' + esc(e.name) + "</a>" : "") + "</b><br>" + esc(e.type) + "</td><td>" +
        (e.out.map(function (x) { return "<code>" + esc(x[0]) + "</code> −" + f(x[1]); }).join("<br>") || "-") + "</td><td>" + (e["in"].map(function (x) { return "<code>" + esc(x[0]) + "</code> +" + f(x[1]); }).join("<br>") || "-") + "</td><td>" + undo + "</td></tr>";
    }).join("");
    [].forEach.call(tb.querySelectorAll("[data-undo]"), function (b) { b.onclick = function () { doUndo(b.dataset.undo, b); }; });
  }

  /* ---------- post / undo ---------- */
  var seq = 0;
  function logEntry(P, live, name, st) {
    var e = { n: ++seq, run: (S.run || "").trim(), when: whenText(), station: st || S.station, grp: gname(g()), type: PLAIN[st || S.station] || P.type, live: live, name: name, at: Date.now(), out: [], "in": [] };
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
    return '<div class="cap-rows">' + P.rows.filter(function (r) { return r.qty; }).map(function (r) { return '<div class="cap-row ' + r.dir + '"><span class="d">' + (r.dir === "out" ? "OUT −" : "IN +") + '</span><span class="it"><b title="' + esc(r.item) + '">' + esc(RL[r.key] || r.item) + "</b><span>" + (r.dir === "out" ? "from " : "into ") + esc(r.wh) + (r.unit !== "books" && r.unit !== "cartons" ? " · " + ctnBooks(Math.abs(r.qty) * g().ups) : "") + '</span></span><span class="q"><b>' + (r.qty > 0 ? "+" : "") + f(r.qty) + "</b><small>" + f(r.before) + " → " + f(r.after) + " " + r.unit + "</small></span></div>"; }).join("") + "</div>";
  }
  function totals(P) {
    var out = P.rows.filter(function (r) { return r.qty < 0; }).map(function (r) { return f(-r.qty) + " " + r.unit + " of " + r.item; });
    var inn = P.rows.filter(function (r) { return r.qty > 0; }).map(function (r) { return f(r.qty) + " " + r.unit + " of " + r.item; });
    return (out.length ? "Takes out " + out.join(", ") + ". " : "") + (inn.length ? "Puts in " + inn.join(", ") + "." : "");
  }
  function doPost() {
    if (S.posting) return;
    var P0 = planEntry(), run0 = (S.run || "").trim(); if (!P0.ok || !run0) return;
    if (!MODE.server) { $("v3-result").innerHTML = '<div class="cap-msg bad">' + esc(NEED) + "</div>"; return; }
    var btn = $("v3-post"), checked = true; btn.disabled = true; btn.textContent = "Checking…";
    loadWeek(mondayOf(S.date)).catch(function () { checked = false; }).then(function () {
      renderToday(); renderPreview();
      var P = planEntry(), run = (S.run || "").trim(); if (!P.ok || !run) return;
      if (!checked) P.msgs.push(["warn", "Could not check ERPNext for duplicates. Look at the list before posting."]);
      var warns = P.msgs.filter(function (m) { return m[0] === "warn" || m[0] === "bad"; });
      dialog("Step 1 of 2: is this correct?",
        "<p><b>" + esc(PLAIN[S.station] || P.type) + "</b> · run <code>" + esc(run) + "</code> · " + esc(gname(g())) + "</p><p><b>Production date " + esc(whenText()) + "</b></p>" + rowsHtml(P) +
        warns.map(function (m) { return '<div class="cap-msg ' + m[0] + '">' + esc(m[1]) + "</div>"; }).join(""),
        "Yes, this is correct", function () {
          dialog("Step 2 of 2: post to ERPNext now?",
            '<p class="cap-msg warn">This changes stock in ERPNext.</p><p>' + esc(totals(P)) + '</p><p class="cap-note">' + esc(PLAIN[S.station] || P.type) + " · run " + esc(run) + " · " + esc(whenText()) + "</p>",
            "Post now", function () { send(P, run); });
        });
    });
  }
  function entryPayload(P, run) {
    var bk = book();
    return { station: S.station, group: S.group, book: bk ? bk.code : null, run: run, date: S.date, shift: S.shift, machine: (machine() || {}).name || "", weights: P.extra.weights || "", confirmed: 2,
      inputs: { good: S.v.good, spoiled: S.v.spoiled, rejects: S.v.rejects, opening: !!S.v.opening, sets: S.v.sets, hold_fold_check: !!S.v.hold, cartons: S.v.cartons, loose: S.v.loose } };
  }
  function doBackfill(need) {
    if (S.posting) return;
    var P = planEntry(), run = (S.run || "").trim(), s = stock();
    if (backfillNeed(P) !== need) return;
    var folds = s.fld === 0 ? "Folds are not deducted: none are recorded yet." : f(need) + " folds come out of stock.";
    dialog("Step 1 of 2: back-post " + f(need) + " inserts and pack?",
      "<p><b>" + esc(gname(g())) + "</b> · run <code>" + esc(run) + "</code></p><p><b>Production date " + esc(whenText()) + "</b></p>" +
      "<p><b>Entry 1:</b> " + f(need) + " cover sheets out, " + f(need) + " inserts in. " + esc(folds) + "</p>" +
      "<p><b>Entry 2:</b> pack " + f(P.extra.books) + " books into Finished Goods.</p>" +
      '<div class="cap-msg warn">Both are marked as back-posted by you. If either fails, neither posts.</div>',
      "Yes, this is correct", function () {
        dialog("Step 2 of 2: post both to ERPNext now?", '<p class="cap-msg warn">This changes stock in ERPNext.</p><p>' + f(need) + " inserts, then " + f(P.extra.books) + " books packed.</p>", "Post both now", function () { sendBackfill(P, run); });
      });
  }
  function sendBackfill(P, run) {
    var btn = $("v3-post"); S.posting = true; btn.disabled = true; btn.textContent = "Posting…";
    post(M + "post_backfill_packing", { payload: JSON.stringify(entryPayload(P, run)) }).then(function (m) {
      logEntry({ rows: m.inserts.rows, type: m.inserts.type }, true, m.inserts.name, "inserts");
      logEntry({ rows: m.packing.rows, type: m.packing.type }, true, m.packing.name, "packing");
      S.posting = false; clearProduction();
      return load().catch(function () {}).then(function () { S.v = {}; renderStation();
        $("v3-result").innerHTML = '<div class="cap-msg ok">Posted ✓ ' + f(m.need) + ' inserts (<a href="/app/stock-entry/' + encodeURIComponent(m.inserts.name) + '" target="_blank" rel="noopener">' + esc(m.inserts.name) + '</a>) and the packing (<a href="/app/stock-entry/' + encodeURIComponent(m.packing.name) + '" target="_blank" rel="noopener">' + esc(m.packing.name) + "</a>). To undo, cancel the packing first.</div>"; });
    }).catch(function (err) {
      S.posting = false; btn.textContent = "Post and receive"; renderPreview();
      var msg = /404|not found|has no attribute|No module|not whitelisted/i.test(err.message) ? NEED : "Not posted. Neither entry went through. " + err.message;
      $("v3-result").innerHTML = '<div class="cap-msg bad">' + esc(msg) + "</div>";
    });
  }
  function send(P, run) {
    var btn = $("v3-post"); S.posting = true; btn.disabled = true; btn.textContent = "Posting…";
    post(M + "post_entry", { payload: JSON.stringify(entryPayload(P, run)) }).then(function (m) {
      logEntry(P, true, m.name); S.posting = false; clearProduction();
      /* it has posted: a failed stock refresh must not read as "Not posted" */
      return load().catch(function () {}).then(function () { S.v = {}; renderStation();
        $("v3-result").innerHTML = '<div class="cap-msg ok">Posted ✓ <a href="/app/stock-entry/' + encodeURIComponent(m.name) + '" target="_blank" rel="noopener">' + esc(m.name) + "</a> (" + esc(m.type) + "). Undo is open for 10 minutes in the Entries table.</div>"; });
    }).catch(function (err) {
      S.posting = false; btn.disabled = false; btn.textContent = "Post entry";
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
          clearProduction();
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
  function barBtns() { return '<div class="btn-grp"><button type="button" class="cap-sec" id="o-xlsx">Download Excel</button><button type="button" class="cap-sec" id="o-pdf">Print / PDF</button><button type="button" class="cap-sec" id="o-reload">Reload</button></div>'; }
  function filterBar(withScope, noActions) {
    var L = O.lines, on = ["q", "brand", "customer", "size", "pages", "ruling"].filter(function (k) { return OV[k]; }).length;
    return '<details class="cap-card fold fb"' + (PHONE() ? "" : " open") + '><summary class="cap-h"><div><h3>Filters</h3><span class="cap-note">' + (on ? on + " on" : "none on") + '</span></div><span class="fold-i" aria-hidden="true"></span></summary><div class="cap-top fb-in">' +
      '<label class="cap-grp" style="flex:2 1 240px"><span class="lb">Search order, customer or item</span><input id="o-q" type="search" autocomplete="off" value="' + esc(OV.q) + '"></label>' +
      sel("o-brand", "Brand", OV.brand, uniq(L.map(function (l) { return l.d.brand; })).sort()) +
      sel("o-customer", "Customer", OV.customer, uniq(L.map(function (l) { return l.customer; })).sort()) +
      sel("o-size", "Size", OV.size, uniq(L.map(function (l) { return l.d.size; })).sort()) +
      sel("o-pages", "Pages", OV.pages, uniq(L.map(function (l) { return l.d.pages || ""; })).sort(function (a, b) { return a - b; })) +
      sel("o-ruling", "Ruling", OV.ruling, uniq(L.map(function (l) { return l.d.ruling; })).sort().map(function (r) { return [r, rulName(r)]; })) + "</div></details>" + (noActions ? "" :
      '<div class="cap-top">' +
      (withScope ? '<div class="seg" role="group" aria-label="Which orders"><button type="button" data-scope="open" aria-pressed="' + (OV.scope === "open") + '">Open orders</button><button type="button" data-scope="all" aria-pressed="' + (OV.scope === "all") + '">All non-cancelled</button></div>' : "") +
      '<span class="cap-note">Cartons from each item\'s Carton unit; books below in small print.</span>' +
      '<span style="flex:1"></span>' + barBtns() + "</div>");
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
        h += '<div class="cap-card" data-b="' + esc(br) + '"><div class="cap-h"><h3 class="bdot">' + esc(br) + '</h3><span class="cap-note"><b>' + c1(pc) + " ctn</b> (" + f(pb) + ' books) still to deliver</span></div><div class="tw"><table class="mx"><thead><tr><th rowspan="2">Size</th><th rowspan="2" class="num">Pages</th>' +
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
  /* Sorting only: a type with no Carton unit counts as about 100 books a carton. */
  function shortCtn(r) { return (r.short || 0) / (r.per || 100); }
  /* Stacked bar: Finished Goods, inserts + covers, short, not tracked. parts = [class, value, label]. */
  function covBar(parts, text) {
    var all = parts.reduce(function (t, p) { return t + p[1]; }, 0);
    return '<div class="os-bar" role="img" aria-label="' + esc(text) + '">' + parts.map(function (p) { return p[1] > 0 && all ? '<span class="' + p[0] + '" style="width:' + (p[1] / all * 100).toFixed(2) + '%" title="' + esc(p[2]) + '"></span>' : ""; }).join("") + "</div>";
  }
  function osStat(label, big, unit, sub) { return '<div class="os-st"><span class="n">' + label + '</span><span class="v">' + big + (unit ? " <small>" + unit + "</small>" : "") + '</span><span class="s">' + sub + "</span></div>"; }
  function osStore(label, n, gg, p, unit) {
    if (!n) return osStat(label, "None", "", "in Stores - VCL");
    var bk = n * gg.ups;
    return osStat(label, f(n), unit, f(bk) + " books" + (p ? " · about " + c1(bk / p) + " ctn" : ""));
  }
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
        r.uFg = r.pending - r.need; r.uPipe = gg ? r.need - r.short : 0; r.uNone = gg ? 0 : r.need;
        return r;
      }).sort(function (a, b) { return shortCtn(b) - shortCtn(a) || b.need - a.need || bucketKey(a.d).localeCompare(bucketKey(b.d)); });
      function tot(k) { var t = { c: 0, b: 0, miss: 0 }; rows.forEach(function (r) { var v = r[k] || 0; t.b += v; if (r.per) t.c += v / r.per; else if (v) t.miss++; }); return t; }
      var tp = tot("pending"), tf = tot("fg"), tn = tot("need"), ts = tot("short"), tuf = tot("uFg"), tup = tot("uPipe"), tun = tot("uNone");
      function leg(cls, label, t, sub) { return '<div class="os-lg"><i class="' + cls + '"></i><span class="n">' + label + '</span><span class="v">' + c1(t.c) + ' <small>ctn</small></span><span class="s">' + f(t.b) + " books" + (sub || "") + "</span></div>"; }
      var h = filterBar(false, true) +
        '<section class="os-hero"><div class="os-big"><span class="n">Short after stock and pipeline</span><span class="v">' + c1(ts.c) + ' <small>ctn</small></span><span class="s">' + f(ts.b) + " books · from " + c1(tp.c) + " ctn on open orders, " + c1(tn.c) + " ctn still to make</span></div>" +
        covBar([["fg", tuf.c, "Finished Goods"], ["pipe", tup.c, "Inserts and covers"], ["short", ts.c, "Short"], ["none", tun.c, "Not tracked"]], c1(tuf.c) + " cartons from Finished Goods, " + c1(tup.c) + " from inserts and covers, " + c1(ts.c) + " short, " + c1(tun.c) + " not tracked") +
        '<div class="os-legs">' + leg("fg", "From Finished Goods", tuf, " · " + c1(tf.c) + " ctn in stock") + leg("pipe", "From inserts and covers", tup) + leg("short", "Short", ts) + leg("none", "Not tracked yet", tun, " · School and Hi5") + "</div></section>" +
        (tp.miss ? '<div class="cap-msg warn">' + tp.miss + " book types have no Carton unit, so they are in the book figures but not the cartons.</div>" : "") +
        '<div class="cap-card os-card"><div class="cap-h"><div><h3>By book type</h3><span class="cap-note">' + rows.length + ' book types · biggest shortfall first · tap a row for stock and orders</span></div><div class="os-act">' + barBtns() + '</div></div><div class="tw"><table class="osl"><thead><tr><th>Book type</th><th class="num">Pending</th><th>Covered</th><th class="num">Short</th><th class="num">Sheets to print</th><th><span class="vh">Details</span></th></tr></thead><tbody>' +
        rows.map(function (r, i) {
          var d = r.d, p = r.per, gg = r.gg, cov = r.pending ? Math.round((r.uFg + r.uPipe) / r.pending * 100) : 0;
          var low = r.ctnNeed != null && r.ctn != null && !r.ctnOff && r.ctn < r.ctnNeed;
          var bar = covBar([["fg", r.uFg, "Finished Goods " + f(r.uFg) + " books"], ["pipe", r.uPipe, "Inserts and covers " + f(r.uPipe) + " books"], ["short", r.short || 0, "Short " + f(r.short || 0) + " books"], ["none", r.uNone, "Not tracked " + f(r.uNone) + " books"]], cov + "% covered");
          return '<tr class="osr" data-row="' + i + '"><th scope="row"><b class="bdot" data-b="' + esc(d.brand) + '">' + esc(d.brand + " " + (d.size || "?") + " · " + (d.pages || "?") + " pages") + '</b><span class="sub">' + esc(rulName(d.ruling)) + " · " + (p ? p + " books/ctn" : "no Carton unit") + (gg ? " · " + gg.ups + "-up" : "") + "</span>" + (low ? '<span class="chip low">Empty cartons low</span>' : "") + "</th>" +
            '<td class="num" data-l="Pending">' + cb(r.pending, p) + "</td>" +
            '<td class="cv">' + bar + '<span class="pc">' + (gg ? cov + "% covered" : (r.uFg ? cov + "% from Finished Goods" : "Not tracked yet")) + "</span></td>" +
            '<td class="num" data-l="Short">' + (!gg ? '<span class="dash">-</span>' : r.short ? '<span class="sh">' + cb(r.short, p) + "</span>" : '<span class="chip okc">Covered</span>') + "</td>" +
            '<td class="num" data-l="Sheets to print">' + (r.sheets ? '<b class="ct">' + f(r.sheets) + "</b><small>sheets</small>" : '<span class="dash">-</span>') + "</td>" +
            '<td class="tg"><button type="button" class="os-tog" data-det="' + i + '" aria-expanded="false" aria-controls="o-det-' + i + '" aria-label="Details for ' + esc(d.brand + " " + (d.size || "") + " " + (d.pages || "") + " pages") + '"></button></td></tr>' +
            '<tr class="det" id="o-det-' + i + '" hidden><td colspan="6"><div class="os-sts">' +
            (gg ? osStore("Inserts", r.ins, gg, p, "inserts") + osStore("Covers", r.cov, gg, p, "sheets") + osStore("Folds", r.fld, gg, p, "folds") +
              osStat("Empty cartons", r.ctn == null ? "-" : f(r.ctn), r.ctn == null ? "" : "ctn", r.ctn == null ? "no carton set" : r.ctnOff ? "item disabled" : "shared pool · need " + (r.ctnNeed == null ? "?" : f(r.ctnNeed)))
              : '<p class="cap-note">No covers, folds or inserts items for this type yet (School and Hi5 are Phase 2/3). Only orders and Finished Goods are compared.</p>') + '</div><div class="detg"><section><b>Open order lines</b>' +
            r.lines.map(function (l) { return "<div>" + esc(l.due || "") + " · " + esc(l.so) + " · " + esc(l.customer) + " · <b>" + (l.per ? c1(l.pending / l.per) + " ctn" : f(l.pending) + " books") + "</b>" + (l.per ? " (" + f(l.pending) + " books)" : "") + "</div>"; }).join("") + "</section>" +
            "<section><b>Finished Goods - VCL by item</b>" + Object.keys(r.codes).map(function (c) { var q = D.bin[c + "|" + FG] || 0, cp = r.codes[c] || p; return "<div><code>" + esc(c) + "</code> · " + (cp ? c1(q / cp) + " ctn · " : "") + f(q) + " books</div>"; }).join("") + "</section>" +
            (gg ? "<section><b>Item codes in Stores - VCL</b><div><code>" + esc(gg.cov) + "</code></div><div><code>" + esc(gg.fld) + "</code></div><div><code>" + esc(gg.ins) + "</code></div><div><code>" + esc(gg.carton || "no carton set") + "</code></div></section>" : "") + "</div></td></tr>";
        }).join("") + (rows.length ? "" : '<tr><td colspan="6" class="cap-note">No open orders match these filters.</td></tr>') + "</tbody></table></div></div>" +
        '<details class="os-how"><summary>How these figures work</summary><p>Cartons = books ÷ the book\'s Carton unit. Cover sheets, folds and inserts × 2 for A4 or 3 for A5 = books, then ÷ books per carton. Finished Goods - VCL only. Short = still to make − (inserts + covers) × up-count; folds are shown but not yet counted in the pipeline until there is a fold count. Sheets to print = short ÷ up-count. Empty cartons use the shared carton for that size and brand.</p></details>';
      $("v3-app").innerHTML = '<div class="cap">' + h + "</div>";
      wireBar(paint);
      [].forEach.call($("v3-app").querySelectorAll("[data-det]"), function (b) { b.onclick = function () { var row = $("o-det-" + b.dataset.det), op = row.hidden; row.hidden = !op; b.setAttribute("aria-expanded", String(op)); }; });
      [].forEach.call($("v3-app").querySelectorAll("tr.osr"), function (t) { t.onclick = function (e) { if (!e.target.closest("button")) t.querySelector("[data-det]").click(); }; });
      $("o-xlsx").onclick = function () {
        var q = function (b, p) { return p ? Math.round(b / p * 10) / 10 : ""; };
        download("EB order and stock " + today(), ["Brand", "Size", "Pages", "Ruling", "Books per carton", "Up-count", "Pending (ctn)", "Finished Goods (ctn)", "Still to make (ctn)", "Inserts (ctn)", "Covers (ctn)", "Folds (ctn)", "Short (ctn)", "Pending (books)", "Finished Goods (books)", "Still to make (books)", "Inserts", "Cover sheets", "Folds", "Short (books)", "Sheets to print", "Empty cartons", "Cartons needed"],
          rows.map(function (r) { var gg = r.gg, p = r.per, u = gg ? gg.ups : 0; return [r.d.brand, r.d.size, r.d.pages || "", rulName(r.d.ruling), p || "", u || "", q(r.pending, p), q(r.fg, p), q(r.need, p), gg ? q(r.ins * u, p) : "", gg ? q(r.cov * u, p) : "", gg ? q(r.fld * u, p) : "", gg ? q(r.short, p) : "", r.pending, r.fg, r.need, gg ? r.ins : "", gg ? r.cov : "", gg ? r.fld : "", gg ? r.short : "", gg ? r.sheets : "", r.ctn == null ? "" : r.ctn, r.ctnNeed == null ? "" : r.ctnNeed]; }));
      };
    });
    paint();
  }

  /* ---------- Production: what each process made, by date and by item (Tanuj, 05/11/2026) ----------
     Read-only, from submitted Stock Entries, so undone (cancelled) entries drop out by themselves.
     Counted: COV-/FLD- Material Receipts and INS- Repacks into Stores, book Manufactures into Finished Goods.
     Left out: opening stock and opening fold counts, and book stock-ins for goods already delivered. */
  var PROCS = [["cov", "Covers printed", "sheets"], ["fld", "Folds", "folds"], ["ins", "Inserts bound", "inserts"], ["pack", "Packed", "books"]];
  var PC = {}, PCat = {}, PCerr = {};   // week start -> classified rows, when read, read failed
  function clearProduction() { PC = {}; PCat = {}; PCerr = {}; }
  var PV = { week: "", day: "", brand: "", size: "", pages: "", ruling: "" };
  function parseIso(v) { var m = v.split("-"); return new Date(+m[0], +m[1] - 1, +m[2]); }
  function addDays(v, n) { var d = parseIso(v); d.setDate(d.getDate() + n); return iso(d); }
  function mondayOf(v) { return addDays(v, -((parseIso(v).getDay() + 6) % 7)); }
  function weekDays(w) { return [0, 1, 2, 3, 4, 5, 6].map(function (n) { return addDays(w, n); }); }
  function dayName(v) { return ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][parseIso(v).getDay()]; }
  function classify(r) {
    if (/opening/i.test(r.remarks || "")) return null;
    var code = r.item_code || "", proc = null, brand, size, pages, ruling, m;
    if ((m = /^(COV|FLD|INS)-(PNC|SWR)-(A4|A5)-(\d{3})PG-([A-Z0-9]+)$/.exec(code))) {
      if (r.t_warehouse !== STORES || r.stock_entry_type !== (m[1] === "INS" ? "Repack" : "Material Receipt")) return null;
      proc = m[1].toLowerCase(); brand = m[2]; size = m[3]; pages = +m[4]; ruling = m[5];
    } else if ((m = /^(PNC|SWR)EB-(A4|A5)-(\d+)PGS-[A-Z]+-[A-Z]+-([A-Z0-9]+)$/.exec(code))) {
      if (r.t_warehouse !== FG || r.stock_entry_type !== "Manufacture") return null;
      proc = "pack"; brand = m[1]; size = m[2]; pages = +m[3]; ruling = m[4];
    } else return null;
    brand = brand === "PNC" ? "Prince" : "Swara";
    var k = brand + "|" + size + "|" + pages + "|" + ruling, gg = D.groups[k], ups = gg ? gg.ups : (size === "A4" ? 2 : 3), per = gg ? gcpc(gg) : 0, q = Number(r.qty) || 0;
    return { date: String(r.posting_date).slice(0, 10), proc: proc, k: k, brand: brand, size: size, pages: pages, ruling: ruling, code: code, se: r.name, at: r.creation, by: r.owner, run: (/Capture v3 · run ([^·]+?) ·/.exec(r.remarks || "") || [])[1] || "", qty: q, books: proc === "pack" ? q : q * ups, per: per };
  }
  function loadWeek(w) {
    var T = "`tabStock Entry Detail`.";
    return list("Stock Entry", ["name", "stock_entry_type", "posting_date", "remarks", "owner", "creation", T + "item_code as item_code", T + "qty as qty", T + "t_warehouse as t_warehouse"],
      [["docstatus", "=", 1], ["posting_date", "between", [w, addDays(w, 6)]], ["stock_entry_type", "in", ["Material Receipt", "Repack", "Manufacture"]], ["Stock Entry Detail", "t_warehouse", "in", [STORES, FG]]])
      .then(function (rows) { PC[w] = rows.map(classify).filter(Boolean); PCat[w] = Date.now(); delete PCerr[w]; });
  }
  function sum(rows) { var t = { q: 0, b: 0, c: 0 }; rows.forEach(function (r) { t.q += r.qty; t.b += r.books; if (r.per) t.c += r.books / r.per; }); return t; }
  /* Cartons big, the process's own unit small. Without a Carton unit: books big. */
  function pcell(rows, unit) {
    if (!rows.length) return '<span class="dash">-</span>';
    var t = sum(rows);
    return t.c ? '<b class="ct">' + c1(t.c) + " <span>ctn</span></b><small>" + f(t.q) + " " + unit + "</small>" : '<b class="ct">' + f(t.b) + " <span>books</span></b><small>no carton unit</small>";
  }
  function pMatrix(rows, w, pickable) {
    var days = weekDays(w), now = todayIso();
    return '<div class="tw"><table class="pm"><thead><tr><th>Process</th>' + days.map(function (d) {
      var t = dayName(d) + '<span class="dd">' + dmy(d).slice(0, 5) + "</span>";
      return '<th class="num' + (d === now ? " now" : "") + '">' + (pickable ? '<button type="button" class="pm-day" data-day="' + d + '" aria-pressed="' + (PV.day === d) + '">' + t + "</button>" : t) + "</th>";
    }).join("") + '<th class="num tot">Week</th></tr></thead><tbody>' + PROCS.map(function (p) {
      var pr = rows.filter(function (r) { return r.proc === p[0]; });
      return '<tr><th scope="row">' + p[1] + "</th>" + days.map(function (d) { return '<td class="num' + (PV.day === d && pickable ? " sel" : "") + '">' + pcell(pr.filter(function (r) { return r.date === d; }), p[2]) + "</td>"; }).join("") + '<td class="num tot">' + pcell(pr, p[2]) + "</td></tr>";
    }).join("") + "</tbody></table></div>";
  }
  function pAmount(t) { return t.c ? c1(t.c) + " ctn" : f(t.b) + " books"; }
  /* One card per process: week total, today, and a seven-day trend. */
  function pCards(rows, w, thisWeek) {
    var days = weekDays(w), now = todayIso();
    return '<div class="pk-row">' + PROCS.map(function (p) {
      var pr = rows.filter(function (r) { return r.proc === p[0]; }), t = sum(pr);
      var byDay = days.map(function (d) { return sum(pr.filter(function (r) { return r.date === d; })); });
      var top = Math.max.apply(null, byDay.map(function (x) { return x.c || x.b; }));
      var key = '<span class="n"><i class="k-' + p[0] + '"></i>' + p[1] + "</span>";
      if (!pr.length) return '<div class="pk">' + key + '<span class="v none">None yet</span><span class="s">No entries this week</span></div>';
      var td = sum(pr.filter(function (r) { return r.date === now; }));
      return '<div class="pk">' + key + '<span class="v">' + (p[0] !== "pack" && t.q ? f(t.q) + " <small>" + p[2] + "</small>" : t.c ? c1(t.c) + " <small>ctn</small>" : f(t.b) + " <small>books</small>") + '</span><span class="s">' + (p[0] !== "pack" && t.c ? "about " + c1(t.c) + " ctn" : f(t.q) + " " + p[2]) + (thisWeek ? " · today " + (td.q ? f(td.q) + " " + p[2] : "none") : "") + "</span>" +
        '<div class="pk-sp" aria-hidden="true">' + byDay.map(function (x) { var v = x.c || x.b; return '<i class="' + (v ? "k-" + p[0] : "z") + '" style="height:' + (v ? Math.max(8, v / top * 100).toFixed(1) : 0) + '%"></i>'; }).join("") + "</div></div>";
    }).join("") + "</div>";
  }
  function niceMax(v) { var e = Math.pow(10, Math.floor(Math.log(v) / Math.LN10)), m = v / e, n = [1, 2, 4, 6, 8, 10].filter(function (x) { return m <= x; })[0]; return n * e; }
  /* Columns per day on one carton axis. The day is the button; a table view sits behind the Table switch. */
  function pChart(rows, w) {
    var days = weekDays(w), now = todayIso();
    var data = days.map(function (d) { return PROCS.map(function (p) { return sum(rows.filter(function (r) { return r.date === d && r.proc === p[0]; })).c; }); });
    var top = Math.max.apply(null, data.map(function (v) { return Math.max.apply(null, v); }));
    var leg = '<div class="pc-leg">' + PROCS.map(function (p, i) { var any = data.some(function (v) { return v[i] > 0; }); return '<span class="' + (any ? "" : "off") + '"><i class="k-' + p[0] + '"></i>' + p[1] + (any ? "" : " · none") + "</span>"; }).join("") + "</div>";
    if (!top) return leg + '<p class="cap-note pe">Nothing recorded this week.</p>';
    var max = niceMax(top), live = PROCS.map(function (p, i) { return data.some(function (v) { return v[i] > 0; }) ? i : -1; }).filter(function (i) { return i >= 0; });
    var ticks = [0, 1, 2, 3, 4].map(function (n) { return '<span style="bottom:' + n * 25 + '%"><b>' + f(max * n / 4) + "</b></span>"; }).join("");
    return leg + '<div class="pc"><div class="pc-grid" aria-hidden="true">' + ticks + '</div><div class="pc-days">' + days.map(function (d, di) {
      var v = data[di], big = Math.max.apply(null, v);
      var said = dayName(d) + " " + dmy(d).slice(0, 5) + ": " + (big ? PROCS.map(function (p, i) { return v[i] ? p[1] + " " + c1(v[i]) + " cartons" : ""; }).filter(Boolean).join(", ") : "nothing recorded");
      return '<button type="button" class="pc-day' + (d === now ? " now" : "") + '" data-day="' + d + '" data-i="' + di + '" aria-pressed="' + (PV.day === d) + '" aria-label="' + esc(said) + '"><span class="pc-bars">' +
        live.map(function (i) { return '<i class="' + (v[i] ? "k-" + PROCS[i][0] : "e") + '" style="height:' + (v[i] / max * 100).toFixed(2) + '%">' + (v[i] && v[i] === big ? '<b class="pc-v">' + f(v[i]) + "</b>" : "") + "</i>"; }).join("") +
        '</span><span class="pc-x">' + dayName(d) + "<small>" + dmy(d).slice(0, 5) + "</small></span></button>";
    }).join("") + '</div><div class="pc-tip" id="p-tip" hidden></div></div><p class="pc-unit">Carton equivalents per day</p>';
  }
  function pChartWire(rows, w) {
    var tip = $("p-tip"); if (!tip) return;
    var days = weekDays(w);
    function hide() { tip.hidden = true; }
    [].forEach.call(document.querySelectorAll(".pc-day"), function (b) {
      function show() {
        var d = days[+b.dataset.i]; tip.textContent = "";
        var h = document.createElement("div"); h.className = "t"; h.textContent = dayName(d) + " " + dmy(d); tip.appendChild(h);
        var any = false;
        PROCS.forEach(function (p) {
          var pr = rows.filter(function (r) { return r.date === d && r.proc === p[0]; }); if (!pr.length) return;
          any = true; var t = sum(pr), row = document.createElement("div"), k = document.createElement("i"), v = document.createElement("b"), l = document.createElement("span");
          row.className = "r"; k.className = "k-" + p[0]; v.textContent = pAmount(t); l.textContent = p[1] + " · " + f(t.q) + " " + p[2];
          row.appendChild(k); row.appendChild(v); row.appendChild(l); tip.appendChild(row);
        });
        if (!any) { var e = document.createElement("div"); e.textContent = "Nothing recorded"; tip.appendChild(e); }
        tip.hidden = false;
        var box = tip.parentNode.clientWidth, x = b.offsetLeft + b.offsetWidth / 2 - tip.offsetWidth / 2;
        tip.style.left = Math.max(0, Math.min(box - tip.offsetWidth, x)) + "px";
      }
      b.addEventListener("pointerenter", show); b.addEventListener("focus", show);
      b.addEventListener("pointerleave", hide); b.addEventListener("blur", hide);
    });
  }
  function renderProduction() {
    if (!PV.mode) PV.mode = lsGet("p.mode", "chart");
    if (!PV.week) PV.week = mondayOf(todayIso());
    var w = PV.week;
    if (!PC[w]) {
      $("v3-app").innerHTML = '<div class="loading">Loading production from ERPNext…</div>';
      loadWeek(w).then(function () { if (S.view === "production" && PV.week === w) renderProduction(); })
        .catch(function (err) { $("v3-app").innerHTML = '<div class="cap-msg bad">Could not load production: ' + esc(err.message) + "</div>"; });
      return;
    }
    var G = Object.keys(D.groups).map(function (k) { return D.groups[k]; });
    var rows = PC[w].filter(function (r) { return (!PV.brand || r.brand === PV.brand) && (!PV.size || r.size === PV.size) && (!PV.pages || String(r.pages) === PV.pages) && (!PV.ruling || r.ruling === PV.ruling); });
    var shown = PV.day ? rows.filter(function (r) { return r.date === PV.day; }) : rows, byK = {};
    shown.forEach(function (r) { (byK[r.k] = byK[r.k] || []).push(r); });
    var keys = Object.keys(byK).sort(function (a, b) { return sum(byK[b]).b - sum(byK[a]).b || a.localeCompare(b); });
    var thisWeek = w === mondayOf(todayIso()), span = dmy(w) + " to " + dmy(addDays(w, 6));
    var h = '<div class="cap-top"><div class="pw"><span class="lb">Week</span><div class="seg" role="group" aria-label="Choose week"><button type="button" id="p-prev" aria-label="Previous week">‹</button><button type="button" id="p-now" aria-pressed="' + thisWeek + '">This week</button><button type="button" id="p-next" aria-label="Next week"' + (thisWeek ? " disabled" : "") + ">›</button></div></div>" +
      sel("p-brand", "Brand", PV.brand, uniq(G.map(function (x) { return x.brand; })).sort()) + sel("p-size", "Size", PV.size, uniq(G.map(function (x) { return x.size; })).sort()) +
      sel("p-pages", "Pages", PV.pages, uniq(G.map(function (x) { return x.pages; })).sort(function (a, b) { return a - b; })) +
      sel("p-ruling", "Ruling", PV.ruling, uniq(G.map(function (x) { return x.ruling; })).sort().map(function (r) { return [r, rulName(r)]; })) + "</div>" + pCards(rows, w, thisWeek) +
      '<div class="cap-card os-card"><div class="cap-h"><div><h3>By date</h3><span class="cap-note">' + span + (rows.length ? " · tap a day to see its items" : "") + '</span></div><div class="os-act btn-grp"><div class="seg" role="group" aria-label="Chart or table"><button type="button" data-mode="chart" aria-pressed="' + (PV.mode !== "table") + '">Chart</button><button type="button" data-mode="table" aria-pressed="' + (PV.mode === "table") + '">Table</button></div><button type="button" class="cap-sec" id="p-xlsx">Download Excel</button><button type="button" class="cap-sec" id="p-pdf">Print / PDF</button><button type="button" class="cap-sec" id="p-reload">Reload</button></div></div>' + (PV.mode === "table" ? pMatrix(rows, w, true) : pChart(rows, w)) + "</div>" +
      '<div class="cap-card os-card"><div class="cap-h"><div><h3>By item' + (PV.day ? " · " + dayName(PV.day) + " " + dmy(PV.day) : "") + '</h3><span class="cap-note">' + keys.length + " book types · most made first" + (keys.length ? " · tap a row for its days" : "") + "</span></div>" + (PV.day ? '<button type="button" class="cap-sec" id="p-all">Show whole week</button>' : "") + "</div>" +
      (keys.length ? '<div class="tw"><table class="osl pi"><thead><tr><th>Book type</th>' + PROCS.map(function (p) { return '<th class="num">' + p[1] + "</th>"; }).join("") + '<th><span class="vh">Details</span></th></tr></thead><tbody>' +
        keys.map(function (k, i) {
          var a = byK[k], r0 = a[0], gg = D.groups[k], name = r0.brand + " " + r0.size + " · " + r0.pages + " pages";
          return '<tr class="osr"><th scope="row"><b class="bdot" data-b="' + esc(String(name).split(" ")[0]) + '">' + esc(name) + '</b><span class="sub">' + esc(rulName(r0.ruling)) + " · " + (r0.per ? r0.per + " books/ctn" : "no Carton unit") + (gg ? " · " + gg.ups + "-up" : "") + "</span></th>" +
            PROCS.map(function (p) { return '<td class="num" data-l="' + p[1] + '">' + pcell(a.filter(function (r) { return r.proc === p[0]; }), p[2]) + "</td>"; }).join("") +
            '<td class="tg"><button type="button" class="os-tog" data-det="' + i + '" aria-expanded="false" aria-controls="p-det-' + i + '" aria-label="Days for ' + esc(name) + '"></button></td></tr>' +
            '<tr class="det" id="p-det-' + i + '" hidden><td colspan="6">' + pMatrix(rows.filter(function (r) { return r.k === k; }), w, false) + "</td></tr>";
        }).join("") + "</tbody></table></div>" : '<p class="cap-note pe">Nothing recorded ' + (PV.day ? "on this day." : "this week.") + "</p>") + "</div>" +
      '<details class="os-how"><summary>What is counted</summary><p>Submitted Stock Entries by posting date: covers and folds received into Stores - VCL, inserts repacked in Stores - VCL, and books manufactured into Finished Goods - VCL. Opening stock, opening fold counts and book stock-ins for goods already delivered are left out, and undone entries drop out. Cartons here are equivalents: sheets, folds or inserts × 2 for A4 or 3 for A5, ÷ books per carton. Weeks run Monday to Sunday.</p></details>';
    $("v3-app").innerHTML = '<div class="cap">' + h + "</div>";
    function go(week) { PV.week = week; PV.day = ""; renderProduction(); }
    $("p-prev").onclick = function () { go(addDays(w, -7)); };
    $("p-next").onclick = function () { if (!thisWeek) go(addDays(w, 7)); };
    $("p-now").onclick = function () { go(mondayOf(todayIso())); };
    ["brand", "size", "pages", "ruling"].forEach(function (k) { $("p-" + k).onchange = function (e) { PV[k] = e.target.value; renderProduction(); }; });
    if ($("p-all")) $("p-all").onclick = function () { PV.day = ""; renderProduction(); };
    $("p-pdf").onclick = function () { window.print(); };
    [].forEach.call($("v3-app").querySelectorAll("[data-mode]"), function (b) { b.onclick = function () { PV.mode = b.dataset.mode; lsSet("p.mode", PV.mode); renderProduction(); }; });
    pChartWire(rows, w);
    $("p-reload").onclick = function () { delete PC[w]; renderProduction(); };
    $("p-xlsx").onclick = function () {
      var names = {}; PROCS.forEach(function (p) { names[p[0]] = p; });
      download("EB production " + (PV.day || w), ["Date", "Process", "Item", "Brand", "Size", "Pages", "Ruling", "Quantity", "Unit", "Books", "Cartons", "Stock Entry"],
        shown.slice().sort(function (a, b) { return a.date.localeCompare(b.date) || a.code.localeCompare(b.code); }).map(function (r) { return [r.date, names[r.proc][1], r.code, r.brand, r.size, r.pages, rulName(r.ruling), r.qty, names[r.proc][2], r.books, r.per ? Math.round(r.books / r.per * 10) / 10 : "", r.se]; }));
    };
    var app = $("v3-app");
    [].forEach.call(app.querySelectorAll("[data-day]"), function (b) { b.onclick = function () { PV.day = PV.day === b.dataset.day ? "" : b.dataset.day; renderProduction(); }; });
    [].forEach.call(app.querySelectorAll("[data-det]"), function (b) { b.onclick = function () { var row = $("p-det-" + b.dataset.det), op = row.hidden; row.hidden = !op; b.setAttribute("aria-expanded", String(op)); }; });
    [].forEach.call(app.querySelectorAll("tr.osr"), function (t) { t.onclick = function (e) { if (!e.target.closest("button")) t.querySelector("[data-det]").click(); }; });
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

  /* ---------- Priority (Tanuj, 05/11/2026): production decision, kept off the Sales Order ----------
   * One VCL EB Priority row per order (key = SO) and per book type (key = SO::item). No row = Normal.
   * Rank: urgent orders first, then earliest due date. Within an order: urgent book types first. */
  var PR = null, PRerr = "", PRbusy = false, PRmsg = "", PRopen = {};
  var PRDT = "VCL EB Priority";
  function prKey(so, code) { return code ? so + "::" + code : so; }
  function prVal(so, code) { var r = PR[prKey(so, code)]; return r && r.priority === "Urgent" ? "Urgent" : "Normal"; }
  function prDate(v) { return dmy(String(v || "").slice(0, 10)).replace(/-/g, "/"); }
  function loadPriority() {
    return list(PRDT, ["name", "priority", "modified", "modified_by"], []).then(function (rows) {
      PR = {}; PRerr = ""; rows.forEach(function (r) { PR[r.name] = r; });
    }).catch(function (err) { PR = {}; PRerr = err.message || "Could not read priorities."; });
  }
  function prRank() {
    var by = {};
    O.lines.filter(isOpen).forEach(function (l) {
      var o = by[l.so] = by[l.so] || { so: l.so, customer: l.customer, due: l.due, books: 0, ctn: 0, noCtn: false, lines: {} };
      if (String(l.due || "9") < String(o.due || "9")) o.due = l.due;
      o.books += l.pending; if (l.per) o.ctn += l.pending / l.per; else o.noCtn = true;
      var b = o.lines[l.code] = o.lines[l.code] || { code: l.code, name: l.name, d: l.d, due: l.due, books: 0, ctn: 0, per: l.per };
      if (String(l.due || "9") < String(b.due || "9")) b.due = l.due;
      b.books += l.pending; if (l.per) b.ctn += l.pending / l.per;
    });
    var up = function (v) { return v === "Urgent" ? 0 : 1; };
    return Object.keys(by).map(function (k) {
      var o = by[k];
      o.list = Object.keys(o.lines).map(function (c) { return o.lines[c]; }).sort(function (a, b) {
        return up(prVal(o.so, a.code)) - up(prVal(o.so, b.code)) || String(a.due || "9").localeCompare(String(b.due || "9")) || b.books - a.books;
      });
      return o;
    }).sort(function (a, b) {
      return up(prVal(a.so)) - up(prVal(b.so)) || String(a.due || "9").localeCompare(String(b.due || "9")) || a.so.localeCompare(b.so);
    });
  }
  function prSeg(so, code, label) {
    var v = prVal(so, code);
    return '<div class="seg pr-seg" role="group" aria-label="Priority for ' + esc(label) + '">' + ["Normal", "Urgent"].map(function (x) {
      return '<button type="button" data-so="' + esc(so) + '" data-code="' + esc(code || "") + '" data-v="' + x + '" aria-pressed="' + (v === x) + '"' + (PRbusy ? " disabled" : "") + ">" + x + "</button>";
    }).join("") + "</div>";
  }
  function prWho(so, code) {
    var r = PR[prKey(so, code)];
    if (!r || r.priority !== "Urgent") return "";
    return '<small class="pr-who">Set by ' + esc(String(r.modified_by || "").split("@")[0]) + " on " + esc(prDate(r.modified)) + "</small>";
  }
  function prQty(x) { return x.ctn ? c1(x.ctn) + " ctn · " + f(x.books) + " books" : f(x.books) + " books"; }
  function prSave(so, code, val) {
    if (PRbusy || prVal(so, code) === val) return;
    var k = prKey(so, code), row = PR[k];
    PRbusy = true; PRmsg = ""; renderPriority();
    var doc = { doctype: PRDT, key: k, sales_order: so, priority: val };
    if (code) doc.item_code = code;
    (row ? post("frappe.client.set_value", { doctype: PRDT, name: k, fieldname: "priority", value: val }) : post("frappe.client.insert", { doc: doc }))
      .then(function () { return loadPriority(); })
      .catch(function (err) { PRmsg = "Not saved: " + (err.message || "the change was refused") + ". Only the priority setter can change this."; })
      .then(function () { PRbusy = false; if (S.view === "priority") renderPriority(); });
  }
  function renderPriority() {
    if (!PR) {
      $("v3-app").innerHTML = '<div class="loading">Loading priorities…</div>';
      loadPriority().then(function () { if (S.view === "priority") renderPriority(); });
      return;
    }
    var rows = prRank(), today = todayIso();
    var urgent = rows.filter(function (o) { return prVal(o.so) === "Urgent"; }).length;
    var h = '<div class="cap-card pr-top"><div class="pr-head"><div><b>' + rows.length + " open orders · " + urgent + " urgent</b>" +
      "<p>Urgent orders come first, then the earliest due date. Within an order, urgent book types come first. This is for production only: the Sales Order is not changed.</p></div>" +
      '<button type="button" class="cap-sec" id="pr-reload">Reload</button></div></div>';
    if (PRerr) h += '<div class="cap-msg bad">Could not read priorities: ' + esc(PRerr) + "</div>";
    if (PRmsg) h += '<div class="cap-msg bad" role="alert">' + esc(PRmsg) + "</div>";
    if (!rows.length) h += '<div class="cap-card"><p class="pr-empty">No open exercise book orders.</p></div>';
    rows.forEach(function (o, i) {
      var late = o.due && String(o.due) < today, open = !!PRopen[o.so], urg = prVal(o.so) === "Urgent";
      h += '<div class="cap-card pr-order' + (urg ? " urgent" : "") + '"><div class="pr-row"><span class="pr-n">' + (i + 1) + '</span><div class="pr-main"><b>' + esc(o.customer) + "</b>" +
        '<small><a href="/app/sales-order/' + encodeURIComponent(o.so) + '" target="_blank" rel="noopener">' + esc(o.so) + "</a> · due " + (o.due ? esc(prDate(o.due)) : "not set") + (late ? ' <span class="chip low">Late</span>' : "") + "</small>" +
        "<small>" + prQty(o) + "</small>" + prWho(o.so) + "</div>" + prSeg(o.so, "", o.so) + "</div>" +
        '<button type="button" class="pr-tog" data-tog="' + esc(o.so) + '" aria-expanded="' + open + '">' + (open ? "Hide" : "Show") + " " + o.list.length + (o.list.length === 1 ? " book type" : " book types") + "</button>";
      if (open) h += '<div class="pr-books">' + o.list.map(function (b) {
        return '<div class="pr-row pr-book"><div class="pr-main"><b class="bdot" data-b="' + esc(wiBrand(b.code)) + '">' + esc(b.name || b.code) + "</b><small>" + prQty(b) + (b.due && b.due !== o.due ? " · due " + esc(prDate(b.due)) : "") + "</small>" + prWho(o.so, b.code) + "</div>" + prSeg(o.so, b.code, b.name || b.code) + "</div>";
      }).join("") + "</div>";
      h += "</div>";
    });
    $("v3-app").innerHTML = h;
    [].forEach.call($("v3-app").querySelectorAll(".pr-seg button"), function (b) { b.onclick = function () { prSave(b.dataset.so, b.dataset.code, b.dataset.v); }; });
    [].forEach.call($("v3-app").querySelectorAll("[data-tog]"), function (b) { b.onclick = function () { PRopen[b.dataset.tog] = !PRopen[b.dataset.tog]; renderPriority(); }; });
    $("pr-reload").onclick = function () { O = null; PR = null; PRmsg = ""; showView("priority"); };
  }

  /* ---------- What-if (Tanuj, 05/11/2026): pick orders, set the order, see who is met and who waits ----------
   * Read-only unless "Mark as Urgent" is pressed. Stock is walked in the chosen order, book type by book type:
   * 1 finished books of the EXACT item; 2 insert sets; 3 cover sheets paired with folds; the rest is short.
   * Sets and sheets are shared by brand/size/pages/ruling and make `ups` books each. No dates: those need hours. */
  var WI = { sel: [], others: false, open: {}, q: "", msg: "", busy: false, by: "order", openB: {} };
  var WISTAGES = [["fg", "Finished"], ["ins", "Inserts"], ["cf", "Covers + folds"], ["short", "Short"]];
  function wiPools() {
    return { fg: {}, g: {}, take: function (o, k, need) { var n = Math.min(need, Math.max(0, o[k] || 0)); o[k] = (o[k] || 0) - n; return n; } };
  }
  function wiGroup(p, d) {
    var gk = d.brand + "|" + d.size + "|" + d.pages + "|" + d.ruling, gg = D && D.groups[gk];
    if (!gg) return null;
    if (!p.g[gk]) {
      var u = gg.ups, cov = D.bin[gg.cov + "|" + STORES] || 0, fld = D.bin[gg.fld + "|" + STORES] || 0;
      p.g[gk] = { ins: (D.bin[gg.ins + "|" + STORES] || 0) * u, cf: Math.min(cov, fld) * u, cov: cov, fld: fld };
    }
    return p.g[gk];
  }
  function wiBook(p, l) {
    var r = { code: l.code, name: l.name, need: l.books, per: l.per, fg: 0, ins: 0, cf: 0, short: 0, none: 0, noFold: false };
    var c = l.code; if (!(c in p.fg)) p.fg[c] = D.bin[c + "|" + FG] || 0;
    var left = l.books; r.fg = p.take(p.fg, c, left); left -= r.fg;
    var g = wiGroup(p, l.d);
    if (!g) { r.none = left; return r; }
    r.ins = p.take(g, "ins", left); left -= r.ins;
    r.cf = p.take(g, "cf", left); left -= r.cf;
    r.short = left; r.noFold = left > 0 && g.cov > 0 && g.fld === 0;
    return r;
  }
  function wiOrders() { var m = {}; prRank().forEach(function (o) { m[o.so] = o; }); return m; }
  function wiRun(list) {
    var p = wiPools();
    return list.map(function (o) {
      var res = { so: o.so, customer: o.customer, due: o.due, books: [], need: 0, fg: 0, ins: 0, cf: 0, short: 0, none: 0, ctn: {}, noFold: false };
      o.list.forEach(function (b) {
        var r = wiBook(p, { code: b.code, name: b.name, books: b.books, per: b.per, d: b.d });
        r.so = o.so; r.customer = o.customer; r.due = o.due;
        res.books.push(r); res.need += r.need; res.noFold = res.noFold || r.noFold;
        ["fg", "ins", "cf", "short", "none"].forEach(function (k) { res[k] += r[k]; if (r.per) res.ctn[k] = (res.ctn[k] || 0) + r[k] / r.per; });
      });
      res.missing = res.short + res.none;
      return res;
    });
  }
  function wiBar(r) {
    var parts = [["fg", r.fg], ["ins", r.ins], ["cf", r.cf], ["short", r.short], ["none", r.none]].filter(function (x) { return x[1] > 0; });
    var name = { fg: "Finished", ins: "Inserts", cf: "Covers + folds", short: "Short", none: "Not tracked" };
    var say = parts.map(function (x) { return name[x[0]] + " " + f(x[1]) + " books"; }).join(", ");
    return '<div class="wi-bar" role="img" aria-label="' + esc(say) + '">' + parts.map(function (x) {
      return '<span class="' + x[0] + '" style="flex:' + x[1] + ' 1 0" title="' + esc(name[x[0]] + ": " + f(x[1]) + " books (" + Math.round(x[1] / (r.need || 1) * 100) + "%)") + '"></span>';
    }).join("") + "</div>";
  }
  function wiState(r) {
    if (!r.missing) return '<span class="chip ok">Can be met</span>';
    if (r.missing === r.need) return '<span class="chip low">Nothing available</span>';
    return '<span class="chip low">' + Math.round(r.missing / r.need * 100) + "% short</span>";
  }
  function wiAmt(r, k) { var c = r.ctn && r.ctn[k]; return c ? c1(c) + " ctn" : f(r[k]) + " books"; }
  var WIUP = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5M6 11l6-6 6 6"/></svg>', WIDN = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M6 13l6 6 6-6"/></svg>', WIX = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';
  function wiToggle(so) { var i = WI.sel.indexOf(so); if (i >= 0) WI.sel.splice(i, 1); else WI.sel.push(so); renderWhatIf(); }
  function wiMark() {
    if (WI.busy || !WI.sel.length) return;
    WI.busy = true; WI.msg = ""; renderWhatIf();
    var todo = WI.sel.filter(function (so) { return prVal(so) !== "Urgent"; });
    todo.reduce(function (chain, so) {
      return chain.then(function () {
        return PR[so] ? post("frappe.client.set_value", { doctype: PRDT, name: so, fieldname: "priority", value: "Urgent" })
          : post("frappe.client.insert", { doc: { doctype: PRDT, key: so, sales_order: so, priority: "Urgent" } });
      });
    }, Promise.resolve()).then(loadPriority).then(function () { WI.msg = "ok:Marked as Urgent on the Priority tab."; })
      .catch(function (err) { WI.msg = "Not saved: " + (err.message || "the change was refused") + ". Only the priority setter can change this."; })
      .then(function () { WI.busy = false; if (S.view === "whatif") renderWhatIf(); });
  }
  function renderWhatIf() {
    if (!PR) {
      $("v3-app").innerHTML = '<div class="loading">Loading orders…</div>';
      loadPriority().then(function () { if (S.view === "whatif") renderWhatIf(); });
      return;
    }
    var ranked = prRank(), M = wiOrders(), q = WI.q.trim().toLowerCase();
    WI.sel = WI.sel.filter(function (so) { return M[so]; });
    var chosen = WI.sel.map(function (so) { return M[so]; });
    var rest = WI.others ? ranked.filter(function (o) { return WI.sel.indexOf(o.so) < 0; }) : [];
    var res = wiRun(chosen.concat(rest)), mine = res.slice(0, chosen.length), after = res.slice(chosen.length);
    var alone = {}; mine.forEach(function (r, i) { alone[r.so] = wiRun([chosen[i]])[0]; });
    var cust = {}; ranked.forEach(function (o) { (cust[o.customer] = cust[o.customer] || []).push(o); });
    var names = Object.keys(cust).sort().filter(function (c) { return !q || c.toLowerCase().indexOf(q) >= 0 || cust[c].some(function (o) { return o.so.toLowerCase().indexOf(q) >= 0; }); });
    var h = '<div class="wi-grid"><section class="cap-card wi-pick"><div class="cap-h"><h3>Choose customers or orders</h3></div>' +
      '<input type="search" id="wi-q" placeholder="Search customer or order" aria-label="Search customer or order" value="' + esc(WI.q) + '">' +
      '<div class="wi-list">' + names.map(function (c) {
        var os = cust[c], on = os.filter(function (o) { return WI.sel.indexOf(o.so) >= 0; }).length;
        var row = function (o, sub) {
          return '<label class="wi-opt' + (sub ? " sub" : "") + '"><input type="checkbox" data-so="' + esc(o.so) + '"' + (WI.sel.indexOf(o.so) >= 0 ? " checked" : "") + '><span><b>' + esc(sub ? o.so : c) + "</b><small>" + (sub ? "" : esc(o.so) + " · ") + "due " + (o.due ? esc(prDate(o.due)) : "not set") + " · " + prQty(o) + "</small></span></label>";
        };
        if (os.length === 1) return row(os[0], false);
        return '<label class="wi-opt"><input type="checkbox" data-cust="' + esc(c) + '"' + (on === os.length ? " checked" : "") + '><span><b>' + esc(c) + "</b><small>" + os.length + " orders</small></span></label>" + os.map(function (o) { return row(o, true); }).join("");
      }).join("") + (names.length ? "" : '<p class="wi-empty">No open orders match.</p>') + "</div>" +
      (WI.sel.length ? '<a class="wi-jump cap-post" href="#wi-res">' + WI.sel.length + (WI.sel.length === 1 ? " order" : " orders") + " selected · View results</a>" : "") + "</section>";
    h += '<section class="wi-out" id="wi-res">';
    if (!chosen.length) {
      h += '<div class="cap-card wi-start"><h3>Who can we serve?</h3><p>Tick the customers or orders you want to check. Stock goes to the first one, then the next, so you can see who is met and who waits. Nothing changes in ERPNext.</p></div>';
    } else {
      var met = mine.filter(function (r) { return !r.missing; }).length;
      h += '<div class="cap-card wi-sum"><div class="wi-head"><div><h3>' + met + " of " + mine.length + (mine.length === 1 ? " order" : " orders") + " can be met</h3><p>From what is made or part-made today. No dates: those come once hours are recorded.</p></div>" +
        '<div class="wi-ctl"><div class="seg" role="group" aria-label="Show by"><button type="button" data-by="order" aria-pressed="' + (WI.by === "order") + '">By order</button><button type="button" data-by="book" aria-pressed="' + (WI.by === "book") + '">By book type</button></div>' +
        '<label class="wi-sw"><input type="checkbox" id="wi-others"' + (WI.others ? " checked" : "") + "><span>Show everyone else after these</span></label></div></div>" +
        '<div class="wi-legend">' + WISTAGES.map(function (s) { return '<span><i class="' + s[0] + '"></i>' + s[1] + "</span>"; }).join("") + "</div></div>";
      if (WI.msg) h += '<div class="cap-msg ' + (WI.msg.indexOf("ok:") === 0 ? "ok" : "bad") + '" role="status">' + esc(WI.msg.replace(/^ok:/, "")) + "</div>";
      if (mine.some(function (r) { return r.noFold; })) h += '<div class="cap-msg warn">Cover sheets are in stock but no folds are recorded, so they count as short until the fold count is posted.</div>';
      if (WI.by === "book") h += '<div class="wi-sub"><h3>Book types across the ' + mine.length + ' chosen ' + (mine.length === 1 ? "order" : "orders") + ', biggest shortfall first</h3></div>' + wiByBook(mine);
      h += (WI.by === "book" ? [] : mine).map(function (r, i) {
        var lost = alone[r.so].missing < r.missing ? r.missing - alone[r.so].missing : 0, open = !!WI.open[r.so];
        return '<article class="cap-card wi-row"><div class="wi-top"><span class="wi-n">' + (i + 1) + '</span><div class="wi-who"><b>' + esc(r.customer) + "</b><small>" + esc(r.so) + " · due " + (r.due ? esc(prDate(r.due)) : "not set") + " · " + f(r.need) + " books</small></div>" + wiState(r) +
          '<div class="wi-move"><button type="button" data-up="' + i + '" aria-label="Serve ' + esc(r.customer) + ' earlier"' + (i ? "" : " disabled") + ">" + WIUP + '</button><button type="button" data-dn="' + i + '" aria-label="Serve ' + esc(r.customer) + ' later"' + (i < mine.length - 1 ? "" : " disabled") + ">" + WIDN + '</button><button type="button" data-rm="' + esc(r.so) + '" aria-label="Remove ' + esc(r.customer) + '">' + WIX + "</button></div></div>" + wiBar(r) +
          '<div class="wi-nums">' + [["fg", "Finished"], ["ins", "Inserts"], ["cf", "Covers + folds"], ["short", "Short"], ["none", "Not tracked"]].filter(function (s) { return r[s[0]] > 0; }).map(function (s) { return "<span>" + s[1] + " <b>" + wiAmt(r, s[0]) + "</b></span>"; }).join("") + "</div>" +
          (lost ? '<p class="wi-note">' + f(lost) + " books went to the orders above. Served first, it would be short " + f(alone[r.so].missing) + ".</p>" : "") +
          '<button type="button" class="pr-tog wi-tog" data-open="' + esc(r.so) + '" aria-expanded="' + open + '">' + (open ? "Hide" : "Show") + " " + r.books.length + (r.books.length === 1 ? " book type" : " book types") + "</button>" + (open ? wiTable(r) : "") + "</article>";
      }).join("");
      if (after.length) h += '<div class="wi-sub"><h3>Everyone else, in Priority order</h3></div>' + after.map(function (r) {
        return '<article class="cap-card wi-row quiet"><div class="wi-top"><div class="wi-who"><b>' + esc(r.customer) + "</b><small>" + esc(r.so) + " · due " + (r.due ? esc(prDate(r.due)) : "not set") + "</small></div>" + wiState(r) + "</div>" + wiBar(r) + "</article>";
      }).join("");
      h += '<div class="wi-act"><button type="button" class="cap-sec" id="wi-clear">Clear</button><button type="button" class="cap-sec" id="wi-mark"' + (WI.busy ? " disabled" : "") + ">Mark as Urgent</button></div>";
    }
    h += "</section></div>";
    var focusQ = document.activeElement && document.activeElement.id === "wi-q", pos = focusQ ? document.activeElement.selectionStart : 0;
    $("v3-app").innerHTML = h;
    var qi = $("wi-q"); qi.oninput = function () { WI.q = qi.value; renderWhatIf(); };
    if (focusQ) { qi.focus(); qi.setSelectionRange(pos, pos); }
    [].forEach.call($("v3-app").querySelectorAll("[data-so]"), function (b) { b.onchange = function () { wiToggle(b.dataset.so); }; });
    [].forEach.call($("v3-app").querySelectorAll("[data-cust]"), function (b) {
      b.onchange = function () {
        var os = cust[b.dataset.cust].map(function (o) { return o.so; });
        if (b.checked) os.forEach(function (so) { if (WI.sel.indexOf(so) < 0) WI.sel.push(so); }); else WI.sel = WI.sel.filter(function (so) { return os.indexOf(so) < 0; });
        renderWhatIf();
      };
    });
    var swap = function (a, b) { var t = WI.sel[a]; WI.sel[a] = WI.sel[b]; WI.sel[b] = t; renderWhatIf(); };
    [].forEach.call($("v3-app").querySelectorAll("[data-up]"), function (b) { b.onclick = function () { var i = +b.dataset.up; swap(i, i - 1); }; });
    [].forEach.call($("v3-app").querySelectorAll("[data-dn]"), function (b) { b.onclick = function () { var i = +b.dataset.dn; swap(i, i + 1); }; });
    [].forEach.call($("v3-app").querySelectorAll("[data-rm]"), function (b) { b.onclick = function () { wiToggle(b.dataset.rm); }; });
    [].forEach.call($("v3-app").querySelectorAll("[data-open]"), function (b) { b.onclick = function () { WI.open[b.dataset.open] = !WI.open[b.dataset.open]; renderWhatIf(); }; });
    var ot = $("wi-others"); if (ot) ot.onchange = function () { WI.others = ot.checked; renderWhatIf(); };
    [].forEach.call($("v3-app").querySelectorAll("[data-by]"), function (b) { b.onclick = function () { WI.by = b.dataset.by; renderWhatIf(); }; });
    [].forEach.call($("v3-app").querySelectorAll("[data-openb]"), function (b) { b.onclick = function () { WI.openB[b.dataset.openb] = !WI.openB[b.dataset.openb]; renderWhatIf(); }; });
    var cl = $("wi-clear"); if (cl) cl.onclick = function () { WI.sel = []; WI.msg = ""; renderWhatIf(); };
    var mk = $("wi-mark"); if (mk) mk.onclick = wiMark;
  }
  /* By book type: the same allocation, totalled per book across the chosen orders, biggest shortfall first. */
  function wiBrand(code) { return /^PNC/.test(code) ? "Prince" : /^SWR/.test(code) ? "Swara" : /hi5/i.test(code) ? "Hi5" : /^SCH-/.test(code) ? "School" : ""; }
  function wiByBook(res) {
    var by = {};
    res.forEach(function (o) {
      o.books.forEach(function (b) {
        var t = by[b.code] = by[b.code] || { code: b.code, name: b.name, per: b.per, need: 0, fg: 0, ins: 0, cf: 0, short: 0, none: 0, noFold: false, takers: [], ctn: {} };
        ["need", "fg", "ins", "cf", "short", "none"].forEach(function (k) { t[k] += b[k]; });
        t.noFold = t.noFold || b.noFold;
        t.takers.push({ so: b.so, customer: b.customer, due: b.due, need: b.need, got: b.fg + b.ins + b.cf, short: b.short + b.none });
      });
    });
    var rows = Object.keys(by).map(function (k) {
      var t = by[k]; t.missing = t.short + t.none;
      if (t.per) ["need", "fg", "ins", "cf", "short", "none"].forEach(function (x) { t.ctn[x] = t[x] / t.per; });
      return t;
    }).sort(function (a, b) { return b.missing - a.missing || b.need - a.need || a.name.localeCompare(b.name); });
    if (!rows.length) return "";
    return rows.map(function (t) {
      var open = !!WI.openB[t.code];
      return '<article class="cap-card wi-row wi-book"><div class="wi-top"><div class="wi-who"><b class="bdot" data-b="' + esc(wiBrand(t.code)) + '">' + esc(t.name || t.code) + "</b><small>" + (t.per ? c1(t.need / t.per) + " ctn · " : "") + f(t.need) + " books needed by " + t.takers.length + (t.takers.length === 1 ? " order" : " orders") + "</small></div>" + wiState(t) + "</div>" + wiBar(t) +
        '<div class="wi-nums">' + [["fg", "Finished"], ["ins", "Inserts"], ["cf", "Covers + folds"], ["short", "Short"], ["none", "Not tracked"]].filter(function (s) { return t[s[0]] > 0; }).map(function (s) { return "<span>" + s[1] + " <b>" + wiAmt(t, s[0]) + "</b></span>"; }).join("") + "</div>" +
        '<button type="button" class="pr-tog wi-tog" data-openb="' + esc(t.code) + '" aria-expanded="' + open + '">' + (open ? "Hide" : "Show") + " who takes it</button>" +
        (open ? '<div class="wi-tw"><table class="wi-t"><thead><tr><th>Order (served in this order)</th><th>Needs</th><th>Gets</th><th>Short</th></tr></thead><tbody>' + t.takers.map(function (x) {
          return "<tr><td>" + esc(x.customer) + " <small>" + esc(x.so) + (x.due ? " · due " + esc(prDate(x.due)) : "") + "</small></td><td>" + f(x.need) + "</td><td>" + (x.got ? f(x.got) : "-") + "</td><td>" + (x.short ? f(x.short) : "-") + "</td></tr>";
        }).join("") + "</tbody></table><small>Books</small></div>" : "") + "</article>";
    }).join("");
  }
  function wiTable(r) {
    return '<div class="wi-tw"><table class="wi-t"><thead><tr><th>Book type</th><th>Need</th><th>Finished</th><th>Inserts</th><th>Covers + folds</th><th>Short</th></tr></thead><tbody>' + r.books.map(function (b) {
      var z = function (n) { return n ? f(n) : "-"; };
      return "<tr><td>" + esc(b.name || b.code) + "</td><td>" + f(b.need) + "</td><td>" + z(b.fg) + "</td><td>" + z(b.ins) + "</td><td>" + z(b.cf) + "</td><td>" + (b.none ? f(b.none) + " not tracked" : z(b.short)) + "</td></tr>";
    }).join("") + "</tbody></table><small>Books</small></div>";
  }

  /* ---------- views: Capture | Orders | Order & stock ---------- */
  var VIEWS = [["capture", "Capture"], ["production", "Production"], ["orders", "Orders"], ["orderstock", "Order & stock"], ["priority", "Priority"], ["whatif", "What-if"]];
  function renderViews() {
    $("v3-mode").innerHTML = '<div class="seg views" role="tablist" aria-label="Screens">' + VIEWS.map(function (v) { return '<button type="button" role="tab" data-view="' + v[0] + '" aria-pressed="' + (S.view === v[0]) + '">' + v[1] + "</button>"; }).join("") + "</div>";
    [].forEach.call($("v3-mode").querySelectorAll("[data-view]"), function (b) { b.onclick = function () { showView(b.dataset.view); }; });
  }
  function showView(v) {
    S.view = v; lsSet("view", v);
    try { var u = new URL(location.href); u.searchParams.set("view", v); history.replaceState(null, "", u); } catch (e) {}
    renderViews();
    $("ebv3").dataset.view = v;
    $("v3-title").textContent = VIEWS.filter(function (x) { return x[0] === v; })[0][1];
    $("v3-banner").hidden = v !== "capture";
    if (v === "capture") { renderShell(); return; }
    if (v === "production") { renderProduction(); return; }
    var go = function () { if (S.view === v) (v === "orders" ? renderOrders : v === "priority" ? renderPriority : v === "whatif" ? renderWhatIf : renderOrderStock)(); };
    if (O) { go(); return; }
    $("v3-app").innerHTML = '<div class="loading">Loading exercise book orders…</div>';
    loadOrders().then(go).catch(function (err) { $("v3-app").innerHTML = '<div class="cap-msg bad">Could not load orders: ' + esc(err.message) + "</div>"; });
  }

  /* ---------- start ---------- */
  function start() {
    S.group = lsGet("group", null); S.chosen = false; S.station = lsGet("station", "covers"); S.run = lsGet("run", ""); S.date = todayIso(); S.shift = lsGet("shift", "Day Shift"); if (SHIFTS.indexOf(S.shift) < 0) S.shift = "Day Shift";
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
