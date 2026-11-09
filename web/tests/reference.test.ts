import { describe, expect, it } from "vitest";
import { maxDiff, overlayFor, resample, type RefFile } from "../src/reference";
import type { RunOk } from "../src/types";

describe("resample", () => {
  it("returns the same data when the grids coincide", () => {
    const ys = [1, 2, 3];
    expect(resample([0, 1, 2], ys, [0, 1, 2])).toBe(ys);
  });
  it("interpolates linearly and gives null outside the reference range", () => {
    expect(resample([0, 1, 2], [0, 10, 20], [0.5, 1.5, 3, -1])).toEqual([5, 15, null, null]);
  });
  it("propagates gaps and tolerates repeated x values", () => {
    expect(resample([0, 1, 2], [0, null, 20], [0.5])).toEqual([null]);
    expect(resample([0, 1, 1, 2], [0, 1, 5, 6], [1.5])).toEqual([5.5]);
  });
});

describe("maxDiff", () => {
  it("compares only the points both curves have", () => {
    expect(maxDiff([1, 2, null, 4], [1, 2.5, 3, 4])).toEqual({ diff: 0.5, peak: 4 });
    expect(maxDiff([], [])).toEqual({ diff: 0, peak: 0 });
  });
});

const run: RunOk = {
  ok: true, title: "t", version: "0", warnings: [],
  analyses: [{
    type: "dc", title: ".dc", meta: { runtime_ms: 1, points: 3, warnings: [] },
    x: { name: "v1", unit: "V", log: false, values: [0, 1, 2] },
    signals: [{ name: "v(out)", unit: "V", values: [0, 1, 2], part: null }],
  }],
};
const ref = (type: string, values: number[]): RefFile => ({ example: "x", ngspice: "41", analyses: [{ type, x: [0, 1, 2], signals: [{ name: "v(out)", part: null, values }] }] });

describe("overlayFor", () => {
  it("builds dashed reference traces and a worst-case summary", () => {
    const o = overlayFor(ref("dc", [0, 1.001, 2]), run).get(0)!;
    expect(o.extras.get("v")![0]).toEqual({ label: "ngspice v(out)", values: [0, 1.001, 2] });
    expect(o.rows[0].worst).toContain("v(out)");
    expect(o.summary).toContain("of peak");
  });
  it("ignores a reference whose analysis type does not match", () => {
    expect(overlayFor(ref("tran", [0, 1, 2]), run).size).toBe(0);
  });
});