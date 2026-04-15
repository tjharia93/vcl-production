import { useState } from "react";

const COLORS = {
  primary: "#2B3990",
  light: "#E8EAF6",
  fold: "#FF6B35",
  glue: "#4CAF50",
  stitch: "#D32F2F",
  cut: "#333333",
  face: "#C5CAE9",
  side: "#9FA8DA",
  top: "#7986CB",
  base: "#B39DDB",
  trayWall: "#81C784",
};

const JOINT_CONFIG = {
  "Gluing - Manual": { tabWidth: 30, label: "Glue Tab", color: COLORS.glue + "40", markerType: "glue" },
  "Gluing - Machine": { tabWidth: 30, label: "Glue Tab", color: COLORS.glue + "40", markerType: "glue" },
  Stitched: { tabWidth: 40, label: "Stitch Flap", color: COLORS.stitch + "30", markerType: "stitch" },
};

/* ─────────────────────────────────────────────────────────
   FORMULAS
   ───────────────────────────────────────────────────────── */
function calcFormulas(length, width, height, flap, jointType, productType) {
  const joint = JOINT_CONFIG[jointType] || JOINT_CONFIG["Stitched"];
  const tabWidth = joint.tabWidth;

  if (productType === "2 Flap RSC") {
    return {
      blankWidth: flap + height + flap,
      blankLength: 2 * length + 2 * width + tabWidth,
      blankWidthFormula: `Flap + Height + Flap = ${flap} + ${height} + ${flap}`,
      blankLengthFormula: `2L + 2W + ${joint.label} = ${2 * length} + ${2 * width} + ${tabWidth}`,
    };
  }
  if (productType === "1 Flap RSC") {
    return {
      blankWidth: height + flap,
      blankLength: 2 * length + 2 * width + tabWidth,
      blankWidthFormula: `Height + Flap = ${height} + ${flap}`,
      blankLengthFormula: `2L + 2W + ${joint.label} = ${2 * length} + ${2 * width} + ${tabWidth}`,
    };
  }
  if (productType === "Tray") {
    return {
      blankWidth: width + 2 * height,
      blankLength: length + 2 * height,
      blankWidthFormula: `Width + 2 x Height = ${width} + ${2 * height}`,
      blankLengthFormula: `Length + 2 x Height = ${length} + ${2 * height}`,
    };
  }
  return { blankWidth: 0, blankLength: 0, blankWidthFormula: "", blankLengthFormula: "" };
}

/* ─────────────────────────────────────────────────────────
   2-FLAP RSC DIE-CUT VIEW
   ───────────────────────────────────────────────────────── */
function TwoFlapRSC({ length, width, height, flap, jointType }) {
  const joint = JOINT_CONFIG[jointType];
  const tabWidth = joint.tabWidth;
  const totalW = tabWidth + length + width + length + width;
  const totalH = flap + height + flap;
  const scale = Math.min(0.42, 580 / totalW, 380 / totalH);
  const ox = 30, oy = 40;
  const svgW = totalW * scale + 70;
  const svgH = totalH * scale + 60;

  const panels = [
    { label: joint.label, x: 0, y: flap, w: tabWidth, h: height, color: joint.color, isTab: true },
    { label: `Side (${width}mm)`, x: tabWidth, y: flap, w: length, h: height, color: COLORS.side + "60" },
    { label: `Front (${length}mm)`, x: tabWidth + length, y: flap, w: width, h: height, color: COLORS.face + "80" },
    { label: `Side (${width}mm)`, x: tabWidth + length + width, y: flap, w: length, h: height, color: COLORS.side + "60" },
    { label: `Back (${length}mm)`, x: tabWidth + length + width + length, y: flap, w: width, h: height, color: COLORS.face + "80" },
  ];

  const flapSets = [];
  const xPositions = [tabWidth, tabWidth + length, tabWidth + length + width, tabWidth + length + width + length];
  const widths = [length, width, length, width];
  const flapColors = [COLORS.top + "35", COLORS.top + "50", COLORS.top + "35", COLORS.top + "50"];
  xPositions.forEach((x, i) => {
    flapSets.push({ x, y: 0, w: widths[i], h: flap, color: flapColors[i], label: "Top flap" });
    flapSets.push({ x, y: flap + height, w: widths[i], h: flap, color: flapColors[i], label: "Btm flap" });
  });

  const allPanels = [...panels, ...flapSets];
  const foldXPositions = [tabWidth, tabWidth + length, tabWidth + length + width, tabWidth + length + width + length];

  const stitchMarks = [];
  if (joint.markerType === "stitch") {
    const spacing = 25;
    const count = Math.floor(height / spacing);
    const startY = flap + (height - count * spacing) / 2;
    for (let i = 0; i <= count; i++) stitchMarks.push(startY + i * spacing);
  }

  return (
    <svg width={svgW} height={svgH} style={{ background: "#FAFAFA", border: "1px solid #ddd", borderRadius: 4 }}>
      {allPanels.map((p, i) => (
        <g key={i}>
          <rect x={ox + p.x * scale} y={oy + p.y * scale} width={p.w * scale} height={p.h * scale} fill={p.color} stroke={COLORS.cut} strokeWidth={1.5} />
          {p.w * scale > 36 && (
            <text x={ox + (p.x + p.w / 2) * scale} y={oy + (p.y + p.h / 2) * scale} textAnchor="middle" dominantBaseline="middle" fontSize={Math.min(11, p.w * scale * 0.13)} fill="#333" fontWeight="500">{p.label}</text>
          )}
        </g>
      ))}
      {foldXPositions.map((fx, i) => <line key={`fv${i}`} x1={ox + fx * scale} y1={oy} x2={ox + fx * scale} y2={oy + totalH * scale} stroke={COLORS.fold} strokeWidth={1.5} strokeDasharray="6,4" />)}
      {[flap, flap + height].map((fy, i) => <line key={`fh${i}`} x1={ox + tabWidth * scale} y1={oy + fy * scale} x2={ox + totalW * scale} y2={oy + fy * scale} stroke={COLORS.fold} strokeWidth={1} strokeDasharray="4,3" />)}
      {joint.markerType === "stitch" && stitchMarks.map((sy, i) => {
        const cx = ox + (tabWidth * 0.6) * scale, cy = oy + sy * scale;
        return <g key={`s${i}`}><line x1={cx-3} y1={cy-3} x2={cx+3} y2={cy+3} stroke={COLORS.stitch} strokeWidth={1.5}/><line x1={cx+3} y1={cy-3} x2={cx-3} y2={cy+3} stroke={COLORS.stitch} strokeWidth={1.5}/></g>;
      })}
      {joint.markerType === "glue" && [0.25, 0.5, 0.75].map((frac, i) => (
        <line key={`g${i}`} x1={ox + (tabWidth * 0.2) * scale} y1={oy + (flap + height * frac) * scale} x2={ox + (tabWidth * 0.8) * scale} y2={oy + (flap + height * frac) * scale} stroke={COLORS.glue} strokeWidth={2} strokeDasharray="3,2" opacity={0.6} />
      ))}
      {/* Dimension labels */}
      <text x={ox + (tabWidth + length / 2) * scale} y={oy + totalH * scale + 14} textAnchor="middle" fontSize={10} fill="#666">{length}mm</text>
      <text x={ox + (tabWidth + length + width / 2) * scale} y={oy + totalH * scale + 14} textAnchor="middle" fontSize={10} fill="#666">{width}mm</text>
      <text x={ox + totalW * scale + 6} y={oy + (flap + height / 2) * scale} textAnchor="start" dominantBaseline="middle" fontSize={10} fill="#666">{height}mm</text>
      <text x={ox + totalW * scale + 6} y={oy + (flap / 2) * scale} textAnchor="start" dominantBaseline="middle" fontSize={10} fill="#666">{flap}mm</text>
      <text x={ox + (tabWidth / 2) * scale} y={oy - 8} textAnchor="middle" fontSize={9} fill="#888">{tabWidth}mm</text>
      <line x1={ox} y1={oy + totalH * scale + 24} x2={ox + totalW * scale} y2={oy + totalH * scale + 24} stroke="#999" strokeWidth={0.5} />
      <text x={ox + (totalW / 2) * scale} y={oy + totalH * scale + 38} textAnchor="middle" fontSize={11} fill={COLORS.primary} fontWeight="600">Blank: {totalW}mm x {totalH}mm</text>
    </svg>
  );
}

/* ─────────────────────────────────────────────────────────
   1-FLAP RSC DIE-CUT VIEW
   Only one set of flaps (top). Bottom edge is open / sealed separately.
   ───────────────────────────────────────────────────────── */
function OneFlapRSC({ length, width, height, flap, jointType }) {
  const joint = JOINT_CONFIG[jointType];
  const tabWidth = joint.tabWidth;
  const totalW = tabWidth + length + width + length + width;
  const totalH = height + flap;
  const scale = Math.min(0.42, 580 / totalW, 380 / totalH);
  const ox = 30, oy = 40;
  const svgW = totalW * scale + 70;
  const svgH = totalH * scale + 60;

  const panels = [
    { label: joint.label, x: 0, y: 0, w: tabWidth, h: height, color: joint.color, isTab: true },
    { label: `Side (${width}mm)`, x: tabWidth, y: 0, w: length, h: height, color: COLORS.side + "60" },
    { label: `Front (${length}mm)`, x: tabWidth + length, y: 0, w: width, h: height, color: COLORS.face + "80" },
    { label: `Side (${width}mm)`, x: tabWidth + length + width, y: 0, w: length, h: height, color: COLORS.side + "60" },
    { label: `Back (${length}mm)`, x: tabWidth + length + width + length, y: 0, w: width, h: height, color: COLORS.face + "80" },
  ];

  const xPositions = [tabWidth, tabWidth + length, tabWidth + length + width, tabWidth + length + width + length];
  const widths = [length, width, length, width];
  const flapColors = [COLORS.top + "35", COLORS.top + "50", COLORS.top + "35", COLORS.top + "50"];
  const topFlaps = xPositions.map((x, i) => ({
    x, y: height, w: widths[i], h: flap, color: flapColors[i], label: "Flap"
  }));

  const allPanels = [...panels, ...topFlaps];
  const foldXPositions = [tabWidth, tabWidth + length, tabWidth + length + width, tabWidth + length + width + length];

  const stitchMarks = [];
  if (joint.markerType === "stitch") {
    const spacing = 25;
    const count = Math.floor(height / spacing);
    const startY = (height - count * spacing) / 2;
    for (let i = 0; i <= count; i++) stitchMarks.push(startY + i * spacing);
  }

  return (
    <svg width={svgW} height={svgH} style={{ background: "#FAFAFA", border: "1px solid #ddd", borderRadius: 4 }}>
      {allPanels.map((p, i) => (
        <g key={i}>
          <rect x={ox + p.x * scale} y={oy + p.y * scale} width={p.w * scale} height={p.h * scale} fill={p.color} stroke={COLORS.cut} strokeWidth={1.5} />
          {p.w * scale > 36 && (
            <text x={ox + (p.x + p.w / 2) * scale} y={oy + (p.y + p.h / 2) * scale} textAnchor="middle" dominantBaseline="middle" fontSize={Math.min(11, p.w * scale * 0.13)} fill="#333" fontWeight="500">{p.label}</text>
          )}
        </g>
      ))}
      {foldXPositions.map((fx, i) => <line key={`fv${i}`} x1={ox + fx * scale} y1={oy} x2={ox + fx * scale} y2={oy + totalH * scale} stroke={COLORS.fold} strokeWidth={1.5} strokeDasharray="6,4" />)}
      <line x1={ox + tabWidth * scale} y1={oy + height * scale} x2={ox + totalW * scale} y2={oy + height * scale} stroke={COLORS.fold} strokeWidth={1} strokeDasharray="4,3" />
      {/* Bottom edge label */}
      <text x={ox + (totalW / 2) * scale} y={oy - 10} textAnchor="middle" fontSize={9} fill="#999" fontStyle="italic">Open end (no flap)</text>
      {joint.markerType === "stitch" && stitchMarks.map((sy, i) => {
        const cx = ox + (tabWidth * 0.6) * scale, cy = oy + sy * scale;
        return <g key={`s${i}`}><line x1={cx-3} y1={cy-3} x2={cx+3} y2={cy+3} stroke={COLORS.stitch} strokeWidth={1.5}/><line x1={cx+3} y1={cy-3} x2={cx-3} y2={cy+3} stroke={COLORS.stitch} strokeWidth={1.5}/></g>;
      })}
      {joint.markerType === "glue" && [0.25, 0.5, 0.75].map((frac, i) => (
        <line key={`g${i}`} x1={ox + (tabWidth * 0.2) * scale} y1={oy + (height * frac) * scale} x2={ox + (tabWidth * 0.8) * scale} y2={oy + (height * frac) * scale} stroke={COLORS.glue} strokeWidth={2} strokeDasharray="3,2" opacity={0.6} />
      ))}
      <text x={ox + (tabWidth + length / 2) * scale} y={oy + totalH * scale + 14} textAnchor="middle" fontSize={10} fill="#666">{length}mm</text>
      <text x={ox + (tabWidth + length + width / 2) * scale} y={oy + totalH * scale + 14} textAnchor="middle" fontSize={10} fill="#666">{width}mm</text>
      <text x={ox + totalW * scale + 6} y={oy + (height / 2) * scale} textAnchor="start" dominantBaseline="middle" fontSize={10} fill="#666">{height}mm</text>
      <text x={ox + totalW * scale + 6} y={oy + (height + flap / 2) * scale} textAnchor="start" dominantBaseline="middle" fontSize={10} fill="#666">{flap}mm</text>
      <line x1={ox} y1={oy + totalH * scale + 24} x2={ox + totalW * scale} y2={oy + totalH * scale + 24} stroke="#999" strokeWidth={0.5} />
      <text x={ox + (totalW / 2) * scale} y={oy + totalH * scale + 38} textAnchor="middle" fontSize={11} fill={COLORS.primary} fontWeight="600">Blank: {totalW}mm x {totalH}mm</text>
    </svg>
  );
}

/* ─────────────────────────────────────────────────────────
   TRAY (FTD) DIE-CUT VIEW
   Cross/plus shape — base with four walls folding up, corner tabs.
   No joint/glue tab.
   ───────────────────────────────────────────────────────── */
function TrayFTD({ length, width, height }) {
  const cornerTab = Math.min(height, 30); // small ear tabs at corners
  const totalW = height + width + height;
  const totalH = height + length + height;
  const scale = Math.min(0.55, 500 / totalW, 420 / totalH);
  const ox = 30, oy = 30;
  const svgW = totalW * scale + 60;
  const svgH = totalH * scale + 60;

  // Central base
  const base = { x: height, y: height, w: width, h: length, color: COLORS.base + "50", label: `Base (${length} x ${width})` };

  // Four walls
  const walls = [
    { x: height, y: 0, w: width, h: height, color: COLORS.trayWall + "50", label: `Front wall (${height})` },
    { x: height, y: height + length, w: width, h: height, color: COLORS.trayWall + "50", label: `Back wall (${height})` },
    { x: 0, y: height, w: height, h: length, color: COLORS.trayWall + "35", label: `Side (${height})` },
    { x: height + width, y: height, w: height, h: length, color: COLORS.trayWall + "35", label: `Side (${height})` },
  ];

  // Corner ear tabs (small triangular/rectangular tabs for tucking)
  const ears = [
    { x: 0, y: 0, w: height, h: height },
    { x: height + width, y: 0, w: height, h: height },
    { x: 0, y: height + length, w: height, h: height },
    { x: height + width, y: height + length, w: height, h: height },
  ];

  const allPanels = [base, ...walls];

  return (
    <svg width={svgW} height={svgH} style={{ background: "#FAFAFA", border: "1px solid #ddd", borderRadius: 4 }}>
      {/* Corner ear tabs (diagonal cut) */}
      {ears.map((e, i) => {
        const sx = ox + e.x * scale, sy = ox + e.y * scale;
        const sw = e.w * scale, sh = e.h * scale;
        // Draw triangular ear tab
        let points;
        if (i === 0) points = `${sx},${sy + sh} ${sx + sw},${sy} ${sx + sw},${sy + sh}`;
        else if (i === 1) points = `${sx},${sy} ${sx + sw},${sy + sh} ${sx},${sy + sh}`;
        else if (i === 2) points = `${sx + sw},${sy} ${sx},${sy + sh} ${sx + sw},${sy + sh}`;                                                      // bottom-left: triangle top-right, bottom-left, bottom-right
        else points = `${sx},${sy} ${sx + sw},${sy} ${sx},${sy + sh}`;
        return <polygon key={`ear${i}`} points={points} fill="#E0E0E0" stroke={COLORS.cut} strokeWidth={1} strokeDasharray="3,3" />;
      })}

      {/* Main panels */}
      {allPanels.map((p, i) => (
        <g key={i}>
          <rect x={ox + p.x * scale} y={oy + p.y * scale} width={p.w * scale} height={p.h * scale} fill={p.color} stroke={COLORS.cut} strokeWidth={1.5} />
          {p.w * scale > 50 && p.h * scale > 20 && (
            <text x={ox + (p.x + p.w / 2) * scale} y={oy + (p.y + p.h / 2) * scale} textAnchor="middle" dominantBaseline="middle" fontSize={Math.min(11, Math.min(p.w, p.h) * scale * 0.15)} fill="#333" fontWeight="500">{p.label}</text>
          )}
        </g>
      ))}

      {/* Fold lines around base */}
      <line x1={ox + height * scale} y1={oy} x2={ox + height * scale} y2={oy + totalH * scale} stroke={COLORS.fold} strokeWidth={1.5} strokeDasharray="6,4" />
      <line x1={ox + (height + width) * scale} y1={oy} x2={ox + (height + width) * scale} y2={oy + totalH * scale} stroke={COLORS.fold} strokeWidth={1.5} strokeDasharray="6,4" />
      <line x1={ox} y1={oy + height * scale} x2={ox + totalW * scale} y2={oy + height * scale} stroke={COLORS.fold} strokeWidth={1.5} strokeDasharray="6,4" />
      <line x1={ox} y1={oy + (height + length) * scale} x2={ox + totalW * scale} y2={oy + (height + length) * scale} stroke={COLORS.fold} strokeWidth={1.5} strokeDasharray="6,4" />

      {/* Dimension labels */}
      <text x={ox + (height + width / 2) * scale} y={oy + totalH * scale + 14} textAnchor="middle" fontSize={10} fill="#666">{width}mm</text>
      <text x={ox + (height / 2) * scale} y={oy + totalH * scale + 14} textAnchor="middle" fontSize={10} fill="#666">{height}mm</text>
      <text x={ox + totalW * scale + 6} y={oy + (height + length / 2) * scale} textAnchor="start" dominantBaseline="middle" fontSize={10} fill="#666">{length}mm</text>
      <text x={ox + totalW * scale + 6} y={oy + (height / 2) * scale} textAnchor="start" dominantBaseline="middle" fontSize={10} fill="#666">{height}mm</text>

      <line x1={ox} y1={oy + totalH * scale + 24} x2={ox + totalW * scale} y2={oy + totalH * scale + 24} stroke="#999" strokeWidth={0.5} />
      <text x={ox + (totalW / 2) * scale} y={oy + totalH * scale + 38} textAnchor="middle" fontSize={11} fill={COLORS.primary} fontWeight="600">Blank: {totalW}mm x {totalH}mm</text>
      <line x1={ox - 10} y1={oy} x2={ox - 10} y2={oy + totalH * scale} stroke="#999" strokeWidth={0.5} />
      <text x={ox - 14} y={oy + (totalH / 2) * scale} textAnchor="middle" dominantBaseline="middle" fontSize={10} fill={COLORS.primary} fontWeight="600" transform={`rotate(-90, ${ox - 14}, ${oy + (totalH / 2) * scale})`}>{totalH}mm</text>
    </svg>
  );
}

/* ─────────────────────────────────────────────────────────
   MAIN COMPONENT
   ───────────────────────────────────────────────────────── */
export default function CartonVisualisation() {
  const [length, setLength] = useState(300);
  const [width, setWidth] = useState(200);
  const [height, setHeight] = useState(150);
  const [jointType, setJointType] = useState("Stitched");
  const [productType, setProductType] = useState("2 Flap RSC");

  const flap = Math.ceil((width + 5) / 2);
  const formulas = calcFormulas(length, width, height, flap, jointType, productType);
  const joint = JOINT_CONFIG[jointType] || JOINT_CONFIG["Stitched"];

  const inputStyle = { width: 80, padding: "6px 8px", border: "1px solid #ccc", borderRadius: 4, fontSize: 14, textAlign: "center" };
  const labelStyle = { fontSize: 13, fontWeight: 600, color: "#444", marginRight: 4 };

  return (
    <div style={{ fontFamily: "Arial, sans-serif", maxWidth: 960, margin: "0 auto", padding: 24 }}>
      <h2 style={{ color: COLORS.primary, borderBottom: `2px solid ${COLORS.primary}`, paddingBottom: 8, marginBottom: 4, fontSize: 20 }}>
        Carton Job Card — 2D Die-Cut View
      </h2>
      <p style={{ fontSize: 13, color: "#666", marginBottom: 20 }}>
        Flat blank layout showing panels, flaps, fold lines, and manufacturer's joint. Select product type to see the correct blank shape.
      </p>

      {/* Inputs */}
      <div style={{ display: "flex", gap: 16, marginBottom: 20, flexWrap: "wrap", alignItems: "center", background: COLORS.light, padding: "12px 16px", borderRadius: 6 }}>
        <div>
          <span style={labelStyle}>Type:</span>
          <select value={productType} onChange={(e) => setProductType(e.target.value)} style={{ ...inputStyle, width: 140, textAlign: "left" }}>
            <option>2 Flap RSC</option>
            <option>1 Flap RSC</option>
            <option>Tray</option>
          </select>
        </div>
        <div>
          <span style={labelStyle}>L:</span>
          <input type="number" value={length} onChange={(e) => setLength(Math.max(1, +e.target.value))} style={inputStyle} />
        </div>
        <div>
          <span style={labelStyle}>W:</span>
          <input type="number" value={width} onChange={(e) => setWidth(Math.max(1, +e.target.value))} style={inputStyle} />
        </div>
        <div>
          <span style={labelStyle}>H:</span>
          <input type="number" value={height} onChange={(e) => setHeight(Math.max(1, +e.target.value))} style={inputStyle} />
        </div>
        {productType !== "Tray" && (
          <div style={{ borderLeft: "1px solid #ccc", paddingLeft: 16 }}>
            <span style={labelStyle}>Joint:</span>
            <select value={jointType} onChange={(e) => setJointType(e.target.value)} style={{ ...inputStyle, width: 160, textAlign: "left" }}>
              <option>Stitched</option>
              <option>Gluing - Manual</option>
              <option>Gluing - Machine</option>
            </select>
          </div>
        )}
        {productType !== "Tray" && (
          <div style={{ fontSize: 13, color: "#666" }}>Flap: <strong>{flap}mm</strong></div>
        )}
      </div>

      {/* SVG visualisation */}
      {productType === "2 Flap RSC" && <TwoFlapRSC length={length} width={width} height={height} flap={flap} jointType={jointType} />}
      {productType === "1 Flap RSC" && <OneFlapRSC length={length} width={width} height={height} flap={flap} jointType={jointType} />}
      {productType === "Tray" && <TrayFTD length={length} width={width} height={height} />}

      {/* Calculation breakdown */}
      <div style={{ marginTop: 20, display: "flex", gap: 16, flexWrap: "wrap" }}>
        <div style={{ flex: "1 1 320px", padding: 16, background: "#F5F5F5", borderRadius: 6, borderLeft: `4px solid ${COLORS.primary}` }}>
          <h4 style={{ margin: "0 0 10px", color: COLORS.primary, fontSize: 14 }}>Board Plan — {productType}</h4>
          <table style={{ fontSize: 13, color: "#444", borderCollapse: "collapse", width: "100%" }}>
            <tbody>
              <tr>
                <td style={{ padding: "4px 0", fontWeight: 500, whiteSpace: "nowrap", paddingRight: 12 }}>Blank width (1-UP):</td>
                <td style={{ padding: "4px 0" }}>{formulas.blankWidthFormula} = <strong>{formulas.blankWidth}mm</strong></td>
              </tr>
              <tr>
                <td style={{ padding: "4px 0", fontWeight: 500, whiteSpace: "nowrap", paddingRight: 12 }}>Blank length (1-UP):</td>
                <td style={{ padding: "4px 0" }}>{formulas.blankLengthFormula} = <strong>{formulas.blankLength}mm</strong></td>
              </tr>
              {productType !== "Tray" && (
                <tr>
                  <td style={{ padding: "4px 0", fontWeight: 500, paddingRight: 12 }}>Flap formula:</td>
                  <td style={{ padding: "4px 0" }}>ceil((W + 5) / 2) = ceil(({width} + 5) / 2) = <strong>{flap}mm</strong></td>
                </tr>
              )}
            </tbody>
          </table>
          <div style={{ marginTop: 12, padding: "8px 12px", background: "#E3F2FD", borderRadius: 4, fontSize: 12, color: "#1565C0" }}>
            <strong>Planned Board Width</strong> = (Blank Width x UPS Across) + Knife Gap x (UPS Across - 1) + Trim Allowance Width<br/>
            <strong>Planned Board Length</strong> = (Blank Length x UPS Along) + Knife Gap x (UPS Along - 1) + Trim Allowance Length<br/>
            <strong>Approx Weight (g)</strong> = (Planned Width x Planned Length / 1,000,000) x Total GSM
          </div>
        </div>

        {productType !== "Tray" && (
          <div style={{ flex: "1 1 260px", padding: 16, background: jointType === "Stitched" ? "#FFEBEE" : "#E8F5E9", borderRadius: 6, borderLeft: `4px solid ${jointType === "Stitched" ? COLORS.stitch : COLORS.glue}` }}>
            <h4 style={{ margin: "0 0 10px", color: jointType === "Stitched" ? COLORS.stitch : COLORS.glue, fontSize: 14 }}>
              {jointType === "Stitched" ? "Stitched Joint" : "Glued Joint"}
            </h4>
            {jointType === "Stitched" ? (
              <div style={{ fontSize: 13, color: "#444", lineHeight: 1.7 }}>
                <p style={{ margin: "0 0 6px" }}>Flap width: <strong>40mm</strong></p>
                <p style={{ margin: "0 0 6px" }}>Wire stitches at ~25mm intervals</p>
                <p style={{ margin: 0 }}>Stitch points shown as <span style={{ color: COLORS.stitch, fontWeight: 700 }}>X</span> marks</p>
              </div>
            ) : (
              <div style={{ fontSize: 13, color: "#444", lineHeight: 1.7 }}>
                <p style={{ margin: "0 0 6px" }}>Tab width: <strong>30mm</strong></p>
                <p style={{ margin: "0 0 6px" }}>Adhesive applied in strips across the tab</p>
                <p style={{ margin: 0 }}>{jointType === "Gluing - Machine" ? "Machine-applied glue" : "Hand-applied glue"}</p>
              </div>
            )}
          </div>
        )}

        {productType === "Tray" && (
          <div style={{ flex: "1 1 260px", padding: 16, background: "#F1F8E9", borderRadius: 6, borderLeft: `4px solid ${COLORS.trayWall}` }}>
            <h4 style={{ margin: "0 0 10px", color: "#388E3C", fontSize: 14 }}>Tray (FTD) Notes</h4>
            <div style={{ fontSize: 13, color: "#444", lineHeight: 1.7 }}>
              <p style={{ margin: "0 0 6px" }}>No glue tab or joint — corners fold and tuck</p>
              <p style={{ margin: "0 0 6px" }}>Triangular ear tabs at corners provide rigidity</p>
              <p style={{ margin: "0 0 6px" }}>Walls fold up from flat blank to form tray</p>
              <p style={{ margin: 0 }}>No flap calculation — height IS the wall height</p>
            </div>
          </div>
        )}
      </div>

      {/* Legend */}
      <div style={{ marginTop: 16, display: "flex", gap: 20, flexWrap: "wrap", fontSize: 12, color: "#666" }}>
        <span><span style={{ display: "inline-block", width: 20, borderTop: `2px dashed ${COLORS.fold}`, marginRight: 4, verticalAlign: "middle" }}></span> Fold line</span>
        {productType !== "Tray" && <>
          <span><span style={{ display: "inline-block", width: 14, height: 14, background: COLORS.face + "80", border: "1px solid #999", marginRight: 4, verticalAlign: "middle" }}></span> Front/Back</span>
          <span><span style={{ display: "inline-block", width: 14, height: 14, background: COLORS.side + "60", border: "1px solid #999", marginRight: 4, verticalAlign: "middle" }}></span> Side</span>
          <span><span style={{ display: "inline-block", width: 14, height: 14, background: COLORS.top + "50", border: "1px solid #999", marginRight: 4, verticalAlign: "middle" }}></span> Flaps</span>
        </>}
        {productType === "Tray" && <>
          <span><span style={{ display: "inline-block", width: 14, height: 14, background: COLORS.base + "50", border: "1px solid #999", marginRight: 4, verticalAlign: "middle" }}></span> Base</span>
          <span><span style={{ display: "inline-block", width: 14, height: 14, background: COLORS.trayWall + "50", border: "1px solid #999", marginRight: 4, verticalAlign: "middle" }}></span> Walls</span>
          <span><span style={{ display: "inline-block", width: 14, height: 14, background: "#E0E0E0", border: "1px solid #999", marginRight: 4, verticalAlign: "middle" }}></span> Corner tabs</span>
        </>}
      </div>
    </div>
  );
}
