// Screenshot set for design reviews: node scripts/shots.mjs <url> <outdir>   (a preview server must be running)
// States: empty editor, example loaded, one tab per analysis type, error. Widths 360 and 1440, dark and light.
import fs from "node:fs";
import { chromium } from "@playwright/test";

const url = process.argv[2] ?? "http://localhost:4173/";
const out = process.argv[3] ?? "shots";
fs.mkdirSync(out, { recursive: true });
const b64 = (s) => Buffer.from(s, "utf8").toString("base64url");
const STATES = [
  ["empty", "#n=", null],
  ["example", "#ex=rc_lowpass", null],
  ["op", "#ex=inv_amp", ".op"],
  ["dc", "#ex=inv_amp", ".dc"],
  ["ac", "#ex=inv_amp", ".ac"],
  ["tran", "#ex=rc_step", ".tran"],
  ["error", "#n=" + b64("Broken\nV1 in 0 DC 1\nR1 in out\nC1 out 0 1n\n.op\n"), null],
];
const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || "msedge" });
const problems = [];
let firstLoad = null;
for (const theme of ["dark", "light"]) {
  for (const width of [1440, 360]) {
    const ctx = await browser.newContext({ viewport: { width, height: width > 400 ? 900 : 780 }, colorScheme: theme, reducedMotion: "reduce" });
    const page = await ctx.newPage();
    page.on("console", (m) => m.type() === "error" && problems.push(`${theme}/${width}: ${m.text()}`));
    page.on("pageerror", (e) => problems.push(`${theme}/${width}: ${e.message}`));
    for (const [name, hash, tab] of STATES) {
      const t0 = Date.now();
      await page.goto(url + hash);
      await page.waitForSelector(".tab, .msg.err", { timeout: 180000 });
      if (firstLoad === null) firstLoad = Date.now() - t0;
      if (tab) await page.locator(".tab", { hasText: tab }).first().click();
      await page.waitForTimeout(400);
      await page.screenshot({ path: `${out}/${name}-${width}-${theme}.png`, fullPage: width < 400 });
    }
    await ctx.close();
  }
}
console.log(`first results after ${firstLoad} ms (cold browser cache for the first state)`);
console.log(problems.length ? problems.join("\n") : "no console errors");
await browser.close();
