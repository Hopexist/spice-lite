// README hero image: a bundled example running in the built site with the ngspice overlay on.
//   node scripts/hero.mjs <url> <out.png> [example] [theme]      (a preview server must be running)
import { chromium } from "@playwright/test";

const url = process.argv[2] ?? "http://localhost:4173/";
const out = process.argv[3] ?? "hero.png";
const example = process.argv[4] ?? "cmos_inverter_vtc";
const theme = process.argv[5] ?? "dark";
const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || "msedge" });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: theme, reducedMotion: "reduce" });
const page = await ctx.newPage();
const problems = [];
page.on("console", (m) => m.type() === "error" && problems.push(m.text()));
page.on("pageerror", (e) => problems.push(e.message));
await page.goto(`${url}#ex=${example}`);
await page.waitForSelector(".tab", { timeout: 120000 });
await page.locator(".check input[type=checkbox]").first().check(); // overlay the precomputed ngspice curves
await page.waitForTimeout(600);
await page.locator("#app").scrollIntoViewIfNeeded();
await page.evaluate(() => document.querySelector("#app")?.scrollIntoView({ block: "start" }));
await page.waitForTimeout(400);
await page.screenshot({ path: out });
console.log(problems.length ? problems.join("\n") : "no console errors", "->", out);
await browser.close();
