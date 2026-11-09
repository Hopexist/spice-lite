// The real thing, headless: boot Pyodide in Node, install the spicelite wheel exactly as the browser worker does,
// run every bundled example through spicelite.web_api, and compare with the committed ngspice reference curves.
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { loadPyodide, type PyodideInterface } from "pyodide";
import { beforeAll, describe, expect, it } from "vitest";
import { EXAMPLES } from "../src/examples";
import { maxDiff, resample, type RefFile } from "../src/reference";
import type { RunResult } from "../src/types";

const path = (rel: string) => fileURLToPath(new URL(rel, import.meta.url));
let py: PyodideInterface;
const run = (text: string, options: object = {}): RunResult => {
  py.globals.set("_netlist", text);
  py.globals.set("_options", JSON.stringify(options));
  return JSON.parse(py.runPython("json.dumps(run_netlist(_netlist, json.loads(_options)), allow_nan=False)"));
};

beforeAll(async () => {
  const wheel = path("../public/wheels/spicelite.whl");
  if (!fs.existsSync(wheel)) throw new Error("public/wheels/spicelite.whl is missing: run `npm run wheel` first (npm test does)");
  py = await loadPyodide();
  await py.loadPackage(["numpy", "scipy"]);
  py.unpackArchive(new Uint8Array(fs.readFileSync(wheel)), "wheel");
  py.runPython("import json, sys\nfrom spicelite.web_api import run_netlist");
}, 600_000);

describe("spicelite inside Pyodide", () => {
  it("runs on Python 3.14 without importing matplotlib or the ngspice runner", () => {
    expect(py.runPython("sys.version.split()[0]")).toMatch(/^3\.1[0-9]/);
    run("t\nV1 a 0 DC 1\nR1 a 0 1k\n.op\n");
    expect(py.runPython("[m for m in ('matplotlib', 'spicelite.plotting', 'spicelite.ngspice', 'spicelite.cli') if m in sys.modules]").toJs()).toEqual([]);
  });

  it("matches the native result for the RC lowpass to the digit (-0.000434 dB at 10 Hz, -40.0004 dB at 100 kHz)", () => {
    const r = run(EXAMPLES.find((e) => e.name === "rc_lowpass")!.text);
    if (!r.ok) throw new Error(r.error.message);
    const mag = r.analyses[0].signals.find((s) => s.name === "v(out)" && s.part === "magnitude")!.values;
    expect(mag[0]).toBeCloseTo(-0.00043427276812, 9);
    expect(mag[mag.length - 1]).toBeCloseTo(-40.0004342677, 8);
  });

  it("reports errors with a line number instead of throwing", () => {
    const r = run("t\nV1 a 0 DC 1\nR1 a b\n.op\n");
    expect(r).toEqual({ ok: false, error: { message: expect.stringContaining("needs two nodes and a value"), line: 3 } });
  });

  it("enforces the guards inside the browser runtime too", () => {
    const r = run("t\nV1 a 0 DC 1\nR1 a 0 1k\n.ac lin 200000 1 1meg\n");
    expect(r.ok).toBe(false);
  });

  // observed worst case over all examples against ngspice 41 in the browser runtime is far below these (the comparison tests
  // in tests/test_vs_ngspice*.py hold the real tolerances); these catch a runtime that disagrees with native numbers
  const TOL = { op: 1e-6, dc: 1e-3, tran: 5e-2 } as const; // fraction of the signal peak (op: relative); ac: dB / degrees below
  it.each(EXAMPLES.map((e) => [e.name, e.text] as const))("%s runs and agrees with the ngspice reference", (name, text) => {
    const r = run(text);
    if (!r.ok) throw new Error(`${name}: ${r.error.message}`);
    const ref = JSON.parse(fs.readFileSync(path(`../public/reference/${name}.json`), "utf8")) as RefFile;
    expect(ref.analyses.length).toBe(r.analyses.length);
    r.analyses.forEach((a, i) => {
      const ra = ref.analyses[i];
      expect(ra.type).toBe(a.type);
      for (const s of a.signals) {
        expect(s.values.every((v) => v === null || Number.isFinite(v))).toBe(true);
        const m = ra.signals.find((q) => q.name === s.name && q.part === s.part);
        expect(m, `${name} ${a.type} ${s.name}`).toBeDefined();
        const theirs = a.x ? resample(ra.x, m!.values, a.x.values) : m!.values;
        const { diff, peak } = maxDiff(s.values, theirs);
        if (a.type === "ac") expect(diff, `${name} ${s.name} ${s.part}`).toBeLessThan(s.part === "phase" ? 1e-2 : 1e-3);
        else if (a.type === "op") expect(diff, `${name} ${s.name}`).toBeLessThanOrEqual(TOL.op * Math.max(peak, 1e-9));
        else expect(diff, `${name} ${a.type} ${s.name}`).toBeLessThanOrEqual(TOL[a.type] * Math.max(peak, 1e-9));
      }
    });
  }, 180_000);
});