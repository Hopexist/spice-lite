// Every bundled example netlist (../../examples/*.cir) is inlined at build time. The first line of a netlist is its
// title, which doubles as the one-line description in the dropdown.
const files = import.meta.glob("../../examples/*.cir", { query: "?raw", import: "default", eager: true }) as Record<string, string>;

export interface Example {
  name: string;
  text: string;
  description: string;
}

export const EXAMPLES: Example[] = Object.entries(files)
  .map(([path, text]) => ({
    name: path.split("/").pop()!.replace(/\.cir$/, ""),
    text: text.replace(/\r\n/g, "\n"),
    description: text.split(/\r?\n/, 1)[0].trim(),
  }))
  .sort((a, b) => a.name.localeCompare(b.name));

export function findExample(name: string): Example | undefined {
  return EXAMPLES.find((e) => e.name === name);
}

export const DEFAULT_EXAMPLE = "rc_lowpass";