import { describe, expect, it } from "vitest";
import { columns, csvFileName, defaultVisible, eng, groupSignals, num, opRows, toCsv } from "../src/format";
import type { Analysis } from "../src/types";

const meta = { runtime_ms: 1, points: 3, warnings: [] };
const tran: Analysis = {
  type: "tran", title: ".tran", meta,
  x: { name: "time", unit: "s", log: false, values: [0, 0.001, 0.002] },
  signals: [
    { name: "v(out)", unit: "V", values: [0, 0.5, null], part: null },
    { name: "i(v1)", unit: "A", values: [-0.001, -0.0005, -0.00025], part: null },
  ],
};
const ac: Analysis = {
  type: "ac", title: ".ac", meta,
  x: { name: "frequency", unit: "Hz", log: true, values: [10, 100, 1000] },
  signals: [
    { name: "v(out)", unit: "dB", values: [0, -3.01, null], part: "magnitude" },
    { name: "v(out)", unit: "deg", values: [-1, -45, -89], part: "phase" },
    { name: "i(v1)", unit: "dB", values: [-60, -60, -60], part: "magnitude" },
    { name: "i(v1)", unit: "deg", values: [-90, -90, -90], part: "phase" },
  ],
};
const op: Analysis = {
  type: "op", title: ".op", meta, x: null,
  signals: [
    { name: "v(out)", unit: "V", values: [6.666666666], part: null },
    { name: "i(v1)", unit: "A", values: [-0.0033333333], part: null },
  ],
};

describe("engineering notation", () => {
  it("uses SI prefixes with five significant digits", () => {
    expect(eng(0.0033333333, "A")).toBe("3.3333 mA");
    expect(eng(-0.0033333333, "A")).toBe("-3.3333 mA");
    expect(eng(6.666666, "V")).toBe("6.6667 V");
    expect(eng(1500, "Hz")).toBe("1.5 kHz");
    expect(eng(2.5e6, "Hz")).toBe("2.5 MHz");
    expect(eng(1e-9, "V")).toBe("1 nV");
    expect(eng(4.7e-6, "F")).toBe("4.7 \u00b5F");
    expect(eng(10, "")).toBe("10");
  });
  it("handles zero, missing and non-finite values and rounds up across a prefix boundary", () => {
    expect(eng(0, "V")).toBe("0 V");
    expect(eng(null, "V")).toBe("\u2014");
    expect(eng(Infinity, "V")).toBe("Infinity");
    expect(eng(999.99999, "V")).toBe("1 kV");
  });
  it("num keeps 6 significant digits and switches to exponent form at the extremes", () => {
    expect(num(1.5)).toBe("1.5");
    expect(num(0)).toBe("0");
    expect(num(null)).toBe("\u2014");
    expect(num(0.000123456789)).toBe("1.23457e-4");
    expect(num(1234567)).toBe("1.23457e6");
    expect(num(3.14159265)).toBe("3.14159");
  });
});

describe("table columns and CSV", () => {
  it("names columns like the command line CSV", () => {
    expect(columns(tran).map((c) => c.header)).toEqual(["time (s)", "v(out) (V)", "i(v1) (A)"]);
    expect(columns(ac).map((c) => c.header)).toEqual(["frequency (Hz)", "mag_db(v(out))", "phase_deg(v(out))", "mag_db(i(v1))", "phase_deg(i(v1))"]);
    expect(columns(op).map((c) => c.header)).toEqual(["v(out) (V)", "i(v1) (A)"]);
  });
  it("exports every row at full precision, with missing values as empty cells", () => {
    expect(toCsv(tran)).toBe("time (s),v(out) (V),i(v1) (A)\n0,0,-0.001\n0.001,0.5,-0.0005\n0.002,,-0.00025\n");
  });
  it("quotes headers that contain commas or quotes", () => {
    const odd: Analysis = { ...tran, signals: [{ name: 'v("a,b")', unit: "V", values: [1, 2, 3], part: null }] };
    expect(toCsv(odd).split("\n")[0]).toBe('time (s),"v(""a,b"") (V)"');
  });
  it("names the file from the circuit title and the analysis type", () => {
    expect(csvFileName("RC lowpass, corner = 1 kHz!", tran)).toBe("rc-lowpass-corner-1-khz_tran.csv");
    expect(csvFileName("", op)).toBe("spicelite_op.csv");
  });
  it("lists .op rows with a formatted value and the signal kind", () => {
    expect(opRows(op)).toEqual([
      { name: "v(out)", value: "6.6667 V", raw: 6.666666666, kind: "node voltage" },
      { name: "i(v1)", value: "-3.3333 mA", raw: -0.0033333333, kind: "branch current" },
    ]);
  });
});

describe("plot grouping", () => {
  it("never puts voltages and currents on one axis", () => {
    expect(groupSignals(tran).map((g) => [g.id, g.signals.map((s) => s.name)])).toEqual([["v", ["v(out)"]], ["i", ["i(v1)"]]]);
  });
  it("gives AC a magnitude / phase pair for voltages, and a second pair for currents", () => {
    const groups = groupSignals(ac);
    expect(groups.map((g) => g.id)).toEqual(["mag-v", "phase-v", "mag-i", "phase-i"]);
    expect(groups.map((g) => g.phase)).toEqual([false, true, false, true]);
    expect(groups.map((g) => g.current)).toEqual([false, false, true, true]);
  });
  it("starts with at most 8 traces visible", () => {
    expect(defaultVisible(3)).toEqual([true, true, true]);
    expect(defaultVisible(10).filter(Boolean)).toHaveLength(8);
    expect(defaultVisible(0)).toEqual([]);
  });
});