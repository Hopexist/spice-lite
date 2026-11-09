import { defineConfig } from "@playwright/test";

// Serves the built site with `vite preview`. Locally set PW_CHANNEL=msedge (or chrome) to use an installed browser;
// CI installs Playwright's own Chromium.
export default defineConfig({
  testDir: "e2e",
  timeout: 240_000,
  expect: { timeout: 150_000 }, // the first run of a page boots Python, numpy and scipy from the CDN
  retries: 0,
  reporter: "list",
  use: { baseURL: "http://localhost:4173/", channel: process.env.PW_CHANNEL || undefined },
  webServer: { command: "npx vite preview --port 4173 --strictPort", url: "http://localhost:4173/", reuseExistingServer: true, timeout: 60_000 },
});