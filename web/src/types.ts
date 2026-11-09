// Shape of spicelite.web_api.run_netlist() output (see src/spicelite/web_api.py).
export interface Signal {
  name: string; // "v(out)", "i(v1)"
  unit: string; // V, A, dB, deg
  values: (number | null)[];
  part: "magnitude" | "phase" | null; // AC signals come as a magnitude and a phase pair
}
export interface XAxis {
  name: string;
  unit: string;
  log: boolean;
  values: (number | null)[];
}
export interface Warn {
  type: string;
  message: string;
}
export interface Meta {
  runtime_ms: number;
  points: number;
  method?: string;
  step_control?: string;
  steps?: number;
  rejected?: number;
  solver?: string;
  warnings: Warn[];
  [k: string]: unknown;
}
export interface Analysis {
  type: "op" | "dc" | "ac" | "tran";
  title: string;
  x: XAxis | null; // null for .op
  signals: Signal[];
  meta: Meta;
}
export interface RunOk {
  ok: true;
  title: string;
  version: string;
  warnings: Warn[];
  analyses: Analysis[];
}
export interface RunErr {
  ok: false;
  error: { message: string; line: number | null };
}
export type RunResult = RunOk | RunErr;