// Brand assets from their SVG sources: PNG favicons (32 px, 180 px Apple touch icon) and a brand sheet for review
// (mark at size, at 32 and 16 px on paper and on dark, the wordmark, palette with measured contrast, type specimen).
// node scripts/brand.mjs        (run from web/; needs the Archivo and JetBrains Mono font packages)
import fs from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";

const pub = path.resolve("public");
const out = path.resolve("../docs/brand");
fs.mkdirSync(out, { recursive: true });
const svg = (f) => fs.readFileSync(path.join(pub, f), "utf8");
const data = (f) => "data:image/svg+xml;base64," + Buffer.from(svg(f)).toString("base64");
const font = (family, pkg, w) =>
  `@font-face{font-family:"${family}";font-weight:${w};src:url(data:font/woff2;base64,${fs.readFileSync(path.resolve("node_modules/@fontsource", pkg, "files", `${pkg}-latin-${w}-normal.woff2`)).toString("base64")})}`;
const fonts = [400, 600, 700].map((w) => font("Archivo", "archivo", w)).join("") + [400, 600].map((w) => font("JetBrains Mono", "jetbrains-mono", w)).join("");

// WCAG 2.x relative luminance contrast
const lum = (hex) => {
  const c = hex.match(/\w\w/g).map((h) => parseInt(h, 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
};
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return ((x + 0.05) / (y + 0.05)).toFixed(1); };

const PALETTE = [
  ["Ink", "#111316", "text, axes, rules"], ["Paper", "#ffffff", "ground"], ["Signal", "#0b4f9c", "Run, focus, selection, the curve"],
  ["Graphite", "#555b63", "secondary text"], ["Rule", "#b9bec6", "hairlines"], ["Fault", "#a31919", "errors"],
  ["Night", "#0e1013", "dark ground"], ["Night ink", "#e8eaed", "dark text"], ["Night signal", "#7cb2ff", "dark Run, focus"],
];
const swatches = PALETTE.map(([n, h, use]) => {
  const ground = n.startsWith("Night") ? "#0e1013" : "#ffffff";
  const ink = lum(h) > 0.4 ? "#111316" : "#ffffff";
  return `<div class="sw" style="background:${h};color:${ink}"><b>${n}</b><span>${h}</span><span>${use}</span><span>${h === ground ? "ground" : ratio(h, ground) + ":1 on " + (ground === "#ffffff" ? "paper" : "night")}</span></div>`;
}).join("");

const html = `<style>${fonts}
body{margin:0;padding:32px;font:14px Archivo;color:#111316;background:#fff;width:1180px}
h2{font:700 13px Archivo;margin:28px 0 10px;border-bottom:1px solid #111316;padding-bottom:4px}
.row{display:flex;gap:24px;align-items:center}.tile{padding:14px;border:1px solid #b9bec6}
.dark{background:#0e1013}.wm{font:700 64px/1 Archivo;letter-spacing:-0.02em}.wm i{font-style:normal;color:#0b4f9c}
.sw{width:118px;height:118px;padding:8px;display:flex;flex-direction:column;gap:2px;font-size:11px;border:1px solid #b9bec6}
.mono{font-family:"JetBrains Mono"}</style>
<div class="row"><img src="${data("brand/mark.svg")}" width="160"><div><div class="wm">spice<i>·</i>lite</div>
<p style="max-width:520px">Mechanism: every result is a figure you could print in a datasheet. The mark is Figure 1, an RC step response on its axes, the first curve spice-lite was checked against. The wordmark's node dot is the same Signal blue as the curve.</p></div></div>
<h2>Small sizes (favicon cut)</h2><div class="row">
<div class="tile"><img src="${data("favicon.svg")}" width="32"> <img src="${data("favicon.svg")}" width="16"></div>
<div class="tile dark"><img src="${data("favicon.svg")}" width="32"> <img src="${data("favicon.svg")}" width="16"></div>
<div class="tile"><img src="${data("brand/mark.svg")}" width="32"> <img src="${data("brand/mark.svg")}" width="16"></div></div>
<h2>Palette (contrast measured, WCAG 2.x)</h2><div class="row" style="flex-wrap:wrap;gap:8px">${swatches}</div>
<h2>Type</h2><div style="font:700 32px Archivo">Archivo 700: Figure 2. Magnitude (dB)</div>
<div style="font:600 18px Archivo">Archivo 600: Run, Copy link, Download CSV</div><div style="font:400 15px Archivo">Archivo 400: The simulator is Python running in your browser; nothing is uploaded.</div>
<div class="mono" style="font-size:15px;margin-top:6px">JetBrains Mono 400: V1 in 0 DC 1 AC 1 · R1 in out 1k · .ac dec 20 10 100k</div>
<div class="mono" style="font-weight:600;font-size:15px">JetBrains Mono 600: -3.0103 dB at 1.0000 kHz</div>`;

const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || "msedge" });
const page = await browser.newPage({ viewport: { width: 1244, height: 800 } });
await page.setContent(html);
await page.waitForTimeout(400);
await page.screenshot({ path: path.join(out, "brand-sheet.png"), fullPage: true });
for (const [size, file] of [[32, "favicon-32.png"], [180, "apple-touch-icon.png"]]) {
  const p = await browser.newPage({ viewport: { width: size, height: size } });
  await p.setContent(`<body style="margin:0"><img src="${data("favicon.svg")}" width="${size}" height="${size}" style="display:block">`);
  await p.screenshot({ path: path.join(pub, file), omitBackground: true });
}
await browser.close();
console.log("brand sheet and favicons written");
