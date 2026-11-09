// Schematic symbols, drawn in code (no artwork copied): one SVG per element-sheets.json "symbol" key, on a 160 x 80 grid
// with the two main terminals at (8, 40) and (152, 40). Monochrome: stroke and fill are currentColor.

const wrap = (body: string, extra = "") =>
  `<svg viewBox="0 0 160 80" width="160" height="80" class="sym" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${body}${extra}</svg>`;
const leads = (a: number, b: number) => `<path d="M8 40H${a}M${b} 40H152"/>`;
const dot = (x: number, y: number) => `<circle cx="${x}" cy="${y}" r="3" fill="currentColor" stroke="none"/>`;
const ends = dot(8, 40) + dot(152, 40);
const diamond = `<path d="M80 18L102 40L80 62L58 40Z"/>`;
const plusMinus = `<path d="M74 31h12M80 25v12M74 50h12"/>`;
const arrowDown = `<path d="M80 26v28M73 46l7 9 7-9"/>`;
const controlRef = (label: string) => `<text x="80" y="76" text-anchor="middle" class="sym-note">${label}</text>`;

export const SYMBOLS: Record<string, string> = {
  resistor: wrap(leads(48, 112) + `<path d="M48 40l5-12 10 24 10-24 10 24 10-24 10 24 5-12"/>`, ends),
  capacitor: wrap(leads(74, 86) + `<path d="M74 22v36M86 22v36"/>`, ends),
  inductor: wrap(leads(44, 116) + `<path d="M44 40a9 9 0 0 1 18 0a9 9 0 0 1 18 0a9 9 0 0 1 18 0a9 9 0 0 1 18 0"/>`, ends),
  vsource: wrap(leads(58, 102) + `<circle cx="80" cy="40" r="22"/><path d="M66 40h8M70 36v8M86 40h8"/>`, ends),
  isource: wrap(leads(58, 102) + `<circle cx="80" cy="40" r="22"/><path d="M68 40h24M84 33l8 7-8 7"/>`, ends),
  diode: wrap(leads(66, 94) + `<path d="M66 24v32l28-16Z" fill="currentColor"/><path d="M94 24v32"/>`, ends),
  nmos: wrap(
    // drain at the right terminal, source at the left, gate from below, bulk arrow pointing in (NMOS)
    `<path d="M8 40H56V30M152 40H104V30M60 30h40M60 24h40M80 24V6M60 36h40"/>` +
      `<path d="M80 52V38M76 42l4-4 4 4"/>`, // the NMOS arrow points from the bulk into the channel
    ends + `<text x="8" y="60" class="sym-note">S</text><text x="146" y="60" class="sym-note">D</text><text x="86" y="12" class="sym-note">G</text>`,
  ),
  vcvs: wrap(leads(58, 102) + diamond + plusMinus, ends + controlRef("v = k (v(nc+) - v(nc-))")),
  vccs: wrap(leads(58, 102) + diamond + arrowDown, ends + controlRef("i = g (v(nc+) - v(nc-))")),
  cccs: wrap(leads(58, 102) + diamond + arrowDown, ends + controlRef("i = k i(Vsense)")),
  ccvs: wrap(leads(58, 102) + diamond + plusMinus, ends + controlRef("v = r i(Vsense)")),
};
