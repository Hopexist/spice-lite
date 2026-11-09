import { chromium } from "@playwright/test";
const url = process.argv[2], out = process.argv[3];
const b64 = (s) => Buffer.from(s, "utf8").toString("base64url");
const browser = await chromium.launch({ channel: "msedge" });
const errors = [];
async function shoot(name, viewport, scheme, hash, after) {
  const ctx = await browser.newContext({ viewport, colorScheme: scheme });
  const page = await ctx.newPage();
  page.on("console", (m) => m.type() === "error" && errors.push(`${name}: ${m.text()}`));
  page.on("pageerror", (e) => errors.push(`${name}: pageerror ${e.message}`));
  await page.goto(url + hash);
  await page.waitForSelector(".tab, .msg.err", { timeout: 120000 });
  await page.waitForTimeout(600);
  if (after) await after(page);
  await page.screenshot({ path: `${out}/${name}.png` });
  await ctx.close();
}
await shoot("s-op", { width: 1440, height: 900 }, "dark", "#ex=divider");
await shoot("s-tran", { width: 1440, height: 900 }, "light", "#ex=stiff_adaptive");
await shoot("s-error", { width: 1440, height: 900 }, "light", "#n=" + b64("Broken netlist\nV1 in 0 DC 1\nR1 in out\nC1 out 0 1u\n.op\n"));
await shoot("s-table", { width: 1440, height: 900 }, "dark", "#ex=rc_step", async (p) => { await p.click("text=Table"); await p.waitForTimeout(300); });
await shoot("s-mobile-light", { width: 360, height: 900 }, "light", "#ex=nmos_iv");
console.log(errors.length ? errors.join("\n") : "no console errors");
await browser.close();
