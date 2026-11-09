// Headless smoke + screenshots against a running preview server: node scripts/shoot.mjs <url> <outdir>
import { chromium } from "@playwright/test";
const url = process.argv[2] ?? "http://localhost:4173/";
const out = process.argv[3] ?? ".";
const browser = await chromium.launch({ channel: "msedge" });
const errors = [];
async function shoot(name, viewport, scheme, hash = "") {
  const ctx = await browser.newContext({ viewport, colorScheme: scheme, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.on("console", (m) => m.type() === "error" && errors.push(`${name}: console: ${m.text()}`));
  page.on("pageerror", (e) => errors.push(`${name}: pageerror: ${e.message}`));
  const t0 = Date.now();
  await page.goto(url + hash);
  await page.waitForSelector(".tab", { timeout: 120000 });
  await page.waitForTimeout(800);
  console.log(name, "first results after", Date.now() - t0, "ms");
  await page.screenshot({ path: `${out}/${name}.png` });
  await ctx.close();
}
await shoot("desktop-dark", { width: 1440, height: 900 }, "dark");
await shoot("desktop-light", { width: 1440, height: 900 }, "light");
await shoot("mobile-dark", { width: 360, height: 800 }, "dark");
console.log(errors.length ? errors.join("\n") : "no console errors");
await browser.close();
