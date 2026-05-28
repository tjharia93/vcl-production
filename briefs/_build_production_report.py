#!/usr/bin/env python3
"""Build the VCL-DEV-PROD-001 (Production Log) status report.

Same VCL Brand v1.1 chrome as the PMO report. Replaces the
PMO-specific content with the production_log Frappe app.

Palette + fonts + stamp loaded from /tmp/b64/ (same source as the
PMO build script).
"""
from pathlib import Path
import base64

REPO = Path('/home/tanujharia/projects/vcl-production')
B64 = Path('/tmp/b64')

def load_b64(name): return B64.joinpath(name).read_text()
def img_b64(p): return base64.b64encode(Path(p).read_bytes()).decode()

STAMP = load_b64('stamp.b64')
MR_400 = load_b64('manrope-400.b64'); MR_600 = load_b64('manrope-600.b64')
MR_700 = load_b64('manrope-700.b64'); MR_800 = load_b64('manrope-800.b64')
JB_400 = load_b64('jbmono-400.b64'); JB_700 = load_b64('jbmono-700.b64')

SHOT_DIR = REPO / 'briefs/screenshots'
def shot(name):
    p = SHOT_DIR / f'{name}.png'
    return img_b64(p) if p.exists() else ''

SHOT_WORKSPACE = shot('vcl-production-workspace')
SHOT_PPC       = shot('ppc-workspace')
SHOT_CPS       = shot('cps-list')
SHOT_CARTON    = shot('job-card-carton-list')
SHOT_LABEL     = shot('job-card-label-list')
SHOT_DIES      = shot('dies-list')
SHOT_PLAN      = shot('ppc-daily-plan-list')
SHOT_JOBPOOL   = shot('ppc-open-job-pool')

CSS = r"""
@font-face { font-family:'Manrope'; font-weight:400; src:url(data:font/ttf;base64,__MR_400__) format('truetype'); }
@font-face { font-family:'Manrope'; font-weight:600; src:url(data:font/ttf;base64,__MR_600__) format('truetype'); }
@font-face { font-family:'Manrope'; font-weight:700; src:url(data:font/ttf;base64,__MR_700__) format('truetype'); }
@font-face { font-family:'Manrope'; font-weight:800; src:url(data:font/ttf;base64,__MR_800__) format('truetype'); }
@font-face { font-family:'JetBrains Mono'; font-weight:400; src:url(data:font/ttf;base64,__JB_400__) format('truetype'); }
@font-face { font-family:'JetBrains Mono'; font-weight:700; src:url(data:font/ttf;base64,__JB_700__) format('truetype'); }
:root{
  --vcl-blue:#2B3990; --vcl-navy:#1D2766; --vcl-blue-mid:#5C6DBE;
  --vcl-blue-light:#D6DBF5; --vcl-blue-pale:#EEF0FB;
  --vcl-sage:#5A9367; --vcl-sage-soft:rgba(90,147,103,0.22);
  --vcl-green:#1B7A45; --vcl-green-light:#D4EDE0;
  --vcl-amber:#B86B00; --vcl-amber-light:#FFF0CC;
  --vcl-red:#C0392B; --vcl-red-light:#FADBD8;
  --vcl-ink:#1C1C1E; --vcl-mid:#4A4F5C; --vcl-muted:#8A909E;
  --vcl-rule:#CBD2E0; --vcl-surface:#F4F5F8; --vcl-white:#FFFFFF;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;font-family:'Manrope',-apple-system,system-ui,sans-serif;color:var(--vcl-ink);background:var(--vcl-white);font-size:11pt;line-height:1.5;letter-spacing:-0.005em}
.mono,code,kbd{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:10pt}
@page{size:A4 portrait;margin:15mm 15mm 18mm 15mm}
.page{page-break-after:always;padding:0}
.page:last-of-type{page-break-after:auto}

.bar{background:var(--vcl-navy);color:white;padding:12px 18px;display:flex;align-items:center;justify-content:space-between;border-bottom:3px solid var(--vcl-sage);font-size:10pt;font-weight:600;letter-spacing:0.08em}
.bar .left{text-transform:uppercase;color:var(--vcl-sage)}
.bar .right{color:var(--vcl-blue-light);font-family:'JetBrains Mono',monospace;font-size:9pt;font-weight:400;letter-spacing:0.04em}

.foot{background:var(--vcl-navy);color:var(--vcl-blue-light);padding:8px 18px;display:flex;align-items:center;justify-content:space-between;border-top:3px solid var(--vcl-sage);font-size:8.5pt;font-family:'JetBrains Mono',monospace;letter-spacing:0.04em;margin-top:18px}
.foot .stamp-mini{width:32px;height:32px;opacity:0.95}

.cover{background:var(--vcl-navy);color:white;min-height:268mm;padding:24mm 18mm 18mm 18mm;display:flex;flex-direction:column;justify-content:space-between;margin:-15mm;position:relative}
.cover-stripe-top{height:6px;background:var(--vcl-sage);margin:-24mm -18mm 24mm -18mm}
.cover .org-line{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16mm}
.cover .org-line .caps{color:var(--vcl-sage);font-family:'Manrope',sans-serif;font-weight:700;font-size:10.5pt;letter-spacing:0.32em;text-transform:uppercase}
.cover .org-line .stamp img{width:120px;height:120px}
.cover .title{font-family:'Manrope',sans-serif;font-weight:800;font-size:48pt;line-height:1.0;letter-spacing:-0.02em;color:white}
.cover .subtitle{font-family:'Manrope',sans-serif;font-weight:600;font-size:18pt;color:var(--vcl-sage);line-height:1.1;margin-top:8px}
.cover .lede{font-size:15pt;color:rgba(255,255,255,0.82);line-height:1.45;max-width:540px;margin-top:14px;font-weight:400}
.cover .accent-rule{height:4px;background:var(--vcl-sage);width:80px;margin:28px 0}
.cover .meta-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:22px 32px;background:rgba(255,255,255,0.04);border:1px solid rgba(90,147,103,0.4);border-radius:8px;padding:22px 24px;margin-top:24px}
.cover .meta-grid .k{font-family:'JetBrains Mono',monospace;font-size:9pt;color:var(--vcl-sage);text-transform:uppercase;letter-spacing:0.12em;font-weight:600;margin-bottom:4px}
.cover .meta-grid .v{font-family:'Manrope',sans-serif;font-size:12.5pt;color:white;font-weight:600}
.cover .cover-foot{margin-top:auto;border-top:1px solid rgba(90,147,103,0.4);padding-top:14px;display:flex;justify-content:space-between;align-items:center;color:rgba(255,255,255,0.75);font-family:'JetBrains Mono',monospace;font-size:9pt;letter-spacing:0.06em}
.cover .cover-foot .confidential{color:var(--vcl-amber-light);font-weight:700}

h1{font-family:'Manrope',sans-serif;font-weight:800;font-size:24pt;color:var(--vcl-navy);letter-spacing:-0.015em;margin:18px 0 6px 0;line-height:1.1}
h2{font-family:'Manrope',sans-serif;font-weight:700;font-size:14pt;color:var(--vcl-blue);margin:22px 0 8px 0;padding-bottom:6px;border-bottom:2px solid var(--vcl-blue);letter-spacing:-0.01em}
h3{font-family:'Manrope',sans-serif;font-weight:700;font-size:11.5pt;color:var(--vcl-ink);margin:14px 0 6px 0}
.sub{color:var(--vcl-muted);font-size:11pt;margin-top:-2px}
p{margin:8px 0}
ul,ol{margin:8px 0 12px 22px;padding:0}
li{margin:4px 0}

.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0 22px 0}
.kpi{background:var(--vcl-white);border:1px solid var(--vcl-rule);border-top:3px solid var(--vcl-blue);border-radius:8px;padding:16px 18px;page-break-inside:avoid}
.kpi .l{font-size:9pt;text-transform:uppercase;letter-spacing:0.1em;color:var(--vcl-muted);font-weight:700}
.kpi .v{font-family:'JetBrains Mono',monospace;font-size:30pt;font-weight:500;color:var(--vcl-navy);letter-spacing:-0.02em;margin-top:6px;line-height:1}
.kpi .d{font-size:10pt;color:var(--vcl-mid);margin-top:6px}
.kpi.green{border-top-color:var(--vcl-green)} .kpi.green .v{color:var(--vcl-green)}
.kpi.amber{border-top-color:var(--vcl-amber)} .kpi.amber .v{color:var(--vcl-amber)}
.kpi.sage{border-top-color:var(--vcl-sage)} .kpi.sage .v{color:var(--vcl-sage)}
.kpi.slate{border-top-color:var(--vcl-muted)} .kpi.slate .v{color:var(--vcl-mid)}

.chip{display:inline-flex;align-items:center;gap:5px;font-size:9.5pt;font-weight:700;padding:2px 9px;border-radius:11px;letter-spacing:0.02em;border:1px solid transparent}
.chip i{width:6px;height:6px;border-radius:50%;display:inline-block}
.chip.green{background:var(--vcl-green-light);color:var(--vcl-green);border-color:#bfe2cd} .chip.green i{background:var(--vcl-green)}
.chip.amber{background:var(--vcl-amber-light);color:var(--vcl-amber);border-color:#f0d28b} .chip.amber i{background:var(--vcl-amber)}
.chip.muted{background:var(--vcl-surface);color:var(--vcl-mid);border-color:var(--vcl-rule)} .chip.muted i{background:var(--vcl-muted)}
.chip.blue{background:var(--vcl-blue-light);color:var(--vcl-blue);border-color:#bec7ea} .chip.blue i{background:var(--vcl-blue)}
.chip.red{background:var(--vcl-red-light);color:var(--vcl-red);border-color:#f1bcb4} .chip.red i{background:var(--vcl-red)}

.btn{font-size:10pt;font-weight:600;padding:6px 12px;border-radius:5px;border:1px solid var(--vcl-rule);color:var(--vcl-ink);background:var(--vcl-white);display:inline-flex;align-items:center;gap:6px;letter-spacing:-0.005em}
.btn.primary{background:var(--vcl-blue);color:white;border-color:var(--vcl-blue)}
.btn.amber{background:var(--vcl-amber);color:white;border-color:var(--vcl-amber)}
.btn.ghost{border-color:transparent;color:var(--vcl-muted)}

table.tbl{width:100%;border-collapse:separate;border-spacing:0;background:var(--vcl-white);border:1px solid var(--vcl-rule);border-radius:8px;overflow:hidden;font-size:10.5pt;margin:10px 0 16px 0}
table.tbl th{background:var(--vcl-blue);color:white;font-weight:700;font-size:9pt;text-transform:uppercase;letter-spacing:0.06em;text-align:left;padding:9px 13px}
table.tbl td{padding:10px 13px;border-top:1px solid var(--vcl-rule);color:var(--vcl-ink);vertical-align:top}
table.tbl tr:nth-child(even) td{background:var(--vcl-surface)}
table.tbl tr:first-child td{border-top:0}
table.tbl td.id-cell{font-family:'JetBrains Mono',monospace;font-size:10pt;color:var(--vcl-blue);font-weight:700}
table.tbl td.who{color:var(--vcl-mid);font-style:italic;width:100px}
table.tbl td.when{width:80px;color:var(--vcl-muted);font-family:'JetBrains Mono',monospace;font-size:10pt}

.card{background:var(--vcl-white);border:1px solid var(--vcl-rule);border-radius:8px;padding:16px 18px;margin:12px 0}
.summary-box{border-left:4px solid var(--vcl-blue);background:var(--vcl-blue-pale);padding:14px 18px;margin:14px 0 18px 0;border-radius:4px}
.summary-box b{color:var(--vcl-navy)}

.qa{background:var(--vcl-surface);border-left:4px solid var(--vcl-blue-mid);padding:11px 14px;border-radius:4px;margin:8px 0;font-size:11pt}
.qa b{color:var(--vcl-navy);margin-right:4px}

svg.diagram{display:block;margin:14px auto;max-width:100%;height:auto}
.caption{font-size:9.5pt;color:var(--vcl-muted);text-align:center;margin-top:-2px;font-style:italic}

.screenshot{background:var(--vcl-white);border:1px solid var(--vcl-rule);border-radius:8px;overflow:hidden;margin:14px 0;page-break-inside:avoid}
.screenshot .frame{padding:8px 12px;background:var(--vcl-navy);color:white;font-size:10pt;display:flex;justify-content:space-between;align-items:center}
.screenshot .frame b{color:var(--vcl-sage)}
.screenshot .frame .url{font-family:'JetBrains Mono',monospace;font-size:9pt;color:var(--vcl-blue-light)}
.screenshot img{display:block;width:100%;height:auto}
.screenshot .caption-row{padding:8px 12px;font-size:10pt;color:var(--vcl-mid);border-top:1px solid var(--vcl-rule);background:var(--vcl-surface)}

.modules{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:14px 0 18px 0}
.module{background:var(--vcl-white);border:1px solid var(--vcl-rule);border-radius:8px;padding:14px 16px;page-break-inside:avoid}
.module .ttl{font-family:'JetBrains Mono',monospace;font-size:10pt;color:var(--vcl-sage);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px;font-weight:700}
.module .nm{font-weight:800;font-size:14pt;color:var(--vcl-navy);letter-spacing:-0.01em}
.module .ct{font-size:9pt;color:var(--vcl-muted);text-transform:uppercase;letter-spacing:0.06em;font-weight:700;margin-top:4px}
.module .ls{font-size:10pt;color:var(--vcl-mid);margin-top:8px;line-height:1.5}

.signature{margin-top:30px;padding-top:16px;border-top:1px solid var(--vcl-rule);font-size:10.5pt;color:var(--vcl-muted);display:grid;grid-template-columns:1fr 1fr;gap:30px}
.signature .slot{border-bottom:1px solid var(--vcl-ink);padding-bottom:32px;margin-bottom:6px}

.timeline{margin:12px 0}
.t-row{display:grid;grid-template-columns:90px 1fr;gap:14px;padding:8px 0;border-top:1px solid var(--vcl-rule)}
.t-row:first-child{border-top:0}
.t-row .when{color:var(--vcl-blue);font-family:'JetBrains Mono',monospace;font-size:10pt;font-weight:700}
.t-row .what b{color:var(--vcl-navy)}

@media print{
  body{background:white;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .cover{color:white;background:var(--vcl-navy)!important}
  .bar,.foot{background:var(--vcl-navy)!important;color:white!important}
  table.tbl th{background:var(--vcl-blue)!important;color:white!important}
  h1,h2,h3{page-break-after:avoid}
  p,li{orphans:3;widows:3}
  .kpi,.card,.screenshot,.qa,.summary-box,table.tbl tr,.module{page-break-inside:avoid}
}
"""

def bar(left, right):
    return f'<div class="bar"><span class="left">{left}</span><span class="right">{right}</span></div>'
def foot(left):
    return f'<div class="foot"><span>{left}</span><img class="stamp-mini" src="data:image/png;base64,{STAMP}" alt="VCL"/></div>'
def sb(label, url, b64, caption):
    if not b64: return ''
    return f"""
<div class="screenshot">
  <div class="frame"><span><b>{label}</b></span><span class="url">{url}</span></div>
  <img src="data:image/png;base64,{b64}" alt="{label}"/>
  <div class="caption-row">{caption}</div>
</div>"""

# ---------------------------------------------------------------------------
# Diagrams
# ---------------------------------------------------------------------------

PIPELINE_SVG = r"""
<svg class="diagram" viewBox="0 0 720 360" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Carton job pipeline">
  <defs>
    <marker id="arrCP" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="9" markerHeight="9" orient="auto">
      <path d="M0,0 L12,6 L0,12 z" fill="#1D2766"/>
    </marker>
    <style>
      .blk-pri  { fill:#2B3990; }
      .blk-sage { fill:#5A9367; }
      .blk-amb  { fill:#B86B00; }
      .blk-nav  { fill:#1D2766; }
      .ltxt     { fill:white; font:700 12px Manrope, sans-serif; }
      .lsub     { fill:#D6DBF5; font:10px Manrope, sans-serif; }
      .lnk      { fill:#8A909E; font:9px 'JetBrains Mono', monospace; }
    </style>
  </defs>

  <!-- CPS master -->
  <rect x="40" y="40" width="160" height="90" rx="8" class="blk-pri"/>
  <text x="120" y="68" class="ltxt" text-anchor="middle">Customer Product</text>
  <text x="120" y="84" class="ltxt" text-anchor="middle">Specification</text>
  <text x="120" y="104" class="lsub" text-anchor="middle">master — 253 records</text>
  <text x="120" y="118" class="lsub" text-anchor="middle">Carton / Label / CP / ETR</text>

  <!-- Job Card -->
  <rect x="280" y="40" width="160" height="90" rx="8" class="blk-pri"/>
  <text x="360" y="68" class="ltxt" text-anchor="middle">Job Card</text>
  <text x="360" y="84" class="ltxt" text-anchor="middle">(one per type)</text>
  <text x="360" y="104" class="lsub" text-anchor="middle">Carton 19 · Label 56</text>
  <text x="360" y="118" class="lsub" text-anchor="middle">CP 35 · ETR n</text>

  <!-- Print format -->
  <rect x="520" y="40" width="160" height="90" rx="8" class="blk-sage"/>
  <text x="600" y="68" class="ltxt" text-anchor="middle">Print Format</text>
  <text x="600" y="84" class="ltxt" text-anchor="middle">(traveller PDF)</text>
  <text x="600" y="104" class="lsub" text-anchor="middle">4-6 pages — Carton Layout,</text>
  <text x="600" y="118" class="lsub" text-anchor="middle">Station Log, Resources</text>

  <!-- Traveller runs -->
  <rect x="120" y="180" width="160" height="70" rx="8" class="blk-nav"/>
  <text x="200" y="206" class="ltxt" text-anchor="middle">Job Traveller Run</text>
  <text x="200" y="226" class="lsub" text-anchor="middle">child table on every JC</text>
  <text x="200" y="240" class="lsub" text-anchor="middle">stage · operator · qty · time</text>

  <!-- Resource consumption -->
  <rect x="320" y="180" width="160" height="70" rx="8" class="blk-nav"/>
  <text x="400" y="206" class="ltxt" text-anchor="middle">Job Resource</text>
  <text x="400" y="222" class="ltxt" text-anchor="middle">Consumption</text>
  <text x="400" y="240" class="lsub" text-anchor="middle">planned vs actual w/ variance</text>

  <!-- Dies / colours masters -->
  <rect x="520" y="180" width="160" height="70" rx="8" class="blk-amb"/>
  <text x="600" y="206" class="ltxt" text-anchor="middle">Dies · Colours</text>
  <text x="600" y="226" class="lsub" text-anchor="middle">80 Dies · Pantone · Spot</text>
  <text x="600" y="240" class="lsub" text-anchor="middle">referenced by Carton JCs</text>

  <!-- PPC Daily Plan -->
  <rect x="200" y="290" width="320" height="50" rx="8" class="blk-pri"/>
  <text x="360" y="316" class="ltxt" text-anchor="middle">PPC Daily Plan → Production Actual</text>
  <text x="360" y="332" class="lsub" text-anchor="middle">aggregates Job Cards into the daily schedule, 10 reports downstream</text>

  <g stroke="#1D2766" stroke-width="1.5" fill="none" marker-end="url(#arrCP)">
    <line x1="200" y1="85" x2="278" y2="85"/>
    <line x1="440" y1="85" x2="518" y2="85"/>
    <line x1="360" y1="130" x2="200" y2="178"/>
    <line x1="360" y1="130" x2="400" y2="178"/>
    <line x1="360" y1="130" x2="600" y2="178"/>
    <line x1="360" y1="252" x2="360" y2="288"/>
  </g>
</svg>"""

GEMBA_FLOW_SVG = r"""
<svg class="diagram" viewBox="0 0 720 200" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Gemba EOD flow">
  <defs>
    <marker id="arrG" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="9" markerHeight="9" orient="auto">
      <path d="M0,0 L12,6 L0,12 z" fill="#1D2766"/>
    </marker>
    <style>
      .blk-pri{fill:#2B3990;} .blk-sage{fill:#5A9367;} .blk-amb{fill:#B86B00;}
      .ltxt{fill:white;font:700 12px Manrope,sans-serif}
      .lsub{fill:#D6DBF5;font:10px Manrope,sans-serif}
    </style>
  </defs>
  <g>
    <rect x="20"  y="80" width="120" height="50" rx="6" class="blk-pri"/>
    <text x="80" y="106" class="ltxt" text-anchor="middle">17:00 EAT cron</text>
    <text x="80" y="120" class="lsub" text-anchor="middle">Frappe scheduler</text>

    <rect x="170" y="80" width="120" height="50" rx="6" class="blk-pri"/>
    <text x="230" y="100" class="ltxt" text-anchor="middle">generate_eod</text>
    <text x="230" y="116" class="ltxt" text-anchor="middle">_report</text>
    <text x="230" y="128" class="lsub" text-anchor="middle">gemba.py</text>

    <rect x="320" y="80" width="120" height="50" rx="6" class="blk-sage"/>
    <text x="380" y="100" class="ltxt" text-anchor="middle">n8n webhook</text>
    <text x="380" y="116" class="ltxt" text-anchor="middle">vclGembaTelegram001</text>
    <text x="380" y="128" class="lsub" text-anchor="middle">multipart POST</text>

    <rect x="470" y="80" width="120" height="50" rx="6" class="blk-amb"/>
    <text x="530" y="100" class="ltxt" text-anchor="middle">Telegram</text>
    <text x="530" y="116" class="ltxt" text-anchor="middle">sendDocument</text>
    <text x="530" y="128" class="lsub" text-anchor="middle">to Tanuj's chat</text>

    <rect x="620" y="80" width="80" height="50" rx="6" class="blk-pri"/>
    <text x="660" y="106" class="ltxt" text-anchor="middle">reMarkable</text>
    <text x="660" y="120" class="lsub" text-anchor="middle">annotate</text>
  </g>
  <g stroke="#1D2766" stroke-width="1.5" fill="none" marker-end="url(#arrG)">
    <line x1="140" y1="105" x2="168" y2="105"/>
    <line x1="290" y1="105" x2="318" y2="105"/>
    <line x1="440" y1="105" x2="468" y2="105"/>
    <line x1="590" y1="105" x2="618" y2="105"/>
  </g>
</svg>"""

# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

COVER = f"""
<section class="page">
  <div class="cover">
    <div class="cover-stripe-top"></div>
    <div class="org-line">
      <div class="caps">Vimit Converters Limited</div>
      <div class="stamp"><img src="data:image/png;base64,{STAMP}" alt="VCL Stamp"/></div>
    </div>
    <div>
      <div class="title">VCL Production</div>
      <div class="subtitle">Job Cards · Customer Specs · PPC</div>
      <div class="lede">The Frappe / ERPNext app that runs the floor — customer product specifications, four job-card types, the carton calculation pipeline, and the PPC daily planning + reporting layer.</div>
      <div class="accent-rule"></div>
      <div class="meta-grid">
        <div><div class="k">Project ID</div><div class="v">VCL-DEV-PROD-001</div></div>
        <div><div class="k">Sponsor</div><div class="v">Tanuj Haria</div></div>
        <div><div class="k">Phase</div><div class="v">Phase 7 — Carton + Traveller</div></div>
        <div><div class="k">Repo</div><div class="v">github.com/tjharia93/vcl-production</div></div>
        <div><div class="k">Workspace</div><div class="v">/app/vcl-production · /app/ppc</div></div>
        <div><div class="k">This report</div><div class="v">28 May 2026</div></div>
      </div>
    </div>
    <div class="cover-foot">
      <span>Prepared by Claude · review on reMarkable / Boox Air 5 · VCL Brand v1.1</span>
      <span class="confidential">CONFIDENTIAL · VCL INTERNAL</span>
    </div>
  </div>
</section>"""

P_STATUS = f"""
<section class="page">
  {bar('VCL Production · Status', 'page 02 · 28 may 2026')}
  <div style="padding:0 6mm;">
  <h1>Where we are today</h1>
  <div class="sub">Status as at 21:30 EAT, 28 May 2026 against the live site.</div>

  <div class="kpis">
    <div class="kpi"><div class="l">CPS records</div><div class="v">253</div><div class="d">customer product specifications</div></div>
    <div class="kpi"><div class="l">Job Cards live</div><div class="v">110</div><div class="d">Carton 19 · Label 56 · CP 35</div></div>
    <div class="kpi sage"><div class="l">Doctypes</div><div class="v">22</div><div class="d">across 3 modules</div></div>
    <div class="kpi green"><div class="l">PPC reports</div><div class="v">10</div><div class="d">live for the planning desk</div></div>
  </div>

  <div class="summary-box">
    <b>One sentence:</b> The Production Log app is in active build — Job-Card-Tracking is the foundation (Customer Product Spec + four submittable Job Cards + traveller / resource child tables) and the PPC layer (Daily Plan, Production Actual + ten reports) sits on top. The current focus is the Carton job traveller PDF and the per-line stage ladder; the Computer-Paper, Label, and ETR job cards are stable.
  </div>

  <h2>What's running on the live site</h2>
  <table class="tbl">
    <thead><tr><th style="width:34%;">What</th><th>State</th><th style="width:90px;">Health</th></tr></thead>
    <tbody>
      <tr><td><b>Customer Product Specification</b></td><td>Single master doctype with 253 live records. Auto-toggles GSM / colour / packing sections by <code>ply</code> and <code>product_type</code>. Used by every job card.</td><td><span class="chip green"><i></i>LIVE</span></td></tr>
      <tr><td><b>Job Card Carton</b></td><td>19 records. Submittable. RSC / 1-flap / 2-flap / 3-flap / Tray geometry → board sizes + weight pipeline. Print format is a 4-6 page traveller (PDF generator = Chrome).</td><td><span class="chip green"><i></i>LIVE</span></td></tr>
      <tr><td><b>Job Card Label</b></td><td>56 records. Submittable. Spec snapshot auto-populates from CPS. Slack notification on submit via n8n.</td><td><span class="chip green"><i></i>LIVE</span></td></tr>
      <tr><td><b>Job Card Computer Paper</b></td><td>35 records. Submittable. Colour-of-Parts child table for per-part GSM / colour rows.</td><td><span class="chip green"><i></i>LIVE</span></td></tr>
      <tr><td><b>Job Card ETR</b></td><td>Live. Reel-to-reel printing for thermal / receipt rolls. Print format separate from the other three (different schema: <code>status</code> / <code>delivery_date</code>).</td><td><span class="chip green"><i></i>LIVE</span></td></tr>
      <tr><td><b>PPC Daily Plan + Production Actual</b></td><td>Daily-plan and same-day-actual doctypes with item child tables. Feeds 10 query reports (Open Job Pool, Closed Jobs, Waste, Downtime, Carry-Forward Pending, etc.).</td><td><span class="chip amber"><i></i>SOFT LIVE</span></td></tr>
      <tr><td><b>Job Traveller Run + Resource Consumption</b></td><td>Child tables on all 4 job cards (deployed 19-20 May). Capture stage / operator / quantity / time + planned-vs-actual material variance. Render in the print format Jinja loops.</td><td><span class="chip green"><i></i>LIVE</span></td></tr>
      <tr><td><b>Workstation product-line tag ladder</b></td><td>14 workstation types, 33+ tag rows numbered by <code>process_number</code> per product line (R2R, Trading, GSE, Mono Boxes, Self-Adhesive Label, Sheet-to-Sheet, Carton, Exercise Books). Codified in patch v7_4.</td><td><span class="chip green"><i></i>LIVE</span></td></tr>
      <tr><td><b>17:00 EOD Gemba report → Telegram</b></td><td>Frappe scheduler → <code>gemba.py</code> → n8n webhook (vclGembaTelegram001) → Telegram <code>sendDocument</code>. n8n holds the bot token (Frappe Cloud doesn't).</td><td><span class="chip amber"><i></i>NEEDS SITE_CONFIG</span></td></tr>
    </tbody>
  </table>
  </div>
  {foot('VCL Production · VCL-DEV-PROD-001 · 28 May 2026')}
</section>"""

P_ARCH = f"""
<section class="page">
  {bar('VCL Production · Architecture', 'page 03 · 28 may 2026')}
  <div style="padding:0 6mm;">
  <h1>What's in the app</h1>
  <p>One Frappe app (<code>production_log</code>), three modules, 22 doctypes, 10 reports, 44 patches deployed since v3.</p>

  <div class="modules">
    <div class="module">
      <div class="ttl">Module 01</div>
      <div class="nm">Job Card Tracking</div>
      <div class="ct">16 doctypes</div>
      <div class="ls">Customer Product Specification · Job Card Carton / Computer Paper / ETR / Label · Job Traveller Run · Job Resource Consumption · Dies · Dies Order · Colour of Parts · Pantone Colour · Spot Colour · Carton Job Type UPS · ETR Plate Detail · ETR Print Reel Output</div>
    </div>
    <div class="module">
      <div class="ttl">Module 02</div>
      <div class="nm">PPC</div>
      <div class="ct">4 doctypes · 10 reports</div>
      <div class="ls">PPC Daily Plan + Item · PPC Production Actual + Item · Open Job Pool · Daily Plan Report · Production Actual Summary · Completed Awaiting Closure · Closed Jobs · Packing Pending · On Hold · Waste · Downtime · Carry-Forward Pending · Rejection/QC</div>
    </div>
    <div class="module">
      <div class="ttl">Module 03</div>
      <div class="nm">Production Log</div>
      <div class="ct">3 doctypes</div>
      <div class="ls">Production Entry · Production Schedule Line · Workstation Product Line Tag<br><br><i>This module is the "execution layer" leftovers — most of it was removed in the v3 reset; what survives is the stage ladder + per-line route tagging.</i></div>
    </div>
  </div>

  <h2>The carton job pipeline</h2>
  <p>One Customer Product Spec drives one Job Card which renders one multi-page traveller PDF. Traveller runs and resource consumption capture the floor reality. Daily Plan rolls multiple Job Cards into the day's schedule.</p>
  {PIPELINE_SVG}
  <p class="caption">Figure 1. The CPS → Job Card → Print Format pipeline, with Traveller / Resource child tables feeding the PPC layer.</p>

  <h2>The carton calculation chain (the hard bit)</h2>
  <ol>
    <li><b>Ply rules</b> — CPS fields toggle on <code>ply</code> (3 → layers 1-3, 5 → 1-5, SFK → 1-2) and on <code>product_type</code>.</li>
    <li><b>SFK UI</b> — the special-board UI for SFK ply types.</li>
    <li><b>Flap auto-calc</b> — Tray, 1-Flap, 2-Flap, 3-Flap, RSC geometry formulas in <code>vcl_calc_board_sizes_serial</code>.</li>
    <li><b>Board sizes</b> — planned + actual width × length, both planned by the spec and actual measured on-floor.</li>
    <li><b>Weight calc</b> — derived from board sizes + GSM per layer.</li>
    <li><b>Print format</b> — 4-6 pages: Job Card, Carton Layout (full-width die-cut SVG), Station Log (Jinja loop over Traveller Runs), Resources (planned vs actual + variance).</li>
  </ol>
  </div>
  {foot('VCL Production · VCL-DEV-PROD-001 · 28 May 2026')}
</section>"""

P_DEPLOY = f"""
<section class="page">
  {bar('VCL Production · The deployed UI', 'page 04 · 28 may 2026')}
  <div style="padding:0 6mm;">
  <h1>What you see at /app/vcl-production</h1>
  <p>Captured today against <code>https://vimitconverters.frappe.cloud</code> via Playwright with API-token auth.</p>

  {sb('VCL Production · workspace', '/app/vcl-production', SHOT_WORKSPACE, 'Top-level workspace. Customer Specifications (253 CPS + 80 Dies) + Job Card Tracking (Carton 19, Label 56, Computer Paper 35) + Daily Planning shortcuts. Sidebar pins the same links for one-click access from anywhere.')}

  {sb('PPC · workspace', '/app/ppc', SHOT_PPC, 'The PPC planning desk — Daily Plan + Production Actual at the top, then a 10-card report grid: Open Job Pool, Daily Plan Report, Production Actual Summary, Completed Awaiting Closure, Closed Jobs, Packing Pending, On Hold, Waste, Downtime, Rejection/QC, Carry-Forward Pending. Each is a saved query report.')}
  </div>
  {foot('VCL Production · VCL-DEV-PROD-001 · 28 May 2026')}
</section>"""

P_DEPLOY_2 = f"""
<section class="page">
  {bar('VCL Production · The deployed UI (cont.)', 'page 05 · 28 may 2026')}
  <div style="padding:0 6mm;">
  <h1>Lists you live in</h1>

  {sb('Customer Product Specification list', '/app/customer-product-specification', SHOT_CPS, 'Single doctype hosting all four product types. 253 records — CPT- (Computer Paper), CTN- (Carton), ETR-, LBL-SPEC- prefixes show the type. Status chip (Submitted / Cancelled / Draft) drives downstream Job Card creation. List view pinned to "Last Updated On".')}

  {sb('Job Card Carton list', '/app/job-card-carton', SHOT_CARTON, '19 carton job cards live. ID format JC-CORR-YYYY-NNNN. Columns: Print Type (Plain / Printed) + Job Status (Open / In Progress / Completed / Cancelled). The traveller PDF renders from this doctype.')}
  </div>
  {foot('VCL Production · VCL-DEV-PROD-001 · 28 May 2026')}
</section>"""

P_GEMBA = f"""
<section class="page">
  {bar('VCL Production · Reporting flows', 'page 06 · 28 may 2026')}
  <div style="padding:0 6mm;">
  <h1>The 17:00 Gemba flow</h1>
  <p>The end-of-day Gemba report is a per-job-card-type summary (closed, in-progress, on-hold, blocked) auto-generated at 17:00 EAT and pushed to Tanuj on Telegram. The Frappe Cloud site doesn't hold the Telegram bot token — n8n does — so the flow is intentionally split.</p>

  {GEMBA_FLOW_SVG}
  <p class="caption">Figure 2. The Gemba report path. Frappe builds the PDF, n8n owns the credentials and the multipart upload.</p>

  <div class="card">
    <h3 style="margin-top:0;">Implementation details</h3>
    <ul>
      <li><b>Scheduler:</b> 17:00 EAT entry in <code>production_log/hooks.py</code> calling <code>generate_eod_report</code>.</li>
      <li><b>Per-doctype profile</b> (<code>JCL_PROFILE</code>): different job-card schemas (e.g. ETR uses <code>status</code> + <code>delivery_date</code>; Carton/Label use <code>job_status</code>) get aliased in the SQL so one report template covers all four.</li>
      <li><b>Webhook:</b> <code>https://vcl-intranet.tailb2b755.ts.net/webhook/gemba-telegram</code> — n8n workflow <code>vclGembaTelegram001</code>.</li>
      <li><b>Token:</b> stays in n8n's environment (<code>$env</code> read inside the Code node). No Frappe site_config secret.</li>
      <li><b>Default chat:</b> <code>8566637123</code> (Tanuj). Override via site_config <code>gemba_chat_id</code> only if needed.</li>
    </ul>
  </div>

  <h2>What still blocks the flow on prod</h2>
  <table class="tbl">
    <thead><tr><th>Item</th><th>Why it matters</th></tr></thead>
    <tbody>
      <tr><td><code>site_config.telegram_bot_token</code></td><td>Required only for the legacy direct-Telegram path — now bypassed via n8n. Keep absent or remove.</td></tr>
      <tr><td><code>site_config.gemba_channel_chat_id</code></td><td>Optional. Defaults to Tanuj's personal chat if absent. Set if you want to push to a group instead.</td></tr>
    </tbody>
  </table>
  </div>
  {foot('VCL Production · VCL-DEV-PROD-001 · 28 May 2026')}
</section>"""

P_RECENT = f"""
<section class="page">
  {bar('VCL Production · Recent work', 'page 07 · 28 may 2026')}
  <div style="padding:0 6mm;">
  <h1>What we shipped in the last 30 days</h1>
  <p>Pulled from <code>CHANGELOG_DAILY.md</code> + git log. Only the load-bearing commits — for the full daily log read the file.</p>

  <div class="timeline">
    <div class="t-row"><div class="when">19 May</div><div class="what"><b>S1 + S2 deploy (build #5).</b> Job Traveller Run + Job Resource Consumption shipped as child doctypes; <code>print_type</code> + 5 readiness Check fields added across all four job-card types; Carton traveller print format redesigned with Jinja loops over the 8-station ladder; 14 Carton CPS records backfilled with print_type.</div></div>
    <div class="t-row"><div class="when">20 May</div><div class="what"><b>v7_1 patch silent-failure HOTFIX.</b> 2 workstation types (Slotting, Bundling) + 2 workstations (Slotter 01, Bundler 01) inserted manually after the patch's <code>try/except NameError</code> swallowed the failure. Resolved permanently in <code>v7_3.finish_carton_workstations</code> (idempotent).</div></div>
    <div class="t-row"><div class="when">20 May</div><div class="what"><b>Stage ladder + per-line route model.</b> 14 workstation types numbered 15-165 (resolves the 999 collision); 26 existing route tag rows + 7 new ones numbered with <code>process_number</code>. Codified in <code>v7_4</code>. The same station now has different positions in different product lines (Sheeting = step 1 of Trading, step 5 of Exercise Books).</div></div>
    <div class="t-row"><div class="when">20 May</div><div class="what"><b>EOD Gemba rewired to n8n.</b> <code>gemba.py</code> now POSTs <code>{{pdf_base64, filename, caption, chat_id}}</code> to the n8n webhook; <code>_resolve_telegram_credentials</code> and <code>/etc/vcl/telegram.env</code> fallback removed. Bot token stays in n8n.</div></div>
    <div class="t-row"><div class="when">21 May</div><div class="what"><b>Notebook 32 — Carton CPS review.</b> 5-point review from Tanuj's reMarkable: board_type hidden, printing_or_plain retired, GSM-by-ply toggles, packing section hidden for Carton, Carton Layout moved to its own page in the traveller. 16 Property Setters + print_type reposition codified in <code>v7_5.notebook_32_carton_review</code>.</div></div>
    <div class="t-row"><div class="when">21 May</div><div class="what"><b>Print format → Chrome PDF generator.</b> wkhtmltopdf ignored per-page orientation + collapsed the no-viewBox SVG. Carton print format flipped to <code>pdf_generator = chrome</code> (per-format field, not site-wide). Spurious blank pages fixed; landscape NOT achievable (Frappe site-wide <code>pdf_page_size</code> overrides CSS).</div></div>
    <div class="t-row"><div class="when">22-27 May</div><div class="what"><b>Carton geometry + Job Card UI cleanup.</b> 8 commits — full-width die-cut SVG via Jinja viewBox injection, Carton Layout page added (planned + actual board sizes), <code>board_type</code> fully deleted from CPS (not hidden), <code>allow_on_submit</code> on <code>standard_packing</code> + <code>standard_weight_per_carton</code> (so they're editable after submit).</div></div>
    <div class="t-row"><div class="when">28 May</div><div class="what"><b>ETR print-type snapshot fix.</b> <code>etr_print_type</code> snapshot was blocking all Job Card ETR saves — dropped (commit <code>d87988f</code>).</div></div>
  </div>
  </div>
  {foot('VCL Production · VCL-DEV-PROD-001 · 28 May 2026')}
</section>"""

P_OPEN = f"""
<section class="page">
  {bar('VCL Production · Open items', 'page 08 · 28 may 2026')}
  <div style="padding:0 6mm;">
  <h1>What's still open</h1>
  <p>Direct from the TODO blocks in <code>CHANGELOG_DAILY.md</code> + the patch backlog. Owner-tagged where known.</p>

  <h2>Floor / data</h2>
  <table class="tbl">
    <thead><tr><th>Item</th><th>What it blocks</th><th class="who" style="width:120px;">Owner</th></tr></thead>
    <tbody>
      <tr><td><b>Hamada 01 reclassification</b></td><td>Currently tagged <code>Reel to Reel Printing</code>; likely <code>Sheet to Sheet Printing</code>. Wrong tag puts the press in the wrong route order on every Job Card.</td><td class="who">Tanuj</td></tr>
      <tr><td><b>Sheet-to-Sheet Printing exception tag</b></td><td>The <code>Corrugation and Carton Department</code> tag on S2S Printing has no <code>process_number</code> (offset-printed carton exception). Decide keep / drop.</td><td class="who">Tanuj</td></tr>
      <tr><td><b>Floor: rename Slotter 01 / Bundler 01</b></td><td>Generic placeholders. Need actual equipment IDs after the S3 install.</td><td class="who">Floor</td></tr>
    </tbody>
  </table>

  <h2>Print format / PDF</h2>
  <table class="tbl">
    <thead><tr><th>Item</th><th>What it blocks</th><th class="who" style="width:120px;">Owner</th></tr></thead>
    <tbody>
      <tr><td><b>Carton Layout landscape page</b></td><td>Frappe forces page size from site-wide Print Settings — CSS <code>@page</code> orientation is overridden. True landscape only via site-wide flip (touches every print format). Carton box renders portrait, full-width upright today — adequate but not ideal.</td><td class="who">Claude / Codex</td></tr>
      <tr><td><b>Station Log overflow page</b></td><td>Chrome generator improved page-break behaviour but the traveller still spills to 6 pages on dense jobs. Acceptable but could be tightened with row-height + page-break-inside fences.</td><td class="who">Claude / Codex</td></tr>
    </tbody>
  </table>

  <h2>System / config</h2>
  <table class="tbl">
    <thead><tr><th>Item</th><th>What it blocks</th><th class="who" style="width:120px;">Owner</th></tr></thead>
    <tbody>
      <tr><td><b>EOD Gemba on prod</b></td><td>Code is live; n8n webhook + token are live and verified. Site config keys (<code>telegram_bot_token</code>, <code>gemba_channel_chat_id</code>) optional but recommend at minimum confirming the default chat ID.</td><td class="who">Tanuj</td></tr>
      <tr><td><b>v7_2 follow-up patch</b></td><td>Daily-log mentions a follow-up to clean up after v7_1's silent failure. v7_3 covers the workstation create; check if anything else lingers.</td><td class="who">Claude</td></tr>
    </tbody>
  </table>

  <h2>Bigger questions</h2>
  <div class="qa"><b>Q1.</b> Production-execution layer — removed in v3. Was the new traveller + resource model enough, or do we need a slim version of Daily Production Log / Production Entry back (e.g. for cumulative WIP across days)?</div>
  <div class="qa"><b>Q2.</b> Carton job-card releases — the 5 readiness Check fields (plate_ready, material_in_stock, customer_hold, artwork_approved, plates_lead_time_clear) are on every job-card type but nothing gates submit on them yet. Should they gate submit, or just be informational in a Release Plan view?</div>
  <div class="qa"><b>Q3.</b> Carton ply-7 / ply-9 — current GSM toggles handle 3, 5, SFK. Anything heavier needed for export packaging?</div>
  <div class="qa"><b>Q4.</b> Should the PPC reports live on a dashboard (single page, side-by-side charts) instead of separate report URLs?</div>
  </div>
  {foot('VCL Production · VCL-DEV-PROD-001 · 28 May 2026')}
</section>"""

P_NEXT = f"""
<section class="page">
  {bar('VCL Production · What comes next', 'page 09 · 28 may 2026')}
  <div style="padding:0 6mm;">
  <h1>What comes next</h1>

  <h2>This week (29-30 May)</h2>
  <table class="tbl">
    <thead><tr><th class="who" style="width:140px;">Owner</th><th>Action</th><th class="when">By</th></tr></thead>
    <tbody>
      <tr><td class="who">Tanuj</td><td>Confirm Hamada 01 reclassification — is it Sheet-to-Sheet or Reel-to-Reel Printing? Direct MCP fix takes 30 seconds.</td><td class="when">29 May</td></tr>
      <tr><td class="who">Tanuj</td><td>Decide on the Sheet-to-Sheet Printing exception tag (keep with no process_number / drop).</td><td class="when">29 May</td></tr>
      <tr><td class="who">Tanuj</td><td>Confirm site_config for the EOD Gemba flow. End-to-end smoke test from cron → reMarkable.</td><td class="when">30 May</td></tr>
      <tr><td class="who">Claude</td><td>Write a v7_6 patch to drop the orphan <code>etr_print_type</code> column (already removed from JSON; HOTFIX commit <code>d87988f</code> on main).</td><td class="when">30 May</td></tr>
    </tbody>
  </table>

  <h2>June</h2>
  <table class="tbl">
    <thead><tr><th class="who" style="width:140px;">Owner</th><th>Action</th><th class="when">By</th></tr></thead>
    <tbody>
      <tr><td class="who">Tanuj</td><td>Decide on the readiness-flag gating (Q2 above). Either ship as form-level <code>depends_on</code> or build a Release Plan view.</td><td class="when">3 Jun</td></tr>
      <tr><td class="who">Claude / Codex</td><td>Build the Release Plan dashboard if Q2 lands as "yes, build it".</td><td class="when">7 Jun</td></tr>
      <tr><td class="who">Floor</td><td>Rename Slotter 01 / Bundler 01 to actual equipment IDs after S3 install.</td><td class="when">post-S3</td></tr>
      <tr><td class="who">Claude / Codex</td><td>Carton Layout landscape — only if Tanuj wants to absorb the site-wide flip. Otherwise the current portrait full-width carton box stays.</td><td class="when">tbd</td></tr>
    </tbody>
  </table>

  <h2>Outside this app but adjacent</h2>
  <ul>
    <li><b>EOD reports</b> — the Gemba report is one. The same pattern (Frappe → n8n → Telegram/Slack) could be reused for the PPC Daily Plan summary, Open Job Pool digest, etc.</li>
    <li><b>The VCL PMO System (sister project)</b> is now the home for cross-project planning — production change requests beyond a daily-log entry can go through the PMO Plans / Shifts loop. The link is already there in the workspace sidebar.</li>
  </ul>

  <div class="signature">
    <div><div class="slot">&nbsp;</div><div>Tanuj Haria — Sponsor</div></div>
    <div><div class="slot">&nbsp;</div><div>Date</div></div>
  </div>
  </div>
  {foot('VCL Production · VCL-DEV-PROD-001 · 28 May 2026')}
</section>"""

HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>VCL Production — Status Report</title>
<style>{CSS
  .replace('__MR_400__', MR_400).replace('__MR_600__', MR_600)
  .replace('__MR_700__', MR_700).replace('__MR_800__', MR_800)
  .replace('__JB_400__', JB_400).replace('__JB_700__', JB_700)
}</style>
</head>
<body>
{COVER}
{P_STATUS}
{P_ARCH}
{P_DEPLOY}
{P_DEPLOY_2}
{P_GEMBA}
{P_RECENT}
{P_OPEN}
{P_NEXT}
</body>
</html>
"""

out = REPO / 'briefs/VCL-DEV-PROD-001_status_report.html'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(HTML)
print(f'wrote {out} ({len(HTML):,} bytes)')
