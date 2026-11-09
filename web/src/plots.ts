import uPlot from "uplot";
import { eng, num, type Group } from "./format";
import type { XAxis } from "./types";

// Traces differ by dash pattern as well as color, so nothing is conveyed by color alone.
export const DASHES: number[][] = [[], [9, 4], [2, 3], [10, 4, 2, 4], [16, 5], [1, 4], [6, 3, 1, 3], [3, 3]];

export interface Extra {
  label: string;
  values: (number | null)[];
}
export interface PlotHandle {
  destroy(): void;
}

const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

/** Draw one group of traces (voltages, currents, an AC magnitude or phase) into `host`. */
export function drawGroup(host: HTMLElement, x: XAxis, g: Group, visible: boolean[], opts: { syncKey?: string; height?: number; extra?: Extra[] } = {}): PlotHandle {
  const colors = Array.from({ length: 8 }, (_, i) => css(`--c${i + 1}`));
  const muted = css("--muted");
  const grid = css("--grid");
  const mono = css("--mono");
  const axis = (label: string, log = false, engineering = false): uPlot.Axis => ({
    stroke: muted,
    label,
    labelSize: 18,
    labelFont: `12px ${mono}`,
    font: `11.5px ${mono}`,
    grid: { stroke: grid, width: 1 },
    ticks: { stroke: grid, width: 1 },
    values: (_u, splits) =>
      splits.map((v) => {
        if (v === null || v === undefined) return ""; // uPlot passes null for ticks it leaves unlabeled
        if (log) return Math.abs(Math.log10(v) - Math.round(Math.log10(v))) < 1e-9 ? eng(v, "", 3) : ""; // label decades only
        return engineering || Math.abs(v) >= 1e4 || (v !== 0 && Math.abs(v) < 1e-2) ? eng(v, "", 3) : num(v);
      }),
  });
  const series: uPlot.Series[] = [{ label: x.name, value: (_u, v) => (v == null ? "\u2014" : eng(v, x.unit, 5)) }];
  g.signals.forEach((s, i) =>
    series.push({
      label: s.name,
      stroke: colors[i % 8],
      width: 1.9,
      dash: DASHES[i % 8],
      show: visible[i] ?? true,
      spanGaps: false,
      points: { show: false },
      value: (_u, v) => (v == null ? "\u2014" : num(v)),
    }),
  );
  const data: (number | null)[][] = [x.values, ...g.signals.map((s) => s.values)];
  for (const e of opts.extra ?? []) {
    series.push({ label: e.label, stroke: css("--ink"), width: 1.3, dash: [5, 4], points: { show: false }, value: (_u, v) => (v == null ? "\u2014" : num(v)) });
    data.push(e.values);
  }
  const width = Math.max(host.clientWidth, 240);
  const options: uPlot.Options = {
    width,
    height: opts.height ?? 280,
    series,
    scales: { x: { time: false, distr: x.log ? 3 : 1 } },
    axes: [axis(`${x.name} (${x.unit})`, x.log, true), axis(g.yLabel)],
    cursor: {
      drag: { x: true, y: true, setScale: true, uni: 40 },
      sync: opts.syncKey ? { key: opts.syncKey, scales: ["x", null] } : undefined,
    },
    legend: { live: true },
    padding: [8, 12, 0, 0],
  };
  host.replaceChildren();
  const plot = new uPlot(options, data as uPlot.AlignedData, host);
  const ro = new ResizeObserver(() => {
    const w = Math.max(host.clientWidth, 240);
    if (w !== plot.width) plot.setSize({ width: w, height: options.height! });
  });
  ro.observe(host);
  host.setAttribute("role", "img");
  host.setAttribute("aria-label", `${g.title} against ${x.name}: ${g.signals.map((s) => s.name).join(", ")}. Use the Table view for the numbers.`);
  return {
    destroy() {
      ro.disconnect();
      plot.destroy();
    },
  };
}