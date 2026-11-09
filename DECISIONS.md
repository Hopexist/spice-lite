# DECISIONS (overnight run)

Each entry: choice, alternatives, why.

## D1. ngspice "present" means reachable through `$NGSPICE`, not on PATH
- **Choice:** `which ngspice` finds nothing on this machine, but ngspice-41 is installed (bundled with another desktop application) and the runner finds it through the `NGSPICE` environment variable. I proceeded.
- **Alternative:** stop immediately because `which ngspice` fails (literal reading of the safety rule).
- **Why:** the rule exists so that green runs are not green merely because ngspice tests skipped. You asked
  for the `NGSPICE` mechanism yourself in Milestone 2, knowing ngspice was not on PATH, and all earlier
  milestones were verified this way. To keep the rule's intent, every committing run must show
  **0 skipped** tests, which proves the comparisons really ran.

## D2. Golden regression data comes from the v0.6 tag, extracted with `git archive`
- **Choice:** the "M1-M6 results unchanged" test compares against `tests/golden_m1_m6.json`, generated
  by running the *v0.6 tag's own source* (extracted to a temp dir with `git archive`, no worktree).
- **Alternative:** hard-code a handful of numbers from memory.
- **Why:** captures every existing example's op/dc/ac/tran output from the old code, so any behaviour change
  caused by new work shows up.

## D3. No git worktree for the golden data or the branch work
- **Choice:** work directly on `overnight-m5-m7`; extract v0.6 with `git archive | tar -x` into a temp dir.
- **Alternative:** `git worktree add` / `remove`.
- **Why:** removing a worktree needs a destructive command, which the environment gates; `git archive` gives
  the same pristine source with nothing to clean up in the repo.

## D4. Op-amp is a high-gain VCVS (OPAMP_GAIN = 1e6), not a nullor
- **Choice:** `opamp()` returns an `E` element with gain 1e6, configurable per call.
- **Alternatives:** a nullor (ideal op-amp forcing v(in+) = v(in-)) as a new element type.
- **Why:** reuses the VCVS stamp in DC/AC/transient/Newton with no new solver code, and the finite-gain
  error is observable and testable (closed-loop error falls as ~1/A). `shortcut:` no bandwidth, slew,
  saturation or port impedances are modelled.

## D5. E and H are excluded from the voltage-source-loop check
- **Choice:** the union-find loop check only considers V sources (and DC-shorted inductors).
- **Alternative:** include E/H as voltage constraints.
- **Why:** a controlled source's output constraint depends on other unknowns, so an E in parallel with a
  node pair is not always singular (feedback loops are normal for op-amps). Genuinely singular cases still
  raise `SingularCircuitError` through the generic LinAlgError fallback.

## D6. Open-loop op-amp detection is a warning heuristic
- **Choice:** `OpenLoopWarning` when an E with |gain| >= 1e3 has no path from its output to its control
  nodes (avoiding ground and itself; capacitors count as paths).
- **Alternative:** no check, or an error.
- **Why:** open-loop use is legal (comparators), so warn rather than fail. `shortcut:` feedback through
  G/F sources is not seen, so it can warn falsely there.

## D7. F/H sense only V sources, with ngspice's sign convention
- **Choice:** the sense source must be a `V` element; current positive into its + terminal.
- **Why:** matches ngspice (verified by comparison tests in both orientations); other elements have no
  branch-current unknown to sense.

## D8. A netlist with no analysis directive runs `.op` (with a stderr note)
- **Choice:** the CLI falls back to `.op` and prints "no analysis directive; running .op".
- **Alternatives:** exit 1 with an error (ngspice itself just does nothing).
- **Why:** `divider.cir` and `ladder.cir` have no directive and are natural CLI demos; the note keeps it
  from being silent. Library calls (`op(...)`) are unaffected.

## D9. Sparse path: triplet assembly, SuperLU, dense for < 60 unknowns and for diodes
- **Choice:** `Triplets` records `A[i, j] += v` writes so the existing stamps are reused unchanged; CSC +
  `splu`; `solver="auto"` goes sparse at >= 60 unknowns (benchmark: dense wins or ties below ~60).
  Diode circuits stay dense (Newton edits a dense copy each iteration); explicit `solver="sparse"` on them
  raises ValueError, `auto` picks dense. (`shortcut:` noted in `sparse.check_solver`.)
- **Alternatives:** `dok_matrix`/`lil_matrix` assembly (slower, needs no custom class); sparse Newton.
- **Why:** smallest change that keeps one set of stamps; sparse Newton is a bigger rewrite that the
  task did not ask for (large circuits here are linear).

## D10. ruff added to the `dev` extra; config is line-length 125 and E741 ignored
- **Choice:** `pip install ruff` (listed in `pyproject.toml` dev extra; the CI lint step needs it);
  `line-length = 125`, `ignore = ["E741"]`; `ruff --fix` re-sorted imports in 9 files (no behaviour change).
- **Alternatives:** wrap the 25 long lines; rename every inductor variable `l`.
- **Why:** both would be churn across tested code; the longest existing line is 122 and `l` is the standard
  symbol for an inductor. No test was edited other than import order and one unused import.

## D11. Version comes from `spicelite.__version__` (0.7.0)
- **Choice:** `dynamic = ["version"]` in pyproject, `__version__ = "0.7.0"`; `--version` prints it.
- **Why:** pyproject still said 0.1.0. One source of truth. No git tag was created (not allowed here).

## D12. CI uses apt's ngspice and fails if any test is skipped
- **Choice:** `ubuntu-latest`, `apt-get install ngspice`, Python 3.10/3.11/3.12, ruff, pytest, CLI smoke test;
  the test step fails if the log contains "skipped", the same 0-skips rule as the local runs.
- **Risk (unverified):** apt's ngspice is not 41 (the version the tolerances were measured against), so a
  comparison could fail on GitHub even though it passes here. I cannot run the workflow without pushing.

## D13. "Empty netlist" is detected when solving, not when parsing
- **Choice:** `mna.check_topology` raises `SingularCircuitError("the circuit has no elements")`; `parse()` still
  accepts an element-less netlist.
- **Alternative:** `NetlistError` from `parse()` (with line number).
- **Why:** 9 existing tests parse element-less netlists to check directives or the title line, and I may not
  edit or weaken existing tests. Every analysis and the CLI go through `check_topology`, so nothing slips by.

## D14. CLAUDE.md command `python -m spicelite.ngspice ...` replaced by a pytest command
- **Why:** `ngspice.py` has no `__main__`, so the documented command never worked. A `--compare` CLI mode is the
  obvious feature if you want it (see REPORT.md).


# M8-M9 run (branch `m8-mosfet-adaptive`)

## D15. Branch cut from `overnight-m5-m7`, not main
- **Choice:** `main` does not contain M7 (the merge was blocked by the permission classifier), so the branch
  starts at `overnight-m5-m7` (35ecdb5), as the brief allowed.

## D16. ngspice "present" again means reachable through `$NGSPICE`
- Same as D1: `which ngspice` finds nothing, the bundled ngspice-41 is used and every committing run needs 0 skips.

## D17. Bulk junctions are reduced to GMIN conductances; no intrinsic capacitances
- **Choice:** each MOSFET stamps GMIN (1e-12 S) from bulk to drain and bulk to source, nothing else of ngspice's two
  bulk diodes. Cgs/Cgd/Cgb/Cbd/Cbs are skipped (`shortcut:` in `elements.py`, README limitation).
- **Alternatives:** full junction diodes (IS = 1e-14, exponential); a GMIN drain-source shunt instead.
- **Why:** ngspice's default-options results differ from the bare square law by exactly these GMIN terms (5e-12 A at
  Vds = 5 V on a 1.2 mA device), so modelling them lets the comparison use ngspice's defaults. It also stops a node touching
  only cut-off devices from being singular. A forward-biased bulk junction is the known gap (a test documents it).

## D18. VTO keeps its sign (negative for PMOS); W/L default to 100 um like ngspice
- Matches ngspice's cards, so the same `.model` text runs in both tools. W or L of zero or less is a NetlistError.

## D19. Singular-start fix lives in the device model, not in the Newton fallback
- A MOSFET circuit whose output node touches only cut-off devices made the first Newton matrix singular (the
  fallback only catches ConvergenceError). The GMIN junction conductances (D17) fix it at the source.

## D20. Newton limiting follows ngspice's mos1load
- `fetlim` on Vgs (or Vgd when reversed) then `limvds`, in the NMOS frame; "limited" is judged with a 1e-12 tolerance
  because rebuilding Vds through Vgd changes it by round-off (an exact comparison made Newton never converge).

## D21. Tests that filtered examples by `.diodes()` now filter by `.nonlinear()`
- `tests/test_vs_ngspice.py` and `tests/test_sparse.py` treated "no diodes" as "linear"; MOSFET examples are nonlinear too.
  This widens the nonlinear group, it does not weaken any test.

## D22. A second golden file freezes M7 results
- `tests/golden_m1_m7.json` (26 examples, from commit 35ecdb5 via `git archive`) joins the v0.6 file, so the controlled-source
  examples are protected against later changes as well.

## D23. Adaptive stepping is opt-in (`.options step=adaptive` or `adaptive=`); fixed-step stays the default
- **Choice:** default `step=fixed`; `tran(adaptive=False)` overrides the option.
- **Alternative:** adaptive by default.
- **Why:** every existing result, golden file and ngspice tolerance assumes the fixed grid, and the brief asks for the
  fast path to stay for fixed-step runs. The CLI prints whichever grid was used.

## D24. LTE estimator: divided differences of accepted points (no extra solve)
- **Choice:** trap |LTE| ~ h^3 |DD3| / 2, BE ~ h^2 |DD2| over the last accepted points, per unknown, against
  rtol max(|x|, |x_prev|) + floor. Controller: factor 0.9 r^(-1/(p+1)) clamped to [0.5, 2], then rounded DOWN to hmax / 2^k.
- **Alternatives:** step doubling (3 solves per step, simple but 3x the cost); predictor-corrector difference (needs an explicit
  predictor for each element type, the same number mathematically); Richardson with an embedded BE/trap pair.
- **Why:** free (history is already kept), well understood (the SPICE estimator), and the power-of-two grid makes the cached LU
  factors reusable so a linear run pays few factorisations.

## D25. Breakpoints restart the history at `tstep`; no BE start-up step after a corner
- Landing exactly on PULSE/SIN corners and discarding the history there keeps the third difference from straddling a corner.
  `shortcut:` a source with ZERO rise time leaves the trapezoidal capacitor-current history stale for one step (documented
  in `adaptive.py`); use a nonzero rise time or method=be.

## D26. Default rtol = 1e-4 (not 1e-3), hmax = tstop / 50, hmin = tstop x 1e-9
- **Why rtol 1e-4:** at 1e-3 the Q ~ 10 ringing example is only 2e-2 / 4e-2 (V / I) of peak against ngspice because per-step error
  accumulates over ~20 periods; 1e-4 gives 4.7e-3 / 9.4e-3 with ~2150 steps (ngspice uses ~20000). rtol 1e-5 gives 1.1e-3.
- hmax / hmin guard values are overridable with `StepControl`.

## D27. `.ic` / UIC already existed (M6); this phase adds the example, the analytic and ngspice checks and adaptive support
- The brief asks for UIC to remove the M4 "capacitor-only circuits rejected" limitation; M6 had already done that, so Phase 2 only adds
  `rc_ic_discharge.cir` (and a test of a capacitor-only loop) rather than re-implementing it.

## D28. `stiff_adaptive` is excluded from the generic ngspice transient loop and gets its own test
- ngspice runs with tmax = tstep / 10 = 0.1 ns there, i.e. ~5e8 points. `test_adaptive.py::test_stiff_adaptive_matches_ngspice`
  runs it with `tmax_fraction=1e4` (tmax = 10 us). No other example is excluded.

## D29. Audit fixes
- magnitude_db returns -inf for an exact zero without a numpy warning (a supply rail has no AC signal); the CLI had been printing the warning.
- The report from the M5-M7 run was renamed REPORT_M5_M7.md; REPORT.md is the M8-M9 report.

# Web UI run (branch `web-ui`)

## D30. Pyodide route is GO; pinned to Pyodide 314.0.7 (Python 3.14.2, numpy 2.4.6, scipy 1.18.0)
- spicelite declares requires-python >=3.10 with no upper cap and uses only numpy and scipy (linalg, sparse) on the web path.
  `import spicelite` and the analyses do not import matplotlib, the subprocess-based ngspice runner, plotting or cli (checked via sys.modules), so no
  code change was needed for the "no CLI-only imports on the web path" requirement.
- **Install method:** the pure-Python wheel built with `pip wheel . --no-deps` is unpacked with `pyodide.unpackArchive(Uint8Array, "wheel")` after
  `loadPackage(["numpy", "scipy"])`. Alternative: micropip (also works, costs an extra package download and resolves dependencies we do not want:
  matplotlib is in the wheel metadata). A Node Buffer must be converted to a Uint8Array first (Pyodide rejects it).
- **Where Pyodide is served from:** the jsdelivr CDN at the pinned version URL, not self-hosted (the wasm plus numpy plus scipy are tens of MB, and Pages
  repo size and deploy time would balloon). The npm `pyodide` package is a dev dependency used for TypeScript types and the headless Node tests.
  Risk: first load needs the CDN; the browser caches it afterwards.

## D31. Dev tooling
- Node 26 / npm 11 are available; Vite and Playwright are installable from npm (network works), so the frontend is Vite + TypeScript.

## D32. JSON shape and guards (web_api.py)
- Result: {ok, title, version, warnings, analyses:[{type, title, x:{name, unit, log, values}|null, signals:[{name, unit, values, part}], meta}]}.
  AC signals are magnitude (dB) and phase (deg) pairs distinguished by `part`; non-finite numbers become null so the output is strict JSON
  (an AC-quiet supply rail is -inf dB). .op has x = null (a table, not a curve). No analysis directive runs .op with a note, as the CLI does.
- Guards (Limits, all overridable through options): 200,000 characters, 500 nodes (100 with diodes/MOSFETs: dense Newton), 100,000 points per analysis,
  points x elements <= 2,000,000 (x5 for nonlinear), 30 s wall clock. Size and cost are checked BEFORE running; adaptive transients get a max_steps budget
  derived from the same limits. **Runtime limit caveat:** one analysis cannot be interrupted from inside Python (Pyodide has no threads or signals), so
  the time budget is checked between analyses and the worker additionally terminates itself on a hard timeout (Phase 3). Alternative: a deadline callback
  threaded through every analysis loop; rejected as invasive for the core library.
- CLI golden outputs (tests/golden_cli/*.txt) were generated from the CLI before any web change, so the regression test really compares against the old behaviour.

## D33. Frontend stack: Vite 8 + TypeScript 7, uPlot, CodeMirror 6, IBM Plex via @fontsource, Vitest
- **Charts: uPlot, not Plotly.js.** uPlot is ~50 kB (Plotly is ~1 MB even in its basic bundle), handles 100k points at 60 fps, and has what was asked for
  built in: live hover readout (legend), drag zoom, double-click reset, clickable legend toggling, log x scale, and cursor/zoom sync for the Bode pair.
  Costs: less default polish (styled in style.css) and no built-in dual axes (voltages and currents get separate plots instead, which is also clearer).
- **Editor:** CodeMirror 6 with a small StreamLanguage SPICE grammar (title line, * comments, dot commands, element names, numbers with SI suffix incl. meg,
  waveform words, key= parameters), an error gutter and error-line decoration. Colors are CSS variables so the theme switch needs no editor rebuild.
- **Fonts self-hosted** (latin subsets of IBM Plex Sans/Mono via @fontsource, ~170 kB total) instead of Google Fonts: no third-party request, works offline after first load.
- **New npm dependencies:** uplot, codemirror (state, view, language, commands), @lezer/highlight, @fontsource/ibm-plex-*, pyodide (types + Node tests); dev: vite, typescript,
  vitest, @playwright/test, @types/node. Bundle: ~375 kB JS (129 kB gzip), 13 kB CSS.
- **Vite `base: "./"`** so every asset URL is relative and the site works from any sub-path (GitHub Pages /spice-lite/). The worker receives an absolute wheel URL
  built from document.baseURI because a relative fetch inside a worker would resolve against the worker file.

## D34. Look and feel: engineering notebook by day, oscilloscope by night
- Light = warm paper with graph-paper grid, ink blue lines, vermilion Run button. Dark = graphite-green with phosphor traces and an amber Run button. IBM Plex Mono for
  anything numeric or code, Plex Sans for prose. Theme follows prefers-color-scheme with a manual Auto / Light / Dark button (stored in localStorage, applied before first paint).
- Traces use the Okabe-Ito color-blind-safe palette (darkened on paper, brightened on dark) AND eight dash patterns, so color is never the only cue; error state uses an icon,
  a text label and a gutter marker as well as red. The table view is the accessible alternative to every plot.

## D35. Running and sharing
- **Run coalescing:** while a run is in flight, further clicks set a single "run again" flag; the stale result is dropped and one more run starts with the latest text.
- **Hard timeout:** the engine terminates the worker after 60 s (Python cannot be interrupted any other way) and boots a fresh one on the next run. This is the real runtime
  limit; run_netlist only checks the budget between analyses (D32).
- **Share links:** `#ex=<name>` for an unmodified bundled example (short), otherwise `#n=<base64url>` or `#z=<base64url of deflate-raw>` (chosen when shorter), decoded with
  the browser CompressionStream. Editing detaches from the example name and rewrites the hash after 400 ms.
- **Caching:** the Python runtime, numpy and scipy come from the jsdelivr CDN and are cached by the browser's HTTP cache after the first visit; no service worker (a second cache
  to invalidate for little gain). The worker stays alive for the page lifetime, so later runs reuse the loaded interpreter.

## D36. Reference overlay: precomputed, resampled onto spicelite's grid, committed to the repo
- `scripts/gen_reference.py` runs each example through the existing ngspice runner (tightened options as in the comparison tests; tmax_fraction 1e4 for
  stiff_adaptive) and stores ngspice's curves interpolated onto spicelite's own x grid, so the page just subtracts. If the browser's grid differs slightly (adaptive
  stepping can choose marginally different steps under Pyodide's BLAS) the page re-interpolates linearly onto its own grid (`resample`, unit-tested).
- **Committed, not built in CI:** ngspice is not available on the Pages build and apt's version differs from 41, which the tolerances and these curves were measured against
  (893 kB for 33 examples). Regenerate with `npm run reference` (needs NGSPICE).
- Drawn dashed in the ink color over the coloured traces, so agreement is visible as the colour showing through the gaps; labelled "precomputed, not a live run" in the
  toggle tooltip and the error panel. The panel lists the largest difference per plot (dB / degrees for AC, volts / amps and fraction of peak otherwise) and, for `.op`,
  adds ngspice and difference columns to the table. The toggle exists only while the editor still equals the bundled example text.

## D37: Frontend test strategy, deploy, and CI (Phase 5)
- **Tests:** vitest for pure logic (hash round trip, formatting/CSV, reference resampling, palette contrast) plus one test that boots real Pyodide in Node, installs the freshly built wheel and runs all 33 examples against the committed ngspice reference (tolerances in the file, with reasons). Playwright for end-to-end: it drives the built site via `vite preview`, and a second spec serves `dist/` under `/spice-lite/` with a tiny Node server to prove sub-path hosting (`base: "./"`).
- **Alternatives:** jsdom component tests (would not exercise the worker, uPlot canvas or Pyodide); a Playwright-downloaded browser locally (needs a download; the machine has Edge, so `PW_CHANNEL=msedge`, and CI installs Chromium).
- **Pages:** `pages.yml` builds wheel + site on push to main and deploys with the official upload-pages-artifact / deploy-pages actions. Needs the repository setting Pages > Source = GitHub Actions (a manual step for the owner).
- **CI:** a separate `web` job (typecheck, `npm test`, build, e2e) so the Python matrix is untouched. Its first run has not happened (nothing is pushed); the Pyodide test and e2e need network access to the jsdelivr CDN.
- **Screenshots** in `docs/web_ui_*.png` are captured headlessly with `web/scripts/shoot.mjs`; no GIF.
