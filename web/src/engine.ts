import type { RunResult } from "./types";

type Listener = (message: string) => void;
interface Pending {
  resolve(r: RunResult): void;
  reject(e: Error): void;
  timer: ReturnType<typeof setTimeout>;
}

export class EngineTimeout extends Error {}

/**
 * The spicelite engine in a Web Worker. The runtime starts loading as soon as the page does; run() waits for it.
 * A run that exceeds `hardTimeoutMs` terminates the worker (a Python loop cannot be interrupted any other way) and the
 * next run boots a fresh one. Browser caching makes that second boot fast.
 */
export class Engine {
  private worker: Worker | null = null;
  private booting: Promise<void> | null = null;
  private pending = new Map<number, Pending>();
  private nextId = 1;
  runtime = "";

  constructor(private onProgress: Listener, private hardTimeoutMs = 60_000) {}

  /** Start loading the runtime (idempotent). Resolves when spicelite is importable inside the worker. */
  start(): Promise<void> {
    if (this.booting) return this.booting;
    const worker = new Worker(new URL("./worker.ts", import.meta.url), { type: "module" });
    this.worker = worker;
    this.booting = new Promise<void>((resolve, reject) => {
      worker.onmessage = (e: MessageEvent) => {
        const m = e.data;
        if (m.type === "progress") this.onProgress(m.message);
        else if (m.type === "ready") {
          this.runtime = `Python ${m.python} \u00b7 Pyodide ${m.pyodide}`;
          worker.onmessage = (ev) => this.onMessage(ev.data);
          resolve();
        } else if (m.type === "init-error") reject(new Error(m.message));
      };
      worker.onerror = (e) => reject(new Error(e.message || "the worker failed to start"));
      worker.postMessage({ type: "init", wheelUrl: new URL("wheels/spicelite.whl", document.baseURI).href });
    });
    this.booting.catch(() => this.reset());
    return this.booting;
  }

  private onMessage(m: { type: string; id: number; json?: string; message?: string }) {
    const p = this.pending.get(m.id);
    if (!p) return; // a result for a run that was already abandoned
    this.pending.delete(m.id);
    clearTimeout(p.timer);
    if (m.type === "result") p.resolve(JSON.parse(m.json!) as RunResult);
    else p.reject(new Error(m.message ?? "the run failed"));
  }

  private reset() {
    this.worker?.terminate();
    this.worker = null;
    this.booting = null;
  }

  async run(netlist: string, options: Record<string, unknown> = {}): Promise<RunResult> {
    await this.start();
    const worker = this.worker!;
    const id = this.nextId++;
    return new Promise<RunResult>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        this.reset();
        reject(new EngineTimeout(`the run took longer than ${this.hardTimeoutMs / 1000} s and was stopped; reduce the sweep or the circuit size`));
      }, this.hardTimeoutMs);
      this.pending.set(id, { resolve, reject, timer });
      worker.postMessage({ type: "run", id, netlist, options });
    });
  }
}