/* Email opens review only. Approval requires an authenticated, CSRF-checked POST. */
frappe.ready(function () {
  const root = document.getElementById('cps-first-review');
  const find = id => root.querySelector('#cps-review-' + id);
  const query = new URLSearchParams(location.search);
  const args = {sales_order: query.get('sales_order'), cps: query.get('cps')};
  const method = 'production_log.job_card_tracking.cps_first_order_approval.';
  let review;
  function error(message) {
    find('error').textContent = message; find('error').hidden = false;
  }
  function field(label, value) {
    const box = document.createElement('div'); box.className = 'field';
    const name = document.createElement('div'); name.className = 'label'; name.textContent = label;
    const content = document.createElement('div'); content.textContent = value == null ? '—' : String(value);
    box.append(name, content); return box;
  }
  function render(fields, target) {
    fields.forEach(f => {
      if (f.type === 'Table' || f.type === 'Table MultiSelect') {
        if (!f.value.length) return;
        const wrap = document.createElement('div'); wrap.className = 'table-wrap';
        const title = document.createElement('h2'); title.textContent = f.label;
        const table = document.createElement('table');
        const labels = [...new Set(f.value.flatMap(row => row.map(cell => cell.label)))];
        const head = document.createElement('tr');
        labels.forEach(label => {const th = document.createElement('th'); th.textContent = label; head.append(th);});
        const thead = document.createElement('thead'); thead.append(head); table.append(thead);
        const body = document.createElement('tbody');
        f.value.forEach(row => {
          const tr = document.createElement('tr');
          labels.forEach(label => {
            const td = document.createElement('td'); const item = row.find(cell => cell.label === label);
            td.textContent = item && item.value != null ? String(item.value) : '—'; tr.append(td);
          }); body.append(tr);
        });
        table.append(body); wrap.append(title, table); target.append(wrap);
      } else target.append(field(f.label, f.type === 'Check' ? (f.value ? 'Yes' : 'No') : f.value));
    });
  }
  async function load() {
    if (!args.sales_order || !args.cps) throw new Error('The approval link needs a Sales Order and CPS.');
    const result = await frappe.call({method: method + 'review', args, type: 'GET'});
    review = result.message;
    find('name').textContent = review.name + ' · ' + review.cps_status;
    find('customer').textContent = review.customer + ' · ' + review.sales_order;
    find('prices').append(
      field('Proposed CPS price · ' + review.price.status, review.price.currency + ' ' + review.price.rate + ' / ' + review.price.uom),
      field('Effective from', review.price.valid_from),
      field('Sales Order rate · net / ex-VAT', review.order_currency + ' ' + review.order_rate + ' / ' + review.order_uom)
    );
    if (review.changes.length) {
      review.changes.forEach(change => find('changes').append(field(change.field,
        'On order: ' + JSON.stringify(change.ordered) + ' · Now: ' + JSON.stringify(change.current))));
    } else find('changes').textContent = 'Specification matches the frozen first-order snapshot.';
    render(review.fields, find('fields'));
    find('packing').hidden = !review.packing_allowed;
    if (review.packing_allowed) {
      find('sets').value = review.sets_per_carton || '';
      find('tare').value = review.carton_tare == null ? '' : review.carton_tare;
    }
    find('loading').hidden = true; find('content').hidden = false;
  }
  find('approve').addEventListener('click', async () => {
    find('approve').disabled = true; find('error').hidden = true;
    try {
      const payload = {...args, version: review.version};
      if (review.packing_allowed) {
        payload.sets_per_carton = find('sets').value;
        payload.carton_tare = find('tare').value;
      }
      await frappe.call({method: method + 'approve', args: payload, type: 'POST'});
      find('result').textContent = 'CPS and price approved. Job Card release checks remain separate.';
      find('approve').textContent = 'Approved';
    } catch (e) {
      error(e.message || 'Approval failed. Review the message above and reload before trying again.');
      find('approve').disabled = false;
    }
  });
  load().catch(e => {find('loading').hidden = true; error(e.message || 'Unable to load this approval. Sign in and check your approval permissions.');});
});
