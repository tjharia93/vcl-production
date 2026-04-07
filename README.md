<h1>Production Log &mdash; VCL (Vimit Converters Ltd)</h1>

<p>A custom Frappe&nbsp;/&nbsp;ERPNext&nbsp;v16 app for capturing daily production data from the shop floor at Vimit Converters Ltd, Nairobi.<br>
Tracks multiple workstations running 1&ndash;4 paper reels simultaneously.</p>

<hr>

<h2>Contents</h2>
<ol>
  <li><a href="#features">Features</a></li>
  <li><a href="#roles">Roles &amp; Permissions</a></li>
  <li><a href="#installation">Installation</a></li>
  <li><a href="#post-install">Post-Installation Steps</a></li>
  <li><a href="#doctypes">DocTypes</a></li>
  <li><a href="#field-ref-dpl">Field Reference &mdash; Daily Production Log</a></li>
  <li><a href="#field-ref-pe">Field Reference &mdash; Production Entry (child table)</a></li>
  <li><a href="#reel-fields">Reel Fields (Reels 1&ndash;4)</a></li>
  <li><a href="#reference-tables">Reference Tables</a></li>
  <li><a href="#reports">Reports</a></li>
  <li><a href="#development">Development</a></li>
</ol>

<hr>

<h2 id="features">Features</h2>
<ul>
  <li>Uses ERPNext&rsquo;s built-in <strong>Workstation</strong> DocType for station management.</li>
  <li><strong>Workstation Type</strong> selector on each entry row &mdash; the Workstation dropdown filters automatically.</li>
  <li><strong>Daily Production Log</strong> (submittable, amendable) capturing all entries for a date&nbsp;+&nbsp;shift.</li>
  <li><strong>Production Entry</strong> child table with full reel data (GSM, weight, cut size, reams) for up to 4 reels per station run.</li>
  <li>Conditional field visibility &mdash; Reel&nbsp;2/3/4 sections only appear when needed.</li>
  <li>Python validation: weight checks, time checks, station capacity checks, duplicate log prevention.</li>
  <li>Auto-calculated summary fields (recalculated on every save).</li>
  <li>4 built-in reports: Production Summary by Station, Operator Performance, Incomplete Reels Tracker, Daily Production Summary.</li>
  <li>A4 landscape print format.</li>
  <li>Production Management workspace with shortcuts and reports.</li>
  <li>Daily email summary (scheduled task).</li>
</ul>

<hr>

<h2 id="roles">Roles &amp; Permissions</h2>

<p>This app uses ERPNext&rsquo;s built-in roles &mdash; no custom roles are created.</p>

<table>
  <thead>
    <tr>
      <th>Role</th>
      <th>Create</th>
      <th>Read</th>
      <th>Write</th>
      <th>Delete</th>
      <th>Submit</th>
      <th>Cancel</th>
      <th>Amend</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>Manufacturing Manager</strong></td>
      <td align="center">&#10003;</td>
      <td align="center">&#10003;</td>
      <td align="center">&#10003;</td>
      <td align="center">&#10003;</td>
      <td align="center">&#10003;</td>
      <td align="center">&#10003;</td>
      <td align="center">&#10003;</td>
    </tr>
    <tr>
      <td><strong>System Manager</strong></td>
      <td align="center">&#10003;</td>
      <td align="center">&#10003;</td>
      <td align="center">&#10003;</td>
      <td align="center">&#10003;</td>
      <td align="center">&#10003;</td>
      <td align="center">&#10003;</td>
      <td align="center">&#10003;</td>
    </tr>
    <tr>
      <td><strong>Manufacturing User</strong></td>
      <td align="center">&#10003;</td>
      <td align="center">&#10003;</td>
      <td align="center">&mdash;</td>
      <td align="center">&mdash;</td>
      <td align="center">&mdash;</td>
      <td align="center">&mdash;</td>
      <td align="center">&mdash;</td>
    </tr>
  </tbody>
</table>

<hr>

<h2 id="installation">Installation</h2>

<pre><code># 1. Get the app
bench get-app https://github.com/tjharia93/vcl-production.git

# 2. Install on your site
bench --site [your-site] install-app production_log

# 3. Run migrations (runs patches automatically)
bench --site [your-site] migrate
</code></pre>

<hr>

<h2 id="post-install">Post-Installation Steps</h2>
<ol>
  <li>Go to <strong>Manufacturing &rsaquo; Workstation Type</strong> and create types for your shop floor (e.g. <em>Ruling</em>, <em>Sheeting</em>).</li>
  <li>Go to <strong>Manufacturing &rsaquo; Workstation</strong> and create a record for each physical machine.
    <ul>
      <li>Set <strong>Workstation Type</strong> so the cascading filter works.</li>
      <li>Set <strong>Job Capacity</strong> to the maximum number of reels that station can run simultaneously (1&ndash;4).</li>
    </ul>
  </li>
  <li>Assign <strong>Manufacturing Manager</strong> or <strong>System Manager</strong> to supervisors, and <strong>Manufacturing User</strong> to data-entry operators.</li>
  <li>Navigate to the <strong>Production Management</strong> workspace in the sidebar.</li>
  <li>Create a test <strong>Daily Production Log</strong> to verify everything works.</li>
</ol>

<hr>

<h2 id="doctypes">DocTypes</h2>

<table>
  <thead>
    <tr><th>DocType</th><th>Type</th><th>Purpose</th></tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>Daily Production Log</strong></td>
      <td>Transaction (submittable)</td>
      <td>Header record for a date + shift. One per shift per day.</td>
    </tr>
    <tr>
      <td><strong>Production Entry</strong></td>
      <td>Child Table</td>
      <td>Per-workstation reel production data. Up to 4 reels per row.</td>
    </tr>
  </tbody>
</table>

<blockquote>
  <strong>Note:</strong> Production Station has been replaced by ERPNext&rsquo;s built-in <strong>Workstation</strong> DocType.<br>
  Configure workstations in <strong>Manufacturing &rsaquo; Workstation</strong>.
</blockquote>

<hr>

<h2 id="field-ref-dpl">Field Reference &mdash; Daily Production Log</h2>

<table>
  <thead>
    <tr>
      <th>Field Label</th>
      <th>Field Name</th>
      <th>Type</th>
      <th>Required</th>
      <th>Description</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>Series</strong></td>
      <td><code>naming_series</code></td>
      <td>Select</td>
      <td align="center">&#10003;</td>
      <td>Auto-generated document number. Format: <code>PROD-LOG-YYYY-MM-DD-####</code>. Do not change unless instructed by the system administrator.</td>
    </tr>
    <tr>
      <td><strong>Production Date</strong></td>
      <td><code>production_date</code></td>
      <td>Date</td>
      <td align="center">&#10003;</td>
      <td>The calendar date this log covers. Defaults to today. Only one log per date&nbsp;+&nbsp;shift is allowed &mdash; a duplicate will be rejected on save.</td>
    </tr>
    <tr>
      <td><strong>Shift</strong></td>
      <td><code>shift</code></td>
      <td>Select</td>
      <td align="center">&#10003;</td>
      <td><strong>Day</strong> = morning/afternoon shift &nbsp;|&nbsp; <strong>Night</strong> = overnight shift. Only one log per shift per date is permitted.</td>
    </tr>
    <tr>
      <td><strong>Production Manager</strong></td>
      <td><code>production_manager</code></td>
      <td>Link &rarr; User</td>
      <td align="center">&mdash;</td>
      <td>The supervisor or manager responsible for this shift.</td>
    </tr>
    <tr>
      <td><strong>Department</strong></td>
      <td><code>department</code></td>
      <td>Link &rarr; Department</td>
      <td align="center">&mdash;</td>
      <td>Department this log belongs to (e.g. Production, Converting). Used for filtering and reporting.</td>
    </tr>
    <tr>
      <td><strong>Status</strong></td>
      <td><code>status</code></td>
      <td>Select (read-only)</td>
      <td align="center">&mdash;</td>
      <td>Automatically managed. <strong>Draft</strong> = editable &nbsp;|&nbsp; <strong>Submitted</strong> = locked and counted in reports &nbsp;|&nbsp; <strong>Cancelled</strong> = voided. Use <em>Amend</em> to correct a submitted log.</td>
    </tr>
    <tr>
      <td><strong>Total Entries</strong></td>
      <td><code>total_entries</code></td>
      <td>Int (read-only)</td>
      <td align="center">&mdash;</td>
      <td>Auto-calculated. Total number of workstation entry rows in the table.</td>
    </tr>
    <tr>
      <td><strong>Production Entries</strong></td>
      <td><code>production_entries</code></td>
      <td>Table &rarr; Production Entry</td>
      <td align="center">&mdash;</td>
      <td>Add one row per workstation run. A workstation may appear more than once if operators changed mid-shift.</td>
    </tr>
    <tr>
      <td><strong>Total Reels Processed</strong></td>
      <td><code>total_reels_processed</code></td>
      <td>Int (read-only)</td>
      <td align="center">&mdash;</td>
      <td>Sum of <em>Number of Reels</em> across all entries in this log.</td>
    </tr>
    <tr>
      <td><strong>Total Full Reams</strong></td>
      <td><code>total_full_reams</code></td>
      <td>Int (read-only)</td>
      <td align="center">&mdash;</td>
      <td>Sum of all <em>Full Reams</em> values across every reel section in this log.</td>
    </tr>
    <tr>
      <td><strong>Total Incomplete Reels</strong></td>
      <td><code>total_incomplete_reels</code></td>
      <td>Int (read-only)</td>
      <td align="center">&mdash;</td>
      <td>Count of reels flagged as <em>Incomplete Reel</em>. These carry forward and appear in the Incomplete Reels Tracker report.</td>
    </tr>
  </tbody>
</table>

<hr>

<h2 id="field-ref-pe">Field Reference &mdash; Production Entry (child table)</h2>

<h3>Header Section</h3>

<table>
  <thead>
    <tr>
      <th>Field Label</th>
      <th>Field Name</th>
      <th>Type</th>
      <th>Required</th>
      <th>Description</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>Workstation Type</strong></td>
      <td><code>workstation_type</code></td>
      <td>Link &rarr; Workstation Type</td>
      <td align="center">&#10003;</td>
      <td>Select the type of workstation first (e.g. Ruling, Sheeting). The Workstation dropdown will filter to show only matching stations. Changing this clears the Workstation field.</td>
    </tr>
    <tr>
      <td><strong>Workstation</strong></td>
      <td><code>station</code></td>
      <td>Link &rarr; Workstation</td>
      <td align="center">&#10003;</td>
      <td>The specific workstation for this entry. Filtered by the selected Workstation Type. The workstation&rsquo;s <strong>Job Capacity</strong> controls the maximum number of reels allowed.</td>
    </tr>
    <tr>
      <td><strong>Operator</strong></td>
      <td><code>operator</code></td>
      <td>Link &rarr; Employee</td>
      <td align="center">&#10003;</td>
      <td>The employee operating this workstation during this entry.</td>
    </tr>
    <tr>
      <td><strong>Start Time</strong></td>
      <td><code>start_time</code></td>
      <td>Time</td>
      <td align="center">&#10003;</td>
      <td>Time the operator started on this workstation. For overnight shifts enter the actual clock time &mdash; duration is calculated automatically.</td>
    </tr>
    <tr>
      <td><strong>End Time</strong></td>
      <td><code>end_time</code></td>
      <td>Time</td>
      <td align="center">&#10003;</td>
      <td>Time the operator finished. If end time is earlier than start time, an overnight shift is assumed and 24&nbsp;hours are added to the calculation.</td>
    </tr>
    <tr>
      <td><strong>Duration (Hours)</strong></td>
      <td><code>duration_hours</code></td>
      <td>Float (read-only)</td>
      <td align="center">&mdash;</td>
      <td>Auto-calculated from Start and End Time. Overnight shifts are handled correctly.</td>
    </tr>
  </tbody>
</table>

<h3>Material &amp; Run Configuration Section</h3>

<table>
  <thead>
    <tr>
      <th>Field Label</th>
      <th>Field Name</th>
      <th>Type</th>
      <th>Required</th>
      <th>Options</th>
      <th>Description</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>Material Type</strong></td>
      <td><code>material_type</code></td>
      <td>Select</td>
      <td align="center">&#10003;</td>
      <td>NP, BP, AP, CP</td>
      <td><strong>NP</strong>&nbsp;= Newsprint &nbsp;|&nbsp; <strong>BP</strong>&nbsp;= Bond Paper &nbsp;|&nbsp; <strong>AP</strong>&nbsp;= Art Paper &nbsp;|&nbsp; <strong>CP</strong>&nbsp;= Coated Paper</td>
    </tr>
    <tr>
      <td><strong>Output Type</strong></td>
      <td><code>output_type</code></td>
      <td>Select</td>
      <td align="center">&mdash;</td>
      <td>A1, A2, BT</td>
      <td><strong>A1</strong>&nbsp;= Grade&nbsp;A1 output &nbsp;|&nbsp; <strong>A2</strong>&nbsp;= Grade&nbsp;A2 output &nbsp;|&nbsp; <strong>BT</strong>&nbsp;= Broke/Trim (waste&nbsp;/&nbsp;off-cuts)</td>
    </tr>
    <tr>
      <td><strong>Number of Reels</strong></td>
      <td><code>number_of_reels</code></td>
      <td>Select</td>
      <td align="center">&#10003;</td>
      <td>1, 2, 3, 4</td>
      <td>How many reels this workstation is running simultaneously. Cannot exceed the workstation&rsquo;s Job Capacity. Reel 2, 3 and 4 sections appear automatically.</td>
    </tr>
  </tbody>
</table>

<hr>

<h2 id="reel-fields">Reel Fields (Reels 1&ndash;4)</h2>

<p>
  <strong>Reel 1</strong> is always visible.<br>
  <strong>Reel 2</strong> appears when Number of Reels &ge; 2.<br>
  <strong>Reel 3</strong> appears when Number of Reels &ge; 3.<br>
  <strong>Reel 4</strong> appears when Number of Reels = 4.
</p>

<p>The same set of fields exists for each reel. The table below uses the <code>r1_</code> prefix; replace with <code>r2_</code>, <code>r3_</code>, or <code>r4_</code> for the other reels.</p>

<table>
  <thead>
    <tr>
      <th>Field Label</th>
      <th>Field Name (Reel 1)</th>
      <th>Type</th>
      <th>Unit</th>
      <th>Description</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>GSM</strong></td>
      <td><code>r1_gsm</code></td>
      <td>Float (1&nbsp;dp)</td>
      <td>g/m&sup2;</td>
      <td>Grammage of the paper on this reel.</td>
    </tr>
    <tr>
      <td><strong>Reel Width</strong></td>
      <td><code>r1_reel_width</code></td>
      <td>Float (1&nbsp;dp)</td>
      <td>mm</td>
      <td>Cut width of the reel.</td>
    </tr>
    <tr>
      <td><strong>Start Diameter</strong></td>
      <td><code>r1_start_diameter</code></td>
      <td>Float (1&nbsp;dp)</td>
      <td>mm</td>
      <td>Outer diameter of the reel at the beginning of the run.</td>
    </tr>
    <tr>
      <td><strong>Start Weight</strong></td>
      <td><code>r1_start_weight</code></td>
      <td>Float (2&nbsp;dp)</td>
      <td>kg</td>
      <td>Gross weight of the reel at the start of the run.</td>
    </tr>
    <tr>
      <td><strong>End Diameter</strong></td>
      <td><code>r1_end_diameter</code></td>
      <td>Float (1&nbsp;dp)</td>
      <td>mm</td>
      <td>Outer diameter of the reel at the end of the run.</td>
    </tr>
    <tr>
      <td><strong>End Weight</strong></td>
      <td><code>r1_end_weight</code></td>
      <td>Float (2&nbsp;dp)</td>
      <td>kg</td>
      <td>Gross weight of the reel at the end of the run. <em>Must be less than Start Weight.</em></td>
    </tr>
    <tr>
      <td><strong>Cut Size</strong></td>
      <td><code>r1_cut_size</code></td>
      <td>Data</td>
      <td>&mdash;</td>
      <td>Sheet size being cut, e.g. <code>A4</code>, <code>F4</code>, <code>210x297</code>.</td>
    </tr>
    <tr>
      <td><strong>Sheets per Ream</strong></td>
      <td><code>r1_sheets_per_ream</code></td>
      <td>Int</td>
      <td>sheets</td>
      <td>Number of sheets that make one full ream for this cut size (typically 480 or 500).</td>
    </tr>
    <tr>
      <td><strong>Full Reams</strong></td>
      <td><code>r1_full_reams</code></td>
      <td>Int</td>
      <td>reams</td>
      <td>Total complete reams produced from this reel during this run.</td>
    </tr>
    <tr>
      <td><strong>Balance Sheets</strong></td>
      <td><code>r1_balance_sheets</code></td>
      <td>Int</td>
      <td>sheets</td>
      <td>Remaining sheets that did not complete a full ream at the end of the run.</td>
    </tr>
    <tr>
      <td><strong>Incomplete Reel (Carry Forward)</strong></td>
      <td><code>r1_incomplete_reel</code></td>
      <td>Check</td>
      <td>&mdash;</td>
      <td>Tick if paper remains on this reel and it will continue in the next shift or day. Appears in the <strong>Incomplete Reels Tracker</strong> report.</td>
    </tr>
  </tbody>
</table>

<h3>Notes Section</h3>

<table>
  <thead>
    <tr><th>Field Label</th><th>Field Name</th><th>Type</th><th>Description</th></tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>Comments / Observations</strong></td>
      <td><code>notes</code></td>
      <td>Text Editor</td>
      <td>Any additional observations &mdash; e.g. machine downtime, quality issues, reel splices, or handover notes.</td>
    </tr>
  </tbody>
</table>

<hr>

<h2 id="reference-tables">Reference Tables</h2>

<h3>Material Types</h3>
<table>
  <thead><tr><th>Code</th><th>Full Name</th></tr></thead>
  <tbody>
    <tr><td><strong>NP</strong></td><td>Newsprint</td></tr>
    <tr><td><strong>BP</strong></td><td>Bond Paper</td></tr>
    <tr><td><strong>AP</strong></td><td>Art Paper</td></tr>
    <tr><td><strong>CP</strong></td><td>Coated Paper</td></tr>
  </tbody>
</table>

<h3>Output Types</h3>
<table>
  <thead><tr><th>Code</th><th>Description</th></tr></thead>
  <tbody>
    <tr><td><strong>A1</strong></td><td>Grade A1 output</td></tr>
    <tr><td><strong>A2</strong></td><td>Grade A2 output</td></tr>
    <tr><td><strong>BT</strong></td><td>Broke / Trim (waste and off-cuts)</td></tr>
  </tbody>
</table>

<h3>Document Status Values</h3>
<table>
  <thead><tr><th>Status</th><th>docstatus</th><th>Meaning</th></tr></thead>
  <tbody>
    <tr><td><strong>Draft</strong></td><td>0</td><td>Editable. Not yet counted in reports.</td></tr>
    <tr><td><strong>Submitted</strong></td><td>1</td><td>Locked. Counted in all reports.</td></tr>
    <tr><td><strong>Cancelled</strong></td><td>2</td><td>Voided. Not counted in reports.</td></tr>
  </tbody>
</table>

<h3>Workstation Setup Requirements</h3>
<table>
  <thead><tr><th>ERPNext Field</th><th>Location</th><th>Purpose in this App</th></tr></thead>
  <tbody>
    <tr>
      <td><strong>Workstation Type</strong></td>
      <td>Workstation form &rsaquo; Details tab</td>
      <td>Drives the cascading filter on Production Entry rows.</td>
    </tr>
    <tr>
      <td><strong>Job Capacity</strong></td>
      <td>Workstation form &rsaquo; Details tab</td>
      <td>Maximum number of reels this station can run (1&ndash;4). Enforced on data entry and on save.</td>
    </tr>
  </tbody>
</table>

<hr>

<h2 id="reports">Reports</h2>

<table>
  <thead>
    <tr><th>Report</th><th>Type</th><th>Description</th></tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>Production Summary by Station</strong></td>
      <td>Script</td>
      <td>Daily entries grouped by workstation. Filter by date range and station.</td>
    </tr>
    <tr>
      <td><strong>Operator Performance</strong></td>
      <td>Script</td>
      <td>Aggregated reams, hours and efficiency metrics per operator.</td>
    </tr>
    <tr>
      <td><strong>Incomplete Reels Tracker</strong></td>
      <td>Script</td>
      <td>All reels flagged as carry-forward. Defaults to last 7 days.</td>
    </tr>
    <tr>
      <td><strong>Daily Production Summary</strong></td>
      <td>Script</td>
      <td>Yesterday&rsquo;s totals with a bar chart breakdown by station.</td>
    </tr>
  </tbody>
</table>

<hr>

<h2 id="development">Development</h2>

<pre><code># Run bench in dev mode
bench start

# Reload DocTypes after JSON changes
bench --site [your-site] migrate

# Reload a single DocType (no migration needed for cosmetic changes)
bench --site [your-site] reload-doctype "Daily Production Log"
bench --site [your-site] reload-doctype "Production Entry"
</code></pre>

<hr>

<h2>License</h2>

<p>MIT &mdash; see <code>license.txt</code>.</p>
