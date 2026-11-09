# Report: single stamping path and MOSFET capacitances (branch `refactor-stamping`)

Started Mon Nov 9 15:26:52 EST 2026 (per `date`), finished about 16:30: all four phases inside the 1 h 40 m box. Nothing was pushed or tagged.
Previous reports: `REPORT_WEB.md` (web UI), `REPORT_M8_M9.md`, `REPORT_M5_M7.md`.

## Bugs found (both fixed with a failing test first)
1. **`mna.build` / `mna.solve` silently dropped MOSFETs.** The guard that stops a nonlinear device from being built without Newton
   covered diodes only; a MOSFET circuit built directly came back with the transistor missing and a plausible answer. The analyses
   themselves were unaffected (they route MOSFET circuits through Newton), so no published result was wrong, but the public `mna`
   API was. Test: `tests/test_edge_cases.py::test_mna_build_refuses_a_mosfet_instead_of_silently_dropping_it`.
2. **`.tran ... uic` failed for any two capacitors in parallel** ("closes a loop of voltage sources"), on `main` too: the t = 0
   state held every capacitor as a voltage source. Now one source per node pair, current split by capacitance (D43).
   Test: `tests/test_edge_cases.py::test_parallel_capacitors_with_uic_start_from_the_ic_instead_of_failing`.

## What changed
- **Phase 0, safety net.** `tests/golden_refactor/`: the CLI's own `--csv` output (repr floats) for every example, plus a sparse-solver
  set for the linear ones; `tests/test_regression.py` compares every sample at rtol 1e-12. The existing golden tests only compared
  summary statistics at 1e-9 and missed the M8/M9 examples; they are kept. `benchmarks/bench_sparse.py` now also times adaptive
  `.tran`; `benchmarks/bench_examples.py` times the nonlinear and adaptive examples.
- **Phase 1, audit.** Dispatch table in DECISIONS D39 (summary below).
- **Phase 2, one stamping path.** `elements.STAMPS` maps each element class to a `Stamp`: the matrix part that depends only on s, the
  source value, a Newton flag, the small-signal AC model and an expansion. `mna.stamp_matrix` / `mna.stamp_sources` are the only loops
  over element types; `mna.build`, the transient's companion matrix (still factored once per step size, cache of 64), its per-step
  source vector and the AC small-signal path all use them. The voltage-source stamp now shares the V/E/H skeleton. `_newton` refuses
  device types it cannot linearise. Guard: `tests/test_stamp_registry.py` (checked by deleting one entry: it fails). Why a registry
  rather than methods on the element classes: D40.
- **Phase 3, MOSFET capacitances.** `CGSO`, `CGDO` (F/m of width), `CGBO` (F/m of length), `CBD`, `CBS` (F) become hidden linear
  capacitors through `Stamp.expand` (D42), so AC and both transient modes use the ordinary capacitor stamp and companion model. Meyer
  gate capacitance and the junction depletion law are skipped (`shortcut:` note, README limitation). New examples
  `cmos_inverter_overlap.cir` and `nmos_cs_bandwidth.cir`.
- **Phase 4.** README (models row, MOSFET syntax, limitations), web reference data for the two new examples, this report.

## Dispatch table, before and after
| Site | Before | After |
|---|---|---|
| `mna.build` | if/elif over 9 linear types; D guarded; **M fell through** | `stamp_matrix` + `stamp_sources` over the registry; D and M raise unless Newton asked |
| `tran` companion matrix | its own copy of the 8-type chain | `stamp_matrix(..., s = 1/h or 2/h)` |
| `tran` per-step sources | its own V / I branch | registry `rhs` functions, resolved once before the time loop |
| `ac` nonlinear path | separate diode and MOSFET loops, bias extraction inline | registry `small_signal`, linearised once per sweep |
| `newton._expand` | diode RS special case | registry `expand` (diode RS, MOSFET capacitances) |
| `newton._newton` | diodes / MOSFETs by isinstance, anything else ignored | same, plus an error for any other device |
| topology, `element_nodes`, `branch_elements`, waveform breakpoints | per-type rules | unchanged (rules, not stamping) |

## Tests
| Run | Result |
|---|---|
| Baseline (`main`, ngspice on) | 718 passed, 0 skipped |
| After Phase 0 / 1 / 2 / 3 | 775 / 776 / 791 / 809 passed, 0 skipped |
| **Final** (`pytest -q`, ngspice 41 via `NGSPICE`) | **809 passed, 0 skipped**; `ruff check .` clean |
| Golden outputs (all 33 original examples, dense and sparse) | identical to rtol 1e-12 after every phase |
| Every example through the CLI | 35 / 35 ran |
| Frontend `npm test` (unit tests + every example in real Pyodide vs the ngspice reference) | 103 passed |
| `npm run build`, then Playwright e2e (Edge, including the `/spice-lite/` sub-path) | build OK (JS 129 kB gzip, unchanged); 16 passed |

One existing test changed its example input: `test_mosfet.py` used `CGSO=1p` as an *unsupported* parameter; it now uses `TOX=1n`
(still unsupported), so it checks the same error path. No test was deleted, skipped or loosened.

## ngspice agreement for the new capacitances
| Circuit | Analysis | Tolerance | Observed worst |
|---|---|---|---|
| `nmos_cs_bandwidth`, CGSO = CGDO = 5 nF/m | `.ac` | 1e-6 relative | 9.1e-13 |
| same, capacitances removed | `.ac` | 1e-6 relative | 9.1e-13 |
| `cmos_inverter_overlap` (0.1 pF load, CGSO = CGDO = 2 nF/m, 1k gate drive) | `.tran` | 2e-3 of peak | 4.4e-4 (generator current) |
| same, capacitances removed | `.tran` | 2.5e-2 of peak | 5.6e-3 (supply current, faster edges) |

Analytic checks: the Miller pole Rs (Cgs + Cgd (1 + |A|)) = 34 MHz matches the simulated -3 dB point within 25 % (the overlap capacitance
cuts the bandwidth from ~400 MHz to ~30 MHz); CBD alone and Cgs + Cgd + Cgb discharge as RC exponentials to 1e-4 / 1e-5; zero
capacitances are bit-identical to the M8 device.

## Timing (same-session A/B: old `src/` from `git archive` vs new, best of N, idle machine)
| Workload | Before | After | Change |
|---|---:|---:|---:|
| `.op` sparse, 1000-section ladder | 13.3 ms | 11.6 ms | within noise |
| `.tran` dense, 100 sections | 73.4 ms | 71.8 ms | -2 % |
| `.tran` sparse, 1000 sections | 255 ms | 249 ms | -2 % |
| adaptive `.tran` dense, 1000 sections | 1.94 s | 1.84 s | -5 % |
| adaptive `.tran` sparse, 1000 sections | 322 ms | 341 ms | +6 % |
| `diode_rectifier_tran` | 223 ms | 226 ms | +2 % |
| `cmos_inverter_tran` | 534 ms | 546 ms | +2 % |
| `stiff_adaptive` | 11.9 ms | 12.2 ms | +3 % |
| `rlc_ring_adaptive` | 123 ms | 122 ms | -1 % |
| `nmos_common_source .ac` (200 repeats) | 1.88 ms | 2.00 ms | **+7 %** (registry overhead in the per-frequency rebuild; inside the 10 % budget) |

The stand-alone benchmark moved by up to 39 % between identical runs on this machine (and a dense `.op` by 3x while a browser test ran),
so the 10 % rule was judged on the A/B, not against the baseline table in STATUS.md (D41).

## Things you should know
- **Fixed-step trapezoidal ringing** on a capacitor current when the capacitor sits directly between ideal sources (the PMOS Cgs between
  an ideal gate drive and Vdd): 11 % of peak on i(vdd) against ngspice; the voltages are fine. The example therefore drives the gate
  through 1k (D42). The real fix is a backward-Euler step after each source corner (what ngspice does), but it changes existing results,
  which this run forbade: next step 1.
- **Adaptive stepping fails** (step below hmin just after the edge) in that same ideal-source case; with the 1k drive it runs (851 points).
- CBD / CBS are fixed values; ngspice applies a depletion law when they are given, so only the overlap terms are verified against it.
- The web bundle and its reference data include the two new examples; the live site picks them up on the next Pages deploy.
- `graphify-out/` is now in `.gitignore`.

## Skipped
Nothing from the brief. Out of scope and not done: Meyer capacitances, junction depletion and bulk diodes, a backward-Euler restart step.

## Suggested next steps
1. A backward-Euler (or Gear-2) step after each breakpoint in fixed-step trapezoidal, behind an option first, then compare the goldens.
2. Depletion-law junction capacitances (CJ, MJ, PB, FC) so CBD / CBS can be checked against ngspice.
3. Meyer gate capacitances with TOX, so inverter delay no longer depends on overlap capacitance only.
4. Cache the AC small-signal matrix across frequencies (only s changes) to win back the 7 %.
