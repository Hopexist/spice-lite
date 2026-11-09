import { defineConfig } from "vitest/config";

// base "./" makes every asset URL relative, so the built site works from any sub-path
// (GitHub Pages serves it from /spice-lite/).
export default defineConfig({
  base: "./",
  build: { target: "es2022", sourcemap: false, chunkSizeWarningLimit: 700 },
  worker: { format: "es" },
  server: { fs: { allow: [".."] } },
  test: { environment: "node", include: ["tests/**/*.test.ts"], testTimeout: 60_000, hookTimeout: 600_000 },
});