// Social preview card (Open Graph / Twitter / GitHub): 1200 x 630, built from the brand mark and a real plot in docs/.
//   node scripts/social.mjs [out.png]        -> web/public/social-preview.png by default
import fs from "node:fs";
import { chromium } from "@playwright/test";

const out = process.argv[2] ?? "public/social-preview.png";
const b64 = (path, mime) => `data:${mime};base64,${fs.readFileSync(path).toString("base64")}`;
const font = (name) => b64(`node_modules/@fontsource/${name}.woff2`.replace(".woff2", ".woff2"), "font/woff2");
const mark = fs.readFileSync("public/brand/mark.svg", "utf8").replace(/<svg /, '<svg width="84" height="84" ');
const plot = b64("../docs/wave_rc_step.png", "image/png");

const html = `<!doctype html><meta charset="utf-8"><style>
@font-face { font-family: Archivo; font-weight: 700; src: url(${font("archivo/files/archivo-latin-700-normal")}) }
@font-face { font-family: Archivo; font-weight: 400; src: url(${font("archivo/files/archivo-latin-400-normal")}) }
@font-face { font-family: Mono; font-weight: 400; src: url(${font("jetbrains-mono/files/jetbrains-mono-latin-400-normal")}) }
* { box-sizing: border-box; margin: 0 }
body { width: 1200px; height: 630px; background: #fff; color: #111316; font-family: Archivo, sans-serif; display: grid; grid-template-columns: 640px 1fr; border: 14px solid #111316 }
.left { padding: 52px 40px 44px 56px; display: flex; flex-direction: column; justify-content: space-between }
.brand { display: flex; align-items: center; gap: 22px }
h1 { font-size: 64px; letter-spacing: -1.5px; line-height: 1 }
h1 span { color: #0b4f9c }
.tag { font-size: 38px; line-height: 1.15; font-weight: 700; letter-spacing: -0.6px }
.facts { font-family: Mono, monospace; font-size: 22px; line-height: 1.55; border-top: 3px solid #111316; padding-top: 18px }
.facts b { color: #0b4f9c; font-weight: 400 }
.right { padding: 44px 44px 36px 0; display: flex; flex-direction: column; justify-content: center }
.fig { border: 2px solid #111316; padding: 8px; background: #fff }
.fig img { width: 100%; display: block }
.cap { font-family: Mono, monospace; font-size: 17px; margin-top: 10px }
</style>
<div class="left">
  <div class="brand">${mark}<h1>spice<span>·</span>lite</h1></div>
  <p class="tag">A SPICE circuit simulator that runs in your browser.</p>
  <p class="facts">DC · AC · transient · diodes · MOSFETs<br><b>checked against ngspice 41</b><br>Python in WebAssembly · nothing uploaded</p>
</div>
<div class="right"><div class="fig"><img src="${plot}"></div><p class="cap">Figure 1. RC pulse response: spicelite vs ngspice, with the error curve.</p></div>`;

const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || "msedge" });
const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
await page.setContent(html);
await page.evaluate(() => document.fonts.ready);
await page.screenshot({ path: out });
await browser.close();
console.log("wrote", out);
