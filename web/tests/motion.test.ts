import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { BOOT_STAGES, easeOut, stageOf } from "../src/motion";

describe("first-load stages", () => {
  it("match the worker's progress messages, in order, so the loading bar can be determinate", () => {
    const worker = readFileSync(new URL("../src/worker.ts", import.meta.url), "utf8");
    const sent = [...worker.matchAll(/progress\("([^"\\]+)/g)].map((m) => m[1]);
    expect(sent).toEqual(BOOT_STAGES);
    BOOT_STAGES.forEach((s, i) => expect(stageOf(`${s}\u2026`)).toBe(i + 1));
  });
  it("an unknown message is stage 0, so the bar stays where it is", () => {
    expect(stageOf("Something else")).toBe(0);
  });
});

describe("easeOut", () => {
  it("starts at 0, ends exactly at 1, never overshoots and is clamped outside [0, 1]", () => {
    expect(easeOut(0)).toBe(0);
    expect(easeOut(1)).toBe(1);
    expect(easeOut(-1)).toBe(0);
    expect(easeOut(2)).toBe(1);
    for (let t = 0; t <= 1; t += 0.05) expect(easeOut(t)).toBeLessThanOrEqual(1);
    expect(easeOut(0.25)).toBeGreaterThan(0.25); // ease-OUT: most of the change happens early
  });
});
