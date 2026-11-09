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

## D38: Report naming
The M8-M9 report moves to `REPORT_M8_M9.md` (as the M5-M7 one did earlier) and `REPORT.md` is now the web UI report. Alternative: `REPORT_WEB.md`; rejected to keep "REPORT.md = latest run".

# Stamping refactor run

## D39: Element-dispatch audit (Phase 1, before the refactor)
Every place the code branches on element type, and what it handles (✓ handled, – deliberately not applicable, ✗ gap).

| Site | R | C | L | V | I | D | M | E | G | F | H | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `parser.py` element letters (`rclvidegfhm`) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | source of truth for what a netlist can contain |
| `mna.build` (DC, AC, t = 0 solve; Newton's linear part) | ✓ | ✓ | ✓ | ✓ | ✓ | guard | **✗** | ✓ | ✓ | ✓ | ✓ | D raised `NotImplementedError` unless Newton asked; **M fell through and stamped nothing** (bug, fixed with a test first) |
| `tran.matrix` (companion matrix per step size h) | ✓ | ✓ | ✓ | ✓ | – | – | – | ✓ | ✓ | ✓ | ✓ | duplicate of the `mna.build` chain; I is RHS-only; D and M are stamped by Newton each iteration |
| `tran.step` RHS (sources at t) | – | hist | hist | ✓ | ✓ | – | – | – | – | – | – | a third, smaller copy of the source RHS logic; C/L history currents are transient-only by design |
| `ac._diode_solver` (small-signal) | via build | via build | via build | via build | via build | ✓ | ✓ | via build | via build | via build | via build | separate loops: diodes then MOSFETs, each with its own bias extraction |
| `newton._newton` (per-iteration linearisation) | – | – | – | – | – | ✓ | ✓ | – | – | – | – | device-specific limiting and residual checks; by design |
| `circuit.branch_elements` | – | – | ✓ | ✓ | – | – | – | ✓ | – | – | ✓ | extra unknown = current through a voltage-defined branch |
| `circuit.element_nodes` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | |
| `mna.check_topology` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | conduction / voltage-loop rules per type |
| `tran._frozen_state_system` | – | ✓ | ✓ | – | – | – | – | – | – | – | – | holds C as a V source and L as an I source; by design |
| `adaptive.breakpoints`, `tran._warn_if_edges_unresolved` | – | – | – | ✓ | ✓ | – | – | – | – | – | – | only sources have waveforms |
| `web_api._dc` | – | – | – | ✓ | ✓ | – | – | – | – | – | – | sweep unit V or A |

Findings: two real duplications (`mna.build` vs `tran.matrix`, and the source RHS in `mna.build` vs `tran.step`), one bug (MOSFET in `mna.build`),
and a third dispatch in `ac._diode_solver`. The remaining sites are per-type *rules* (topology, nodes, waveforms), not stamping, and stay where they are.

## D40: One stamping path: a registry of functions, not methods on the element classes (Phase 2)
- **Choice:** `elements.STAMPS: dict[type, Stamp]`. Each `Stamp` splits an element's contribution by what it depends on:
  `matrix(A, idx, rows, e, s)` (s = 0 at DC, jω at AC, 1/h or 2/h in a transient: never time or the solution),
  `rhs(b, idx, rows, e, value)` (independent sources), `newton` (linearised per iteration by `_newton`), and
  `small_signal(idx, e, x_bias) -> stamp(A)` (a nonlinear device's AC model, linearised once per sweep).
  `mna.stamp_matrix` / `mna.stamp_sources` are the only loops over elements; `mna.build`, `tran`'s companion matrix (still factored
  once per step size, cache of 64 kept), `tran`'s per-step RHS and `ac`'s small-signal path all go through them.
- **Alternatives:** methods on the dataclasses (`Resistor.stamp_matrix(...)`); `functools.singledispatch`.
- **Why:** `circuit.py` is plain data and CLAUDE.md keeps stamps in `elements.py` (one function per element, with the stamp
  pattern in its docstring); methods would split that across two files or move the numpy code into the data model.
  A plain dict is explicit, easy to enumerate in a test, and a missing entry is a `TypeError` instead of a silent no-op.
  The original `stamp_*` functions are kept unchanged (their hand-checked unit tests still apply); the registry wraps them.
- **Kept outside the registry (by design):** C/L history currents of the companion models (they belong to the integration method and
  exist only in `tran`); `_newton`'s device-specific limiting and residual checks (now guarded by `NEWTON_DEVICES`); topology rules.
- **Guard:** `tests/test_stamp_registry.py` (every parser letter -> class -> registry entry valid for every analysis; an unregistered class raises).
  Checked by deleting the CCVS entry: two tests fail.

## D41: Performance check method
The 10% budget is judged on a same-session A/B (old `src/` from `git archive` vs new, alternated, best of N), because the stand-alone
benchmark moved by up to 39% between runs on an idle machine. Result: every workload within ±6% (table in REPORT.md). The registry lookup is
inlined on the assembly path (`STAMPS.get(type(e))`); per-step RHS functions are resolved once before the time loop.

## D42: MOSFET capacitances as hidden linear capacitors (Phase 3)
- **Choice:** `Stamp.expand` (new registry hook; the diode's RS expansion moved there too) turns a MOSFET into itself plus
  `Capacitor("<name>#cgs" ...)` elements: Cgs = CGSO W, Cgd = CGDO W, Cgb = CGBO L (ngspice's scaling with LD = 0), Cbd = CBD,
  Cbs = CBS. Zero values add nothing, so a model without capacitances is exactly the M8 device (bit-for-bit test + goldens).
- **Alternatives:** a MOSFET-specific companion stamp in `tran` and a jωC stamp in `ac` (two new code paths, the duplication this
  run removed); full Meyer charge model (needs TOX and region-dependent charge partitioning, out of scope).
- **Why:** capacitors already have one stamp, one companion model, history currents and `.ic` handling; reusing them means AC and both
  transient modes are correct by construction. Only the overlap terms are compared with ngspice: with CBD/CBS set ngspice applies the
  depletion law, which this version does not (README limitation, `shortcut:` note in elements.py).
- **The inverter example is driven through 1k.** With the gate on an ideal source, the PMOS Cgs sits between two ideal sources and
  fixed-step trapezoidal integration rings undamped on its current (alternating 2.4 / 0.6 mA around ngspice's 1.6 mA: 11 % of peak
  on i(vdd)); 50 ohm damps the ringing but leaves the RC (6 ps) under-resolved by the 12.5 ps step; 1k (tau ~ 120 ps) is resolved:
  worst 4.4e-4 of peak, tolerance 2e-3. Fixing the integrator (a backward-Euler step after each corner) would change existing results,
  which this run forbids; recorded as a README limitation and a next step.

## D43: Parallel capacitors with uic (bug found in Phase 3, present on main)
`_frozen_state_system` held each capacitor as a voltage source, so two capacitors on the same node pair were a "loop of voltage
sources" and `.tran ... uic` failed. Fix: one held source per node pair; its current is split by capacitance (same dv/dt), with the
sign flipped for a reversed one. A single capacitor per node pair goes through the same code with ratio 1, so existing results are
unchanged (goldens). A capacitor directly across a voltage source with uic is still an error: the two can disagree (inconsistent .ic).

## D44: Report naming (refactor run)
The web UI report moves to `REPORT_WEB.md`; `REPORT.md` stays the latest run, as with `REPORT_M5_M7.md` and `REPORT_M8_M9.md`.


# UI polish run

## D45: Tools evaluated (Phase 1)
Every tool was cloned into the session scratchpad as read-only data (nothing executed). The README and every SKILL.md / rules file of the
part actually followed was read in full before use; the rest of each repository was safety-scanned (network fetches, global installs,
hooks, writes outside the repo, credentials). Installed skills go to this repository's `.claude/skills/` only, never `~/.claude`.

| Tool | Verdict | Why |
|---|---|---|
| StageShow (benjitaylor/skills, MIT) | partly used | It is a skill whose kit is React + lucide-react; the brief forbids adding a framework. Its principles are followed by hand in the landing demo: 3-5 beats and a payoff, values that move instead of swapping, a poster frame that tells the story alone (shown under reduced motion), a loop that resets with a visible cause, real words only on the focal parts. Kit not installed. |
| Impeccable (pbakaus, Apache-2.0) | partly used | Setup runs a launcher that downloads a self-contained binary on first run (a network-fetched executable), and an optional hook auto-runs a detector: not allowed. Used through its own documented "launcher unavailable" path: `craft-floor.md` (quality floor and refuse list), `mode-operate.md` (the app: the world lends type, palette, density and one signature move, never a costume of an instrument), `mode-persuade.md` (the landing section) and `animate.md`. Not installed. |
| Dimensional Drawing (enesozturk, MIT) | used, installed | Pure instructions plus two example HTML sheets; no scripts in the drawing skill. Drives the element spec sheets (monochrome line, title block, coded values, numbered notes, `[TBD]` instead of invented values). The motion sub-skill (Playwright + ffmpeg film) is not needed and not installed. |
| Oil UI (oil-oil, license not stated in the repo root) | partly used | Runs an update check (`check_update.sh`, network) and an upsell script, and its image generation spends paid credits: none of that is used. Its explicit-exploration method is followed by hand: three directions that share at most one of layout, typography, colour and key imagery; first screen only; compared side by side at 480 px and chosen with written reasons when unattended. Not installed. |
| Emil Kowalski skills (MIT) | used, installed | `animate` and `review-animations` (with RECIPES.md and STANDARDS.md): pure instructions. They set the motion rules (frequency gate, named purpose, transform/opacity, strong ease-out curves, UI under 300 ms, reduced motion and hover gating shipped with every animation) and the Phase 6 motion review. The other 16 skills (Swift, Expo, mobile, gestures, Sonner, ...) do not apply to this stack and were not read. |
| Taste Skill (Leonxlnx/taste-skill 2.5.1; the brief's "LeonxInx" spelling does not exist) | partly used | Its frontmatter registers a Claude Code Stop hook that runs `gate.mjs`, and its pipeline downloads photographs and icons: not installed. It targets company marketing sites; the "dials" the brief mentions are in older versions. Rules taken: no fade-in on every section or scroll-jacking, no violet, one button / card system, 44 px tap targets, nothing hidden under reduced motion, no invented figures, every control answers the pointer. Found on the second attempt (`gh search repos`). |
| Brand Identity (fatihaydost, MIT) | partly used | The Python pipeline installs its own packages via uv and fetches Google Fonts, a full run costs ~0.9 M tokens (its README), and it stops for the user to pick. Its method is followed by hand: one mechanism that yields mark, type and palette; the reflex test against `ai-defaults.md` (no Inter, Fraunces, Space Grotesk/Sora, cream-terracotta, violet-in-tech); a mark drawn on a 100-unit grid from filled primitives and judged flat at 16 and 32 px; contrast measured, not asserted. Not installed. |
| Awwwards MCP (INSANE0777/Awwwards) | skipped | Not configured in this session (the brief: use only if already configured), and the repository name does not resolve. Replaced by reading Linear, Falstad's circuit simulator and Wokwi (first-viewport layout, type and motion), via a fetch agent. |
| Kokonut UI (MIT) | studied | React + Tailwind + Motion; not added. Pattern taken and rebuilt natively: a bento of capability tiles where each tile holds a small live diagram rather than an icon. |
| Bklit UI (bklit/bklit-ui, MIT) | studied | React charts library; ui.bklit.com redirects to bklit.com (not the catalog); found on GitHub. Pattern taken: charts that draw their line in once on mount and a value that rolls to its new number. |
| Manus.im | studied | Public site only, for composition: one centred line, an action directly under it, the product shown right below. No branding, copy, images or code taken. |

## D46: Animation engine: none (CSS + Web Animations API), 0 kB
- **Measured** (esbuild, minified, gzip -9, a bare `animate()` import): Motion `animate` 28.4 kB; Motion `motion/mini` 3.7 kB;
  anime.js 4.5 `animate` 13.3 kB.
- **Choice:** no library. Every planned motion (staged loading bar, tab change, plot reveal, number tickers, change highlight, error
  entrance, button press, theme change, toast) is a CSS transition or keyframe, or one `element.animate()` call; the tickers are a short
  `requestAnimationFrame` loop. Emil's rule "cheapest tool that works; don't install a motion library for a fade".
- **Alternatives:** `motion/mini` (3.7 kB) if springs or interruptible sequencing are ever needed; anime.js costs more for features
  (timelines, SVG morphing) this UI does not use.


## D47: Design direction: A, Datasheet (Phase 2)
Three directions were built as CSS overlays on the real app (`docs/ui-directions/*.css`, rendered by `web/scripts/directions.mjs`
with their fonts embedded; nothing was forked). All three keep the working two-pane layout, so any two share only layout (Oil UI's rule:
at most one of layout, typography, colour, key imagery). Compared side by side at 480 px (`docs/ui-directions/sheet.png`).

| Direction | Type | Palette | Density | Signature move |
|---|---|---|---|---|
| **A Datasheet** | Archivo + JetBrains Mono | white, black ink, one signal blue | dense, hairlines, 2 px radius | plots numbered and captioned "Figure N." like a datasheet's characteristic curves |
| B Drafting vellum | Public Sans + IBM Plex Mono | warm vellum, graphite, vermilion | medium, square, 1.5 px rules | the header set as a drawing title block |
| C Night bench | Geist + Geist Mono | blue-black, copper, amber | airy, 12-16 px radius | a resistor colour-code band on the active tab and Run |

Scorecard (1-5):

| Criterion | A | B | C |
|---|---|---|---|
| Legibility of plots | 5: black hairlines on white, the most contrast for traces | 4: the vellum ground lowers trace contrast | 4: traces pop, the grid fades |
| Contrast | 5 (ink 18.6:1, muted 6.9:1) | 4 | 4 |
| Distinctiveness | 4: no other simulator dresses as a datasheet; pane-less full-bleed | 4 | 2: dark dev tool in Geist is the category default |
| Fit for a circuit simulator | 5: EE students read datasheets daily | 3: drafting belongs to mechanical and architecture | 3: the bands are decoration, colour-only |
| Mobile | 4 | 3: the title block breaks awkwardly at 360 | 4 |
| **Total** | **23** | 18 | 17 |

Chosen: **A**. Rejected directions stay as screenshots (`docs/ui-directions/b-*.png`, `c-*.png`) beside their CSS. Impeccable's Operate
rule holds: the world lends type, palette, density and one signature move (the figure captions); controls stay standard web controls.

## D48: Brand system (Phase 2)
Method from the Brand Identity skill, by hand (D45). **Mechanism:** every result is a figure you could print in a datasheet; the mark is
Figure 1, an RC step response v = 1 - exp(-t/RC) on its axes (the first curve spice-lite was validated against), drawn on a 100-unit
grid (`web/public/brand/mark.svg`; favicon cut with heavier strokes on a paper tile so it reads on dark tabs: `web/public/favicon.svg`,
`favicon-32.png`, `apple-touch-icon.png`, generated by `web/scripts/brand.mjs`). Wordmark: "spice·lite" in Archivo 700, the node dot in
Signal blue. Reflex test: no AI-default face (Inter, Fraunces, Space Grotesk, Sora), no violet, no initial-in-a-tile, no spark or
gradient orb. Palette and measured contrast in `docs/brand/brand-sheet.png`: Ink #111316 (18.6:1), Signal #0b4f9c (8.0:1), Graphite
#555b63 (6.9:1), Fault #a31919 (7.7:1), Rule #b9bec6 (hairlines only, 1.9:1, never text); dark: Night #0e1013, Night ink #e8eaed
(15.8:1), Night signal #7cb2ff (8.8:1). Type: Archivo 400/600/700 for UI, JetBrains Mono 400/600 for the netlist and numbers only
(Impeccable: monospace for code and measurement, not as a "technical" costume).


## D49: Design system (Phase 3)
- **Tokens** in `web/src/style.css`: type (`--sans` Archivo, `--mono` JetBrains Mono, a 7-step size scale), space (4 px steps,
  `--s1`..`--s8`, `--gutter`), shape (`--r1` 2 px, `--r2` 4 px, hairline and strong rules), shadow (`--shadow-pop`, for the toast only:
  a datasheet has no shadows), motion (`--dur-1`..`--dur-4` 120-300 ms, `--dur-reveal` 600 ms for the one authored plot reveal,
  `--ease-out` / `--ease-in-out` from Emil Kowalski), and colour. Light and dark are the same token names with different values; the
  contrast test (unchanged) checks every text, state, syntax and trace pair in both themes (37 checks pass).
- **Layout:** the two panes run full bleed, split by one black hairline; the header sits on a 2 px ink rule and the footer on a 1 px
  one (a datasheet page), replacing the floating rounded cards and the graph-paper background.
- **Components:** tabs carry a 3 px signal underline (no folder tabs); the Plot / Table switch is ink-filled when pressed; tables are
  characteristics tables (strong top rule, sunken header, mono values right-aligned, sans for words); the gutter is sunken like a table
  column; buttons and the select are 38 px tall (32 px for in-panel controls); the reference panel lost its 3 px coloured left border
  (an Impeccable refuse-list item); monospace now appears only for the netlist, numbers, legends and axes.
- **Plots:** the trace colours and their dash patterns are unchanged (Okabe-Ito, colour-blind safe, never colour alone).
- **Browser surfaces:** text selection, caret, scrollbars, focus ring, link underline offset and tabular numerals are themed.
- **Fonts:** `@fontsource/archivo` (400/600/700) and `@fontsource/jetbrains-mono` (400/600) replace IBM Plex Sans/Mono: self-hosted
  latin subsets with `font-display: swap`, no third-party font request at runtime. Font files are data, not code; recorded per the
  dependency rule.


## D50: Motion (Phase 4)
Rules: Emil Kowalski's `animate` / `review-animations` (installed, D45), Impeccable's `animate.md`, Taste's never-list. No library (D46).
Thesis: one authored moment (the plot reveal); everything else is feedback or state, short and quiet; nothing moves for redraws.

| Motion | Purpose | Ingredients | Frequency gate |
|---|---|---|---|
| First-load bar | state: which of the three worker steps is running | determinate fill, `transform: scaleX` to (k - 0.5)/3, 300 ms ease-out, "Step k of 3" text, `role=progressbar` | once per visit |
| Plot reveal | the authored moment: a NEW result draws in | a surface-coloured mask over uPlot's plot area slides off (`scaleX` 1 -> 0, origin right), 600 ms ease-in-out; axes readable from frame 0; once per result and panel, never on tab switch, Plot/Table toggle, theme change, overlay, zoom or hover | once per run |
| .op ticker | state: a re-run changed this value | rAF roll from the old value to the new, 300 ms ease-out, ends on the exact formatted text | only changed values, only after a re-run |
| Change wash | state: which cells changed | `accent-soft` background fading to transparent, 1.4 s, colour only | same |
| Error panel / warnings | feedback: something needs reading | opacity + 4 px rise, 240 ms ease-out | per failed run |
| Gutter marker | points at the line | scale 0.6 -> 1 with a fading ring, 300 ms | per failed run |
| Tab change | continuity | underline `scaleX` 180 ms; panel opacity only, 120 ms (tabs are used tens of times a day) | frequent: near-imperceptible |
| Button press | feedback | `scale(0.97)` 120 ms ease-out; hover colour gated behind `(hover: hover) and (pointer: fine)` | frequent: subtle |
| Theme toggle | explains a page-wide palette change | View Transitions cross-fade 240 ms; instant where unsupported | rare |
| Copy link | confirmation on the control itself | label "Link copied" + signal border for 1.6 s, plus the existing toast (opacity + 8 px, 180 ms) | occasional |

- **Not animated** (by the frequency gate): Run itself (press feedback only), Ctrl/Cmd+Enter, the examples `<select>` (a native control: its menu is the platform's, so no custom open/close motion), legend toggles, zoom.
- **Properties:** transform and opacity everywhere except the change wash (background colour, by design) and the view-transition cross-fade. No `transition: all` (the old toast had one; removed).
- **Reduced motion:** no reveal mask, no scale or movement (button press, gutter pulse, tab underline, toast), the error panel only fades,
  the ticker jumps to the final value; the wash and the determinate bar stay (they carry meaning without movement). Tested in e2e.
- **Main thread:** the reveal and the bar are CSS; the ticker is a 300 ms rAF loop after results arrive; nothing animates while the
  worker is computing except the CSS bar during first load.
- **Review** (`review-animations`, self-run, Approve after two fixes): the gutter pulse was 420 ms (over the 300 ms UI budget) -> 300 ms;
  the reveal mask let a trace lying on the plot border show ahead of the sweep -> the mask now overhangs by 2 px. The 600 ms reveal is
  kept deliberately: it is the one authored moment (Impeccable: 500-800 ms for a focal entrance), it runs once per result.
- **Also fixed here** (found in the earlier code review): Ctrl/Cmd+Enter in the editor ran the netlist twice (the editor and the page
  both handled it). The page listener now ignores keys the editor already handled; an e2e test counts renders.
- **Tests:** `web/tests/motion.test.ts` (stages match the worker's messages, easing endpoints) and four e2e tests (reveal once,
  reduced motion, changed-value roll and mark, single run on Ctrl+Enter).
