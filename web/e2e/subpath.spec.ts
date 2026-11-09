// The built site must work when served from a sub-path (GitHub Pages serves it from /spice-lite/).
import fs from "node:fs";
import http from "node:http";
import type { AddressInfo } from "node:net";
import path from "node:path";
import { expect, test } from "@playwright/test";

const dist = path.resolve("dist");
const TYPES: Record<string, string> = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".json": "application/json", ".whl": "application/zip", ".woff2": "font/woff2", ".woff": "font/woff", ".svg": "image/svg+xml" };
let server: http.Server;
let origin = "";

test.beforeAll(async () => {
  if (!fs.existsSync(path.join(dist, "index.html"))) throw new Error("dist/ is missing: run `npm run build` first");
  server = http.createServer((req, res) => {
    const url = new URL(req.url ?? "/", "http://x");
    if (!url.pathname.startsWith("/spice-lite/")) return void res.writeHead(404).end("not under /spice-lite/");
    const rel = url.pathname.slice("/spice-lite/".length) || "index.html";
    const file = path.join(dist, rel.endsWith("/") ? rel + "index.html" : rel);
    if (!file.startsWith(dist) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) return void res.writeHead(404).end("missing");
    res.writeHead(200, { "content-type": TYPES[path.extname(file)] ?? "application/octet-stream" }).end(fs.readFileSync(file));
  });
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  origin = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});
test.afterAll(() => server.close());

test("from /spice-lite/ the page, worker, wheel, fonts and reference data all load", async ({ page }) => {
  const missing: string[] = [];
  page.on("response", (r) => r.url().startsWith(origin) && r.status() >= 400 && missing.push(`${r.status()} ${r.url()}`));
  page.on("pageerror", (e) => missing.push(`pageerror ${e.message}`));
  await page.goto(`${origin}/spice-lite/#ex=rc_lowpass`);
  await expect(page.locator(".uplot canvas").first()).toBeVisible();
  await expect(page.locator("input[type=checkbox]")).toBeVisible(); // reference/rc_lowpass.json was fetched relative to the sub-path
  expect(missing).toEqual([]);
});