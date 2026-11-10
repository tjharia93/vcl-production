/* Isolated test: node SCRIPT [playwright-module-path] [screenshot-directory].
   Uses an installed Edge in headless mode; all URLs are intercepted, no ERPNext. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require(process.argv[2] || 'playwright');
const root = path.resolve(__dirname, '..');
const html = '<meta charset="utf-8">' + fs.readFileSync(path.join(root, 'production_log/www/cps_first_order_approval.html'), 'utf8').replace(/{%.*?%}/g, '');
const js = fs.readFileSync(path.join(root, 'production_log/public/js/cps_first_order_approval.js'), 'utf8');
const output = process.argv[3] || process.cwd();
const dataTemplate = {
  name: 'Invoice paper', cps: 'CPS-TEST', cps_status: 'Draft', sales_order: 'SO-TEST', customer: 'Test customer', version: 'v1',
  price: {status: 'Draft', rate: 3793.1034, currency: 'KES', uom: 'Carton', valid_from: '2026-11-10'},
  order_rate: 3793.1034, order_currency: 'KES', order_uom: 'Carton', packing_allowed: true, sets_per_carton: null, carton_tare: .3,
  changes: [], fields: [
    {label: 'Job size', type: 'Data', value: '9.5 x 11 in'},
    {label: 'Plain or printed', type: 'Data', value: 'Printed'},
    {label: 'Number of parts', type: 'Int', value: 3},
    {label: 'Paper parts', type: 'Table', value: ['White','Yellow','Pink'].map((colour,i) => [
      {label:'Part',value:i+1}, {label:'Paper',value:['CB','CFB','CF'][i]}, {label:'Colour',value:colour}])},
    {label: 'Notes', type: 'Data', value: '<img src=x onerror="window.hacked=true">'},
  ],
};
(async () => {
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  try {
    for (const width of [1440,390]) {
      const page = await browser.newPage({viewport:{width,height:900}});
      const data = structuredClone(dataTemplate), requests = [];
      let failure = '';
      await page.exposeFunction('mockCall', payload => {
        requests.push(payload);
        return failure ? {error:failure} : {message:payload.type === 'GET' ? data : {approved:true}};
      });
      const shim = '<script>window.frappe={ready(fn){document.addEventListener("DOMContentLoaded",fn)},call:async function(p){const r=await window.mockCall(p);if(r.error)throw new Error(r.error);return r;}};</script>';
      await page.route('https://cps-approval.test/**', route => route.fulfill({
        body: route.request().url().includes('/assets/') ? js : shim + html,
        contentType: route.request().url().includes('/assets/') ? 'application/javascript' : 'text/html',
      }));
      await page.goto('https://cps-approval.test/sales-crm-v2/approve-cps?sales_order=SO-TEST&cps=CPS-TEST');
      await page.locator('#cps-review-content').waitFor({state:'visible'});
      assert.deepEqual(requests.map(r=>r.type), ['GET']);
      assert.match(await page.locator('#cps-review-prices').innerText(), /Draft/);
      assert.equal(await page.locator('#cps-review-sets').inputValue(), '');
      assert.equal(await page.locator('#cps-review-tare').inputValue(), '0.3');
      assert.equal(await page.evaluate(()=>!!window.hacked), false);
      assert(await page.evaluate(()=>document.documentElement.scrollWidth <= window.innerWidth + 2));
      await page.screenshot({path:path.join(output,`cps-approval-${width}.png`),fullPage:true});
      await page.locator('#cps-review-sets').fill('500');
      await page.getByRole('button',{name:'Approve CPS + price',exact:true}).click();
      await page.getByRole('button',{name:'Approved',exact:true}).waitFor();
      assert.equal(requests.length,2);
      assert.equal(requests[1].type,'POST');
      assert.equal(requests[1].args.version,'v1');
      assert.equal(requests[1].args.sets_per_carton,'500');
      failure = 'The CPS changed. Reload and review.';
      await page.reload();
      await page.locator('#cps-review-error').waitFor({state:'visible'});
      assert(await page.locator('#cps-review-content').isHidden());
      failure = ''; data.packing_allowed = false;
      await page.reload();
      await page.locator('#cps-review-content').waitFor({state:'visible'});
      assert(await page.locator('#cps-review-packing').isHidden());
      failure = 'The price changed. Reload and review.';
      await page.getByRole('button',{name:'Approve CPS + price',exact:true}).click();
      await page.locator('#cps-review-error').waitFor({state:'visible'});
      assert(await page.getByRole('button',{name:'Approve CPS + price',exact:true}).isEnabled());
      assert(!('sets_per_carton' in requests.at(-1).args));
      await page.close();
      console.log(`Approval UI ${width}px: GET read-only; one POST; packing scope; stale/error handling; no XSS/overflow`);
    }
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
