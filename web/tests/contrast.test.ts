import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// Accessibility basics checked against the real stylesheet: WCAG contrast of the text, state and trace colors in both themes.
const css = readFileSync(new URL("../src/style.css", import.meta.url), "utf8");
const block = (re: RegExp) => {
  const m = re.exec(css);
  if (!m) throw new Error(`block not found: ${re}`);
  return Object.fromEntries([...m[1].matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((d) => [d[1], d[2].trim()]));
};
const light = block(/:root\s*\{([^}]*)\}/);
const darkSystem = block(/:root:not\(\[data-theme="light"\]\)\s*\{([^}]*)\}/);
const darkManual = block(/:root\[data-theme="dark"\]\s*\{([^}]*)\}/);

const lum = (hex: string) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const ratio = (a: string, b: string) => {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

describe.each([["light", light], ["dark", { ...light, ...darkManual }]])("%s theme", (_name, t) => {
  const text: [string, string, number][] = [
    ["--ink", "--bg", 7], ["--ink", "--surface", 7], ["--muted", "--bg", 4.5], ["--muted", "--surface", 4.5], ["--muted", "--raised", 4.5],
    ["--accent", "--surface", 4.5], ["--run-ink", "--run", 4.5], ["--accent-ink", "--accent", 4.5],
    ["--err", "--err-bg", 4.5], ["--warn", "--warn-bg", 4.5], ["--syn-title", "--surface", 4.5], ["--syn-comment", "--surface", 4.5],
    ["--syn-dot", "--surface", 4.5], ["--syn-element", "--surface", 4.5], ["--syn-number", "--surface", 4.5], ["--syn-atom", "--surface", 4.5], ["--syn-prop", "--surface", 4.5],
  ];
  it.each(text)("%s on %s is at least %s:1", (fg, bg, min) => {
    expect(ratio(t[fg], t[bg]), `${fg} ${t[fg]} on ${bg} ${t[bg]}`).toBeGreaterThanOrEqual(min);
  });
  it("every trace color has at least 3:1 against the plot background (non-text contrast)", () => {
    for (let i = 1; i <= 8; i++) expect(ratio(t[`--c${i}`], t["--surface"]), `--c${i} ${t[`--c${i}`]}`).toBeGreaterThanOrEqual(3);
  });
});

describe("dark palette", () => {
  it("is the same whether it comes from the system setting or the manual toggle", () => {
    for (const [k, v] of Object.entries(darkSystem)) if (k !== "--dark") expect(darkManual[k], k).toBe(v);
  });
});