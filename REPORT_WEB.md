# Report: web UI (branch `web-ui`)

Run started 13:09 EST (per `date`); all phases finished well inside the time box (last check 13:59). Nothing was pushed or tagged, `main` is untouched.
Previous reports: `REPORT_M5_M7.md`, `REPORT_M8_M9.md`.

## What was built
| Phase | Result |
|---|---|
| 1. Pyodide spike | **GO.** Pyodide 314.0.7 (Python 3.14.2, numpy 2.4.6, scipy 1.18.0) runs spicelite in a Web Worker; results match the CLI digit for digit; matplotlib is never imported. No FastAPI fallback was needed. |
| 2. JSON API | `spicelite.web_api.run_netlist(text, options)`: never raises, strict JSON, line-numbered errors, size/time guards (D32). 70 new tests, CLI output frozen by golden files. |
| 3. UI | Vite + TypeScript, uPlot charts (log-x Bode pair, zoom, legend toggle), CodeMirror 6 with SPICE highlighting and error gutter, examples with descriptions, tabs per analysis, table + CSV, `.op` table, warnings, share links, dark/light/auto, responsive, keyboard/ARIA basics. |
| 4. Reference overlay | `scripts/gen_reference.py` precomputes ngspice 41 curves for all 33 examples (893 kB committed); dashed overlay + error panel, labelled "precomputed". |
| 5. Tests, build, deploy | Vitest + Playwright, sub-path serving check, `pages.yml`, CI `web` job, README section, screenshots in `docs/web_ui_*.png`. |
| 6. Audit | See below. |

## Tests
| Suite | Result |
|---|---|
| `pytest -q` (ngspice 41 via `NGSPICE`) | **718 passed, 0 skipped** |
| Frontend `npm test` (vitest) | **101 passed** (64 pure-logic tests + 37 that run every example through real Pyodide against the committed reference) |
| Playwright e2e (Edge) | **16 passed** (smoke, errors, guards, rapid clicks, share links, overlay, CSV, theme, 360/1440 px, keyboard, `/spice-lite/` sub-path) |
| Audit script | all 33 examples run through the built site without error |

## Load size and time
- Own site: `dist/` 1.5 MB (JS 375 kB, 129 kB gzip; fonts; 54 kB spicelite wheel; reference JSON loaded on demand).
- First visit transfers ~24 MB in total, almost all Pyodide + numpy + scipy from the jsdelivr CDN; first results appear after **~13 s** cold (11.7-15 s measured). Subsequent runs of any example: 50 ms - 2.5 s (slowest `cmos_inverter_tran`).
- Console errors: none. Layout checked at 360 and 1440 px (no horizontal scroll).

## Skipped, blocked, or not verified
- **CI has never run** (nothing pushed). The Pyodide test and e2e need network access to the CDN; Chromium is installed by the workflow instead of Edge.
- Pages needs one manual setting: Settings > Pages > Source = GitHub Actions.
- No GIF (screenshots only). The audit script waits for a tab to appear after switching examples, so a very fast rerun could be judged on the previous result; correctness per example is covered by the Pyodide vitest test instead.
- The live link in the README is a placeholder until Pages is enabled.

## Known limitations
- No live ngspice in the browser: the overlay is precomputed and only for unmodified bundled examples.
- No schematic view; the netlist is the only input.
- A running analysis cannot be interrupted inside Python; limits are checked beforehand and the worker is hard-terminated after 60 s.
- First load is heavy because it ships a Python runtime; needs internet (CDN).

## Suggested next steps
1. Push, watch the first CI run (both jobs), enable Pages. 2. Self-host Pyodide (or cache it with a service worker) for offline use and faster repeat visits. 3. Schematic viewer. 4. Component sweeps / parameter sliders. 5. The README "How MNA works" and "What I learned" sections.
