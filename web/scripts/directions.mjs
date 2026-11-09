// Render design-direction prototypes: inject each CSS overlay (fonts embedded as data: URLs) into the built app and
// capture the main screen. node scripts/directions.mjs <url> <dir with *.css> <out dir>   (a preview server must run)
import fs from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";

const [url = "http://localhost:4173/", dir = "../docs/ui-directions", out = "../docs/ui-directions"] = process.argv.slice(2);
const FONTS = { "Archivo": "archivo", "JetBrains Mono": "jetbrains-mono", "Public Sans": "public-sans", "IBM Plex Mono": "ibm-plex-mono", "Geist Sans": "geist-sans", "Geist Mono": "geist-mono" };
const face = (family, pkg, w) => {
  const f = path.resolve("node_modules/@fontsource", pkg, "files", `${pkg}-latin-${w}-normal.woff2`);
  return fs.existsSync(f) ? `@font-face{font-family:"${family}";font-weight:${w};font-display:swap;src:url(data:font/woff2;base64,${fs.readFileSync(f).toString("base64")}) format("woff2")}` : "";
};
const fontCss = Object.entries(FONTS).flatMap(([fam, pkg]) => [400, 500, 600, 700].map((w) => face(fam, pkg, w))).join("\n");
const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || "msedge" });
for (const file of fs.readdirSync(dir).filter((f) => f.endsWith(".css"))) {
  const css = fs.readFileSync(path.join(dir, file), "utf8");
  const scheme = css.includes("color-scheme: dark") ? "dark" : "light";
  for (const [width, height] of [[1440, 900], [360, 780]]) {
    const page = await browser.newPage({ viewport: { width, height }, colorScheme: scheme, reducedMotion: "reduce" });
    await page.goto(url + "#ex=inv_amp");
    await page.addStyleTag({ content: fontCss + "\n" + css });
    await page.waitForSelector(".tab", { timeout: 180000 });
    await page.locator(".tab", { hasText: ".ac" }).first().click();
    await page.waitForSelector(".uplot canvas");
    await page.evaluate(() => window.dispatchEvent(new Event("resize")));
    await page.waitForTimeout(700);
    await page.screenshot({ path: path.join(out, `${file.replace(".css", "")}-${width}.png`) });
    await page.close();
  }
  console.log("rendered", file);
}
await browser.close();
