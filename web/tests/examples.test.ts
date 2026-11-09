import { describe, expect, it } from "vitest";
import { DEFAULT_EXAMPLE, EXAMPLES, findExample } from "../src/examples";

describe("bundled examples", () => {
  it("includes every examples/*.cir with a one-line description", () => {
    expect(EXAMPLES.length).toBeGreaterThanOrEqual(30);
    for (const e of EXAMPLES) {
      expect(e.text.trim().length, e.name).toBeGreaterThan(10);
      expect(e.description.length, e.name).toBeGreaterThan(5);
      expect(e.description, e.name).not.toContain("\n");
      expect(e.text, e.name).not.toContain("\r");
    }
  });
  it("has unique, sorted names and a default that exists", () => {
    const names = EXAMPLES.map((e) => e.name);
    expect(new Set(names).size).toBe(names.length);
    expect([...names].sort((a, b) => a.localeCompare(b))).toEqual(names);
    expect(findExample(DEFAULT_EXAMPLE)).toBeDefined();
    expect(findExample("nope")).toBeUndefined();
  });
  it("covers the milestone features: controlled sources, MOSFETs, adaptive stepping, UIC", () => {
    for (const name of ["inv_amp", "nmos_iv", "cmos_inverter_tran", "stiff_adaptive", "rc_ic_discharge", "diode_clamp"]) expect(findExample(name), name).toBeDefined();
  });
});