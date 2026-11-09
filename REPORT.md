# Report: UI polish (branch `ui-polish`)

Started Mon Nov 9 16:27:12 EST 2026 (per `date`), audit finished 17:46: all phases inside the 2 h 40 m limit. Nothing was pushed or
tagged. Previous reports: `REPORT_REFACTOR.md` (stamping refactor, earlier today), `REPORT_WEB.md`, `REPORT_M8_M9.md`, `REPORT_M5_M7.md`.
Decisions: DECISIONS D45 to D52.

## What was built
| Phase | Result |
|---|---|
| 0. Baseline | `docs/ui-before/`: 7 states (empty, example, .op, .dc, .ac, .tran, error) x 360 / 1440 px x dark / light; `web/scripts/shots.mjs` re-creates the set |
| 1. Tools | every tool read before use, scratchpad only; three MIT skills installed in `.claude/skills/` (dimensional-drawing, animate, review-animations); table below |
| 2. Direction | three CSS overlays on the real app, compared at 480 px (`docs/ui-directions/`); **A, Datasheet** chosen; brand: mark (Figure 1, an RC step response on its axes), favicon set, palette and type with measured contrast (`docs/brand/brand-sheet.png`) |
| 3. Design system | tokens for type, space, shape, shadow, motion and colour; light and dark from the same names; every component restyled; Archivo + JetBrains Mono self-hosted (latin subsets, `font-display: swap`) |
| 4. Motion | one authored moment (new results draw in once), a determinate first-load bar, .op values that roll and mark when a re-run changes them, calm error entrance and gutter pulse, tab and theme transitions, copy confirmation; no animation library |
| 5. Landing and sheets | a hero with a live demo drawn from real simulation data (`rc_step`, 4 beats, 9 s loop, pausable, poster frame under reduced motion), a ruled capability table whose every number is checkable, and 11 element spec sheets generated from a data file that a test ties to the parser |
| 6. Audit | below |

## Tools (DECISIONS D45, D46)
| Tool | Verdict | Why, in one line |
|---|---|---|
| StageShow | partly used | React kit not added (no framework); its demo principles followed by hand |
| Impeccable | partly used | its launcher downloads a binary: not run; its quality floor, refuse list, Operate / Persuade modes and motion guide applied |
| Dimensional Drawing | used, installed | pure instructions; drives the element spec sheets |
| Oil UI | partly used | update-check and upsell scripts, paid image credits not used; three-direction method followed |
| Emil Kowalski skills | used, installed | `animate` and `review-animations` set the motion rules and the review |
| Taste Skill | partly used | registers a Stop hook and downloads assets: not installed; its rules applied (found as `Leonxlnx/taste-skill`) |
| Brand Identity | partly used | its pipeline self-installs packages and costs ~0.9 M tokens: not run; its method followed by hand |
| Awwwards MCP | skipped | not configured in this session; three reference sites read instead (Linear, Falstad, Wokwi) |
| anime.js vs Motion | neither | measured 13.3 kB vs 28.4 kB (3.7 kB for `motion/mini`) gzip; CSS + Web Animations did everything |
| Kokonut UI, Bklit UI, Manus | studied | patterns rebuilt natively (ruled bento with live diagrams, draw-in charts, rolling values); nothing copied |

## Design-direction scorecard (D47)
| Criterion | A Datasheet | B Drafting vellum | C Night bench |
|---|---|---|---|
| Legibility of plots | 5 | 4 | 4 |
| Contrast | 5 | 4 | 4 |
| Distinctiveness | 4 | 4 | 2 |
| Fit for a circuit simulator | 5 | 3 | 3 |
| Mobile | 4 | 3 | 4 |
| **Total** | **23** | 18 | 17 |

## Size and timing (Phase 0 baseline vs final build)
| | Before | After |
|---|---:|---:|
| JS (gzip) | 129.4 kB | 134.0 kB (+4.6) |
| CSS (gzip) | 4.1 kB | 6.2 kB (+2.1) |
| HTML (gzip) | 1.4 kB | 2.8 kB (+1.4) |
| Fonts (woff2) | 116.2 kB, 6 files | 86.1 kB, 5 files (-30.1) |
| First load, own assets | | about **22 kB less** than before |
| `dist/` total | 1.708 MB | 1.711 MB |
| First results, cold browser cache | 10.3 s | 10.0 to 11.5 s across three measurements |

First-load time is dominated by Pyodide, NumPy and SciPy from the CDN (24.3 MB measured); the spread is download variance, not the page.

## Accessibility
- Contrast: the stylesheet token test (37 pairs, both themes) and a scan of every rendered text element in both themes: all WCAG AA or better.
- Colour is never the only cue: traces keep dash patterns; the demo legend shows solid and dashed keys; changed values are also rolled.
- Keyboard: logical tab order through the new hero controls; visible focus rings everywhere; tabs keep arrow-key navigation.
- Reduced motion: no movement or scaling anywhere; the demo shows its poster frame and hides its pause button; tested in e2e.
- Tap targets: hero actions 44 px; other controls 38 px (in-panel 32 px).

## Tests
| Suite | Baseline | Final |
|---|---|---|
| `pytest -q` (ngspice 41 via `NGSPICE`) | 809 passed, 0 skipped | **824 passed, 0 skipped** (+15 element-sheet tests) |
| `npm test` (vitest, incl. every example in real Pyodide vs ngspice) | 103 | **106** (+3 motion) |
| Playwright e2e (Edge, incl. `/spice-lite/` sub-path) | 16 | **24** (+4 motion, +4 landing) |
| `npm run build`, `ruff check .` | ok | ok |

## Bugs found and fixed along the way
- Ctrl/Cmd+Enter in the editor ran the netlist twice (found in the earlier code review); now once, with an e2e test that counts renders.
- The `hidden` attribute lost to classes that set `display`, so the demo pause button stayed visible under reduced motion; a base rule fixes it everywhere.

## Skipped, blocked or not verified
- Awwwards MCP (not configured); Bklit's catalog site (redirects; the repository was read instead).
- No custom animation for the examples menu: it is a native `<select>`, whose menu belongs to the platform.
- Oil UI's independent visual reviewer was not dispatched (no reviewer agent was requested for this run); the review is my own, with screenshots.
- One e2e run had 3 intermittent failures that did not reproduce (24/24 on the next run, 9 of 9 repeats); cause not confirmed.
- The live site is not updated until `main` is pushed and Pages deploys.

## Suggested next steps
1. Push and let Pages deploy; check the live first load on a phone.
2. A small Playwright visual-regression set from `docs/ui-after/`, so a CSS change cannot silently undo the design.
3. Let the demo run the real engine once Pyodide is ready, and swap in spicelite's own curve.
4. Click-to-insert from the element sheets into the editor.
5. A print stylesheet, so a result prints as an actual datasheet page.
