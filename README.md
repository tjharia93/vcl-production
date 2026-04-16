<h1>Production Log &mdash; VCL (Vimit Converters Ltd)</h1>

<p>A custom Frappe&nbsp;/&nbsp;ERPNext&nbsp;v16 app for Vimit Converters Ltd, Nairobi.<br>
The current scope is the <strong>master / job-card creation</strong> foundation — Customer
Product Specifications and the three Job Card types (Computer Paper, Label, Carton).</p>

<p>The production execution / planning layer (Daily Production Log, Production Entry,
Daily Production Plans / Actuals, Department Daily Plan) has been removed for a clean
restart. It will be redesigned in a later iteration.</p>

<hr>

<h2>What ships in this app</h2>
<ul>
  <li><strong>Customer Product Specification</strong> — single specification doctype
      that supports Computer Paper, Label, and Carton product types.</li>
  <li><strong>Job Card Computer Paper</strong> — submittable job card for computer-paper
      jobs, links to a Customer Product Specification of type "Computer Paper".</li>
  <li><strong>Job Card Label</strong> — submittable job card for label jobs, with the
      label spec snapshot auto-populated from the Customer Product Specification.</li>
  <li><strong>Job Card Carton</strong> — submittable job card for carton jobs, with the
      ply rules &rarr; SFK UI &rarr; flap auto-calc &rarr; board sizes &rarr; weight
      calculation pipeline.</li>
  <li><strong>Dies</strong> + <strong>Dies Order</strong> — die master and ordering
      records.</li>
  <li><strong>Colour of Parts</strong> — child table used by Customer Product
      Specification and Job Card Computer Paper to capture per-part paper / GSM /
      colour / purpose rows.</li>
  <li><strong>VCL Production</strong> workspace at <code>/app/vcl-production</code> with
      shortcuts for the six items above.</li>
</ul>

<hr>

<h2>What was removed (hard reset)</h2>
<ul>
  <li>Daily Production Log, Production Entry</li>
  <li>Daily Production Plan, Daily Production Plan Line</li>
  <li>Daily Production Actual, Daily Production Actual Line</li>
  <li>Job Card Production Entry, Production Actual Line, Production Planning Line</li>
  <li>Department Daily Plan, Department Daily Plan Line</li>
  <li>Reports: Daily Production Summary, Incomplete Reels Tracker, Operator Performance,
      Production Summary by Station</li>
  <li>Print format: Daily Production Plan - Floor Sheet</li>
  <li>Production Execution Control workspace</li>
  <li>The Production Control section on Job Card Computer Paper / Job Card Label
      (production_status, production_stage, planned_for_date, priority, qty_completed,
      qty_pending, last_production_update, completed_on, hold_reason, production_comments)</li>
  <li>The scheduled <code>send_daily_production_summary</code> task and any related
      hooks / scheduler events</li>
</ul>

<p>The patch <code>production_log.patches.v1_0.remove_production_execution_layer</code>
runs on <code>bench migrate</code> and idempotently drops the old doctypes, tables,
columns, reports, print formats, and workspace links from any site that previously
had them installed.</p>

<hr>

<h2 id="installation">Installation</h2>
<pre><code>bench get-app https://github.com/tjharia93/vcl-production production_log
bench --site &lt;site&gt; install-app production_log
bench --site &lt;site&gt; migrate
</code></pre>

<p>After install, open <code>/app/vcl-production</code> as Administrator to start
creating Customer Product Specifications and Job Cards.</p>

<hr>

<h2 id="testing">Testing</h2>
<p>OAT and UAT plans live in <a href="docs/testing/oat-plan.md"><code>docs/testing/oat-plan.md</code></a>
and <a href="docs/testing/uat-plan.md"><code>docs/testing/uat-plan.md</code></a>.
Run OAT first; UAT second.</p>
