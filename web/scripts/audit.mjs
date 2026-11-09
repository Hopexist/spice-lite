// Audit of the built site (run `npm run build` and `npx vite preview --port 4173` first):
// every bundled example through the real worker, console errors, and first-load transfer size.
import fs from "node:fs";
import { chromium } from "@playwright/test";
const url = process.argv[2] ?? "http://localhost:4173/";
const names = fs.readdirSync("../examples").filter((f) => f.endsWith(".cir")).map((f) => f.slice(0, -4));
const browser = await chromium.launch({ channel: process.env.PW_CHANNEL });
const page = await (await browser.newContext()).newPage();
const problems = [];
let bytes = 0;
page.on("console", (m) => m.type() === "error" && problems.push(`console: ${m.text()}`));
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
page.on("response", async (r) => { if (r.status() >= 400) problems.push(`HTTP ${r.status()} ${r.url()}`); try { bytes += (await r.body()).length; } catch {} });
const t0 = Date.now();
await page.goto(url + "#ex=" + names[0]);
await page.waitForSelector(".tab", { timeout: 180000 });
console.log(`first results ${Date.now() - t0} ms, ${(bytes / 1e6).toFixed(1)} MB transferred (incl. Pyodide, numpy, scipy)`);
for (const n of names) {
  const t = Date.now();
  await page.selectOption("#examples", n);
  await page.waitForFunction((x) => document.querySelector("#examples").value === x && !document.querySelector("#run").disabled, n);
  await page.waitForSelector(".tab, .msg.err", { timeout: 60000 });
  const err = await page.locator(".msg.err").count();
  console.log(`${err ? "ERROR" : "ok   "} ${n} ${Date.now() - t} ms`);
  if (err) problems.push(`${n}: ${await page.locator(".msg.err").innerText()}`);
}
console.log(problems.length ? "PROBLEMS:\n" + problems.join("\n") : "no problems");
await browser.close();
process.exit(problems.length ? 1 : 0);
