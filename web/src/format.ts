import type { Analysis, Signal } from "./types";

const PREFIXES: [number, string][] = [
  [1e12, "T"], [1e9, "G"], [1e6, "M"], [1e3, "k"], [1, ""], [1e-3, "m"], [1e-6, "\u00b5"], [1e-9, "n"], [1e-12, "p"], [1e-15, "f"],
];

/** Engineering notation with an SI prefix: eng(0.0033333, "A") -> "3.3333 mA". null (no value) -> an em dash. */
export function eng(value: number | null, unit = "", digits = 5): string {
  if (value === null || value === undefined) return "\u2014";
  if (!Number.isFinite(value)) return String(value);
  if (value === 0) return `0 ${unit}`.trim();
  const mag = Math.abs(value);
  const [scale, prefix] = PREFIXES.find(([s]) => mag >= s * 0.99995) ?? PREFIXES[PREFIXES.length - 1];
  const scaled = Number((value / scale).toPrecision(digits));
  return `${scaled} ${prefix}${unit}`.trim();
}

/** Compact plain number for tables and legends: 6 significant digits. */
export function num(value: number | null): string {
  if (value === null || value === undefined) return "\u2014";
  if (!Number.isFinite(value)) return String(value);
  if (value === 0) return "0";
  const mag = Math.abs(value);
  return mag >= 1e6 || mag < 1e-3 ? Number(value.toPrecision(6)).toExponential().replace("e+", "e") : String(Number(value.toPrecision(6)));
}

export interface Column {
  header: string;
  values: (number | null)[];
  signal?: Signal;
}

/** Table / CSV columns, named like the command line's CSV: v(out), mag_db(v(out)), phase_deg(v(out)). */
export function columns(a: Analysis): Column[] {
  const cols: Column[] = [];
  if (a.x) cols.push({ header: `${a.x.name} (${a.x.unit})`, values: a.x.values });
  for (const s of a.signals) {
    const header = s.part === "magnitude" ? `mag_db(${s.name})` : s.part === "phase" ? `phase_deg(${s.name})` : `${s.name} (${s.unit})`;
    cols.push({ header, values: s.values, signal: s });
  }
  return cols;
}

function csvCell(text: string): string {
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** Full-precision CSV of one analysis (every row). Missing values are empty cells. */
export function toCsv(a: Analysis): string {
  const cols = columns(a);
  const rows = cols[0]?.values.length ?? 0;
  const lines = [cols.map((c) => csvCell(c.header)).join(",")];
  for (let i = 0; i < rows; i++) lines.push(cols.map((c) => (c.values[i] === null ? "" : String(c.values[i]))).join(","));
  return lines.join("\n") + "\n";
}

export function csvFileName(title: string, a: Analysis): string {
  const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "spicelite";
  return `${slug}_${a.type}.csv`;
}

export interface Group {
  id: string;
  title: string;
  yLabel: string;
  signals: Signal[];
  phase: boolean;
  current: boolean;
}

/** Split an analysis into plots: voltages and currents never share an axis; AC gets a magnitude / phase (Bode) pair. */
export function groupSignals(a: Analysis): Group[] {
  const groups: Group[] = [];
  const add = (id: string, title: string, yLabel: string, signals: Signal[], phase = false, current = false) => {
    if (signals.length) groups.push({ id, title, yLabel, signals, phase, current });
  };
  const isI = (s: Signal) => s.name.startsWith("i(");
  if (a.type === "ac") {
    const pick = (cur: boolean, part: string) => a.signals.filter((s) => isI(s) === cur && s.part === part);
    add("mag-v", "Magnitude", "dB", pick(false, "magnitude"));
    add("phase-v", "Phase", "degrees", pick(false, "phase"), true);
    add("mag-i", "Branch current magnitude", "dB", pick(true, "magnitude"), false, true);
    add("phase-i", "Branch current phase", "degrees", pick(true, "phase"), true, true);
  } else {
    add("v", "Node voltages", "V", a.signals.filter((s) => !isI(s)));
    add("i", "Branch currents", "A", a.signals.filter(isI), false, true);
  }
  return groups;
}

/** Which traces start visible: the first `max` (a 50-node ladder would otherwise be a hairball); the rest are one legend click away. */
export function defaultVisible(count: number, max = 8): boolean[] {
  return Array.from({ length: count }, (_, i) => i < max);
}

export function opRows(a: Analysis): { name: string; value: string; raw: number | null; kind: string }[] {
  return a.signals.map((s) => ({
    name: s.name,
    value: eng(s.values[0] ?? null, s.unit),
    raw: s.values[0] ?? null,
    kind: s.name.startsWith("i(") ? "branch current" : "node voltage",
  }));
}