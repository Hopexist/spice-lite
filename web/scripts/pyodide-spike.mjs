// Feasibility spike: spicelite in Pyodide, headless under Node.
import { loadPyodide } from "pyodide";
import fs from "node:fs";
import path from "node:path";

const t0 = performance.now();
const py = await loadPyodide();
console.log("pyodide", py.version, "python", py.runPython("import sys; sys.version.split()[0]"), `${(performance.now() - t0).toFixed(0)} ms`);
const t1 = performance.now();
await py.loadPackage(["numpy", "scipy"]);
console.log("numpy+scipy loaded", `${(performance.now() - t1).toFixed(0)} ms`);
const wheelDir = process.argv[2];
const wheel = fs.readdirSync(wheelDir).find((f) => f.endsWith(".whl"));
py.unpackArchive(new Uint8Array(fs.readFileSync(path.join(wheelDir, wheel))), "wheel");
const netlist = fs.readFileSync(process.argv[3], "utf8");
py.globals.set("netlist", netlist);
const out = py.runPython(`
import json, sys
from spicelite import parse
from spicelite.analysis.ac import ac, magnitude_db
c = parse(netlist)
r = ac(c)
print("matplotlib imported:", "matplotlib" in sys.modules)
json.dumps({"n": len(r.freqs), "f0": float(r.freqs[0]), "db_out_first": float(magnitude_db(r.voltages["out"])[0]), "db_out_last": float(magnitude_db(r.voltages["out"])[-1])})
`);
console.log(out, `total ${(performance.now() - t0).toFixed(0)} ms`);
