// Build the spicelite wheel that the browser unpacks into Pyodide: public/wheels/spicelite.whl.
// Pure Python, no dependencies installed (numpy and scipy come from Pyodide itself).
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..", "..");
const out = path.resolve(here, "..", "public", "wheels");
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "spicelite-wheel-"));
const python = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
execFileSync(python, ["-m", "pip", "wheel", root, "--no-deps", "-q", "-w", tmp], { stdio: "inherit" });
const wheel = fs.readdirSync(tmp).find((f) => f.endsWith(".whl"));
if (!wheel) throw new Error("pip produced no wheel");
fs.mkdirSync(out, { recursive: true });
fs.copyFileSync(path.join(tmp, wheel), path.join(out, "spicelite.whl"));
fs.writeFileSync(path.join(out, "version.json"), JSON.stringify({ wheel }));
fs.rmSync(tmp, { recursive: true, force: true });
console.log(`built ${wheel} -> public/wheels/spicelite.whl`);