// Run with node testing/test_eb_capture_preferences.cjs; no site or dependencies needed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const values = new Map();
const source = fs.readFileSync(path.join(__dirname, '../exercise-book-production/dev-page-v3/page.js'), 'utf8');
const startup = '  if (window.frappe && frappe.session && frappe.session.user === "Guest")';
assert(source.includes(startup));
const script = source.slice(0, source.indexOf(startup)) + `
  window.test = { S, MODE, todayIso, minIso, checkWhen, rememberDate, rememberedDate, referenceLabel, referenceText, wzOk, GUIDED, entryPayload,
    cleanFoldName, mergeFoldNames, foldNameFromEntry, saveFoldName, foldNames, resetEntry, loadFoldNames, FOLD_NAMES,
    loadSharedFoldNames, saveSharedFoldName, PICK_ORDER, pickBack, pickMatches, suggestedBooks, BOOK_HISTORY,
    setPicker: function(picker) { PK = picker; }, getPicker: function() { return PK; },
    planEntry, classify, groupKeys,
    setData: function(data) { D = data; } };
})();`;
let width = 820;
const context = {
  window: { addEventListener() {}, matchMedia: q => ({matches: width <= Number(q.match(/\d+/)[0])}) },
  localStorage: {getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, String(value))},
  document: {getElementById() { return null; }}, URL, console
};
vm.runInNewContext(script, context);
const t = context.window.test;
const today = t.todayIso();
t.S.station = 'folds'; t.S.run = 'Regina'; t.S.date = t.minIso();
assert.equal(t.referenceLabel(), 'Folded by');
assert.equal(t.referenceText(' Regina '), 'Folded by Regina');
assert.equal(t.wzOk(2), true);
t.rememberDate();
assert.equal(t.rememberedDate(), t.minIso(), 'valid back-date survives reload within the work day');
values.set('vcl.eb-v3.date.savedOn', '2000-01-01');
assert.equal(t.rememberedDate(), today, 'a previous work day starts with today');
values.set('vcl.eb-v3.date.savedOn', today);
values.set('vcl.eb-v3.date', '9999-12-31');
assert.equal(t.rememberedDate(), today, 'future saved dates are discarded');
t.S.date = '2000-01-01';
assert.equal(t.wzOk(2), false, 'out-of-range dates block Next');
t.S.date = today; t.S.run = '';
assert.equal(t.wzOk(2), false, 'folder is required');
t.S.run = 'Regina'; t.S.shift = 'Invalid';
assert.equal(t.wzOk(2), false, 'invalid shifts block Next');
t.S.shift = 'Day Shift'; t.S.station = 'covers';
t.MODE.machines = {covers: [{name:'Solna'}, {name:'Miller'}]};
assert.equal(t.referenceLabel(), 'Run or press');
assert.equal(t.wzOk(2), false, 'machine selection remains required');
values.set('vcl.eb-v3.machine.covers', 'Miller');
assert.equal(t.wzOk(2), true);
t.S.station = 'folds'; t.S.group = 'Swara|A4|120|SL'; t.S.v = {good:'50', rejects:'0'};
t.setData({groups: {[t.S.group]: {books:[]}}});
const payload = t.entryPayload({extra:{}}, 'Regina');
assert.equal(payload.run, 'Regina', 'folder is retained in the existing server reference field');
assert.equal(payload.confirmed, 2, 'posting retains both confirmations');
assert.equal(payload.inputs.good, '50');
assert.equal(t.GUIDED(), true);
width = 1180; assert.equal(t.GUIDED(), true);
width = 1366; assert.equal(t.GUIDED(), false, 'desktop keeps its existing full-page flow');
console.log('PASS: date persistence, date/shift/folder/machine validation, references, posting payload, tablet breakpoint');
assert.equal(t.cleanFoldName('  Mary   Ann  '), 'Mary Ann');
assert.equal(t.cleanFoldName('Regina · run another'), '', 'audit separators cannot enter a name');
assert.equal(t.cleanFoldName('x'.repeat(81)), '');
assert.equal(JSON.stringify(t.mergeFoldNames(['Regina', 'regina', ' Regina ', 'Alice'])), JSON.stringify(['Alice','Regina']));
const foldingRow = {docstatus:1, remarks:'Capture v3 · run Regina · confirmed twice by user at today · Station folds · Group Swara|A4|120|SL'};
assert.equal(t.foldNameFromEntry(foldingRow), 'Regina');
assert.equal(t.foldNameFromEntry({...foldingRow, remarks:foldingRow.remarks.replace('run Regina','run Mary - Night')}), 'Mary');
assert.equal(t.foldNameFromEntry({...foldingRow, remarks:foldingRow.remarks.replace('run Regina','run joyce')}), 'Joyce');
assert.equal(t.foldNameFromEntry({...foldingRow, remarks:foldingRow.remarks.replace('Station folds','Station covers')}), '', 'press references are excluded');
assert.equal(t.foldNameFromEntry({...foldingRow, docstatus:2}), '', 'cancelled stock entries are excluded');
assert.equal(t.foldNameFromEntry({...foldingRow, docstatus:0}), '', 'draft stock entries are excluded');
assert.equal(t.saveFoldName(' Alice '), 'Alice');
assert.equal(t.saveFoldName('alice'), 'Alice');
assert.equal(t.foldNames().filter(n=>n.toLowerCase()==='alice').length, 1);
const kept = {date:t.S.date, shift:t.S.shift, run:t.S.run, station:t.S.station};
t.S.chosen = true; t.S.book = 'selected-book'; t.S.log = [{name:'previous-entry'}];
t.resetEntry();
assert.equal(Object.keys(t.S.v).length, 0);
assert.equal(t.S.chosen, false); assert.equal(t.S.book, null);
for(const key of Object.keys(kept)) assert.equal(t.S[key],kept[key], 'New entry preserves '+key);
assert.equal(t.S.log.length, 1, 'New entry retains the posting log');
let historyCalls = [];
context.fetch = async url => {
  const u = new URL(url,'https://fixture.invalid');
  const offset = Number(u.searchParams.get('limit_start')); historyCalls.push(offset);
  return {ok:true,json:async()=>({message:offset===0 ? Array.from({length:500},()=>foldingRow) : [{...foldingRow,remarks:foldingRow.remarks.replace('run Regina','run Judith')}]})};
};
t.loadFoldNames().then(()=>{
  assert.equal(JSON.stringify(historyCalls), JSON.stringify([0,500]), 'history is paginated beyond the first page');
  assert(t.foldNames().includes('Judith')); assert(t.FOLD_NAMES.loaded);
  assert(JSON.parse(values.get('vcl.eb-v3.fold.names')).includes('Judith'), 'history is cached with added names');
  console.log('PASS: folding-history names, deduplication, paginated loading, and New entry reset');
}).catch(error=>{ console.error(error); process.exitCode=1; });

async function sharedNamesAndPicker() {
  const shared = [{folder_name:'Regina'}], writes = [];
  function client() {
    const cache = new Map();
    const env = {
      window:{addEventListener(){},matchMedia:()=>({matches:true})}, document:{getElementById:()=>null}, URL,
      localStorage:{getItem:key=>cache.get(key)??null,setItem:(key,value)=>cache.set(key,String(value))},
      fetch: async (url, options={}) => {
        if(options.method==='POST') {
          const payload=JSON.parse(options.body); writes.push(payload.doc.doctype);
          assert.equal(payload.doc.doctype,'VCL EB Folder','adding a name cannot create a stock entry');
          shared.push({folder_name:payload.doc.folder_name});
          return {ok:true,json:async()=>({message:shared.at(-1)})};
        }
        return {ok:true,json:async()=>({message:shared.slice()})};
      }
    };
    vm.runInNewContext(script,env); env.window.test.S.station='folds';
    return {api:env.window.test,env,cache};
  }
  const first=client(), second=client();
  assert.equal(await first.api.saveSharedFoldName('Joyce'),'Joyce');
  await second.api.loadSharedFoldNames(true);
  assert(second.api.foldNames().includes('Joyce'),'a separate iPad sees a name without any production posting');
  await second.api.saveSharedFoldName('joyce');
  assert.equal(writes.length,1,'existing case variants do not insert duplicate records');
  const failing=client();
  failing.env.fetch=async()=>{throw new Error('offline');};
  await assert.rejects(failing.api.saveSharedFoldName('Mary'),/unavailable/);
  assert(!failing.api.foldNames().includes('Mary'),'failed shared save is not reported as a local success');
  const p=first.api;
  const groups={};
  for(const [brand,size,pages,ruling] of [['Swara','A4',120,'SL'],['Swara','A4',96,'SL'],['Swara','A5',120,'SQ'],['Prince','A4',120,'SL']]) {
    const key=[brand,size,pages,ruling].join('|'); groups[key]={k:key,brand,size,pages,ruling,dem:0,books:[]};
  }
  p.setData({groups}); p.S.station='folds'; p.S.v={good:'20'};
  p.BOOK_HISTORY.byStation.folds=['Swara|A4|120|SL','Swara|A5|120|SQ','Prince|A4|120|SL'];
  assert.equal(JSON.stringify(p.PICK_ORDER),JSON.stringify(['brand','size','pages','ruling']));
  p.setPicker({brand:'Swara',size:'A4'});
  assert.equal(JSON.stringify(p.suggestedBooks()),JSON.stringify(['Swara|A4|120|SL']),'suggestions respect brand and size');
  p.setPicker({brand:'Swara',size:'A4',pages:120,ruling:'SL'}); p.pickBack('size');
  assert.equal(JSON.stringify(p.getPicker()),JSON.stringify({brand:'Swara'}),'changing size also clears pages and lines');
  assert.equal(p.S.v.good,'20','suggestion ranking itself does not modify quantities');
  console.log('PASS: names shared between separate clients, duplicate and offline saves, reordered picker and filtered suggestions');
}
sharedNamesAndPicker().catch(error=>{console.error(error);process.exitCode=1;});
const hi5key='Hi5|A4|120|SL';
t.S.station='packing'; t.S.group=hi5key; t.S.date=t.todayIso(); t.S.v={cartons:'2',weights:'10'};
t.setData({groups:{[hi5key]:{k:hi5key,brand:'Hi5',size:'A4',pages:120,ruling:'SL',ups:2,cov:'COV-HI5-A4-120PG-SL',fld:'FLD-HI5-A4-120PG-SL',ins:'INS-HI5-A4-120PG-SL',carton:null,books:[{code:'Hi5-A4-120PGS-CB-BP-SL',cpc:102}]}},
  cartons:{},bin:{'INS-HI5-A4-120PG-SL|Stores - VCL':1000}});
t.MODE.brands=['Prince','Swara'];
assert.equal(t.planEntry().ok,false,'old servers cannot offer Hi5 posting');
t.MODE.brands.push('Hi5');
const hi5Plan=t.planEntry();
assert.equal(hi5Plan.ok,true);
assert.equal(JSON.stringify(hi5Plan.rows.map(r=>[r.key,r.qty])),JSON.stringify([['ins',-102],['fg',204]]));
const classified=t.classify({item_code:'Hi5-A4-120PGS-CB-BP-SL',stock_entry_type:'Manufacture',t_warehouse:'Finished Goods - VCL',qty:204,posting_date:t.todayIso(),name:'fixture'});
assert.equal(classified.brand,'Hi5'); assert.equal(classified.proc,'pack'); assert.equal(classified.k,hi5key);
console.log('PASS: Hi5 preview, old-server guard, carton exclusion, and production classification');
