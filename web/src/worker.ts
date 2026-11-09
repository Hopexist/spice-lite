/// <reference lib="webworker" />
// Runs spicelite inside Pyodide, off the main thread so the page never freezes.
// Pyodide itself comes from the jsdelivr CDN at a pinned version (numpy and scipy from Pyodide's own package set);
// the spicelite wheel is built from this repository and served next to the page.
const PYODIDE_VERSION = "314.0.7";
const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

type WorkerRequest = { type: "init"; wheelUrl: string } | { type: "run"; id: number; netlist: string; options: Record<string, unknown> };
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let py: any;

const post = (message: unknown) => (self as unknown as DedicatedWorkerGlobalScope).postMessage(message);
const progress = (message: string) => post({ type: "progress", message });

async function init(wheelUrl: string) {
  progress("Downloading the Python runtime\u2026");
  const { loadPyodide } = await import(/* @vite-ignore */ `${PYODIDE_URL}pyodide.mjs`);
  py = await loadPyodide({ indexURL: PYODIDE_URL });
  progress("Loading numpy and scipy\u2026");
  await py.loadPackage(["numpy", "scipy"]);
  progress("Installing spicelite\u2026");
  const wheel = new Uint8Array(await (await fetch(wheelUrl)).arrayBuffer());
  py.unpackArchive(wheel, "wheel");
  py.runPython("import json\nfrom spicelite.web_api import run_netlist");
  post({ type: "ready", python: py.runPython("import sys; sys.version.split()[0]"), pyodide: PYODIDE_VERSION });
}

self.onmessage = async (event: MessageEvent<WorkerRequest>) => {
  const msg = event.data;
  try {
    if (msg.type === "init") return await init(msg.wheelUrl);
    py.globals.set("_netlist", msg.netlist);
    py.globals.set("_options", JSON.stringify(msg.options));
    const json: string = py.runPython("json.dumps(run_netlist(_netlist, json.loads(_options)), allow_nan=False)");
    post({ type: "result", id: msg.id, json });
  } catch (err) {
    post({ type: msg.type === "init" ? "init-error" : "run-error", id: (msg as { id?: number }).id, message: String((err as Error)?.message ?? err) });
  }
};