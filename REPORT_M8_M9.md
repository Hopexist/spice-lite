# Report: M8 MOSFET and M9 adaptive stepping (branch `m8-mosfet-adaptive`)

Started Mon Nov 9 10:20:54 EST 2026 (per `date`); the last test run finished 12:48. Nothing was pushed or tagged, and `main` is untouched.
`main` does not contain M7 (the merge was blocked earlier), so this branch was cut from `overnight-m5-m7` (d6ec1f2): merging it brings M5-M9 together.
The previous overnight report is kept as `REPORT_M5_M7.md`. Commits: `M8: level-1 MOSFET`, `M9: .ic/UIC and adaptive time stepping`,
`M8-M9 audit pass` (hashes in `git log --oneline`).

## Tests
| Run | Result |
|---|---|
| Baseline at start (`overnight-m5-m7`) | 520 passed, 0 skipped |
| End of Phase 1 (M8) | 602 passed, 0 skipped |
| End of Phase 2 (M9) | 635 passed, 0 skipped |
| **Final, ngspice enabled** | **648 passed, 0 skipped** (a CI-style check for the word "skipped" in the log finds none) |
| Final, ngspice absent | 577 passed, 71 skipped (all ngspice comparisons, each with a message) |
| `ruff check .` | clean |

`which ngspice` finds nothing here; ngspice 41 (bundled with another application) is reached through `NGSPICE` (DECISIONS D1 / D16). Every committing run required 0 skips.

## Phase 1: M8 level-1 MOSFET
- `M name d g s b model [W= L=]`, `.model name NMOS|PMOS (LEVEL=1 VTO KP LAMBDA GAMMA PHI)`; ngspice defaults (W = L = 100 um, KP 2e-5, PHI 0.6).
  Line-numbered errors: wrong field count, unknown model (or a diode/MOS model mix-up), unknown parameter, non-level-1, duplicate or non-positive W / L.
- Shichman-Hodges with cutoff / triode / saturation, channel-length modulation (also in triode, as in ngspice), body effect (GAMMA, PHI, with ngspice's
  continuation for Vbs > 0), PMOS by sign flip, drain/source swap when Vds reverses.
- Newton: gm / gds / gmbs companion model, `fetlim` + `limvds` voltage limiting as in ngspice's mos1load, residual check on the channel current, gmin
  stepping fallback; AC uses the three conductances at the bias point. MOSFET circuits stay on the dense solver (explicit `solver="sparse"` is an error).
- Intrinsic capacitances skipped (`shortcut:` in `elements.py`, README limitation); bulk junctions reduced to their GMIN conductance (D17).
- Examples: `nmos_iv`, `cmos_inverter_vtc`, `cmos_inverter_tran`, `nmos_common_source`. Docs: `iv_nmos.png` (family of four Vgs with ngspice dashed),
  `transfer_cmos_inverter.png` (VTC overlay), `wave_cmos_inverter_tran.png`, `bode_nmos_common_source.png`.
- Regression: `tests/golden_m1_m7.json` (all 26 earlier examples, frozen from commit d6ec1f2 via `git archive`) compared at 1e-9 relative: **unchanged**,
  including the diode circuits that now go through the generalised Newton loop.

### ngspice agreement (M8; tolerance is a fraction of the signal peak unless noted)
| Circuit | Analysis | Tolerance | Observed worst |
|---|---|---|---|
| `nmos_iv` (Vgs 1.5, 2, 2.5, 3 V) | `.dc` | 1e-9 | 8e-12 (junction leakage ngspice has, we do not) |
| `cmos_inverter_vtc` | `.dc` | 5e-8 | 6.5e-10 (3.3e-9 V at the switching point; gain ~50 amplifies ngspice's own tolerance) |
| `nmos_common_source` | `.op` / `.ac` | 1e-9 / 1e-6 relative | 1e-11 / ~1e-9 |
| body-effect follower, PMOS load, reverse conduction (inline) | `.dc` | 1e-8 | below tolerance (see `tests/test_mosfet.py`) |
| `cmos_inverter_tran` (0.0125 ns step) | `.tran` | 1.2e-3 | 2.6e-4 on v(out) (supply current 2.1e-4); error falls 4x per halving of h (O(h^2)) |

Analytic checks: region boundaries and derivatives by hand, PMOS = mirror of NMOS, common-source bias and gain, inverter switching threshold
against the closed form (lambda ~ 0) and against the exact equation with lambda (2e-3 V, limited by the sweep interpolation).

## Phase 2: M9 initial conditions and adaptive stepping
- `.ic` / `uic` already existed from M6 (D27), so this phase adds `rc_ic_discharge.cir` (analytic and ngspice checks) and a capacitor-only-loop test.
- `.options step=fixed|adaptive` (combinable with `method=`) or `tran(adaptive=True | StepControl(rtol, vabs, iabs, hmin, hmax, max_steps))`;
  `adaptive=False` overrides the option. Estimator: divided differences of the accepted points (trap h^3 |DD3| / 2, BE h^2 |DD2|); accept / reject with
  factor 0.9 r^(-1/(p+1)) in [0.5, 2], rounded down to hmax / 2^k so factored matrices are reused; steps land exactly on every PULSE / SIN corner and the
  history restarts there; the `hmin` and `max_steps` guards raise a `ConvergenceError` that says where. The fixed-step path is unchanged (golden regression plus a bit-identical result test).
- Examples: `rc_ic_discharge`, `rlc_ring_adaptive`, `stiff_adaptive`. Docs: `adaptive_steps.png`, `adaptive_steps_stiff.png`.

### Step counts and accuracy
| Circuit | Fixed | Adaptive | Max error |
|---|---|---|---|
| RC, 5 ms, tau 1 ms, trap | 5001 steps | **94** | 6.8e-5 vs analytic |
| RC, backward Euler | 5001 | 607 (67 rejected) | 1.2e-3 vs analytic |
| `stiff_adaptive` (tau 1 us / 10 ms, 50 ms, 1 ns edge) | 5000 steps: error 0.17; 5e5 steps: 4.7e-2 | **191** | 5e-4 analytic, 3.3e-4 of peak vs ngspice (tol 1.5e-3) |
| `rlc_ring_adaptive` (Q ~ 10) | ngspice ~20000 points | 2154 (38 rejected) | 4.7e-3 (v), 9.4e-3 (i) of peak vs ngspice (tol 4e-2) |
| `rc_ic_discharge` (fixed, UIC) | 501 steps | n/a | 1.0e-5 vs ngspice (tol 5e-5) |

Global error is the per-step error accumulated over the run, so an oscillator drifts: error falls roughly as rtol^(2/3) (3.9e-2, 9.2e-3, 2.2e-3 for rtol 1e-3, 1e-4, 1e-5).

## Phase 3: audit
Re-ran the full suite both ways, every example through the CLI (a test does this), the benchmark script (still works) and parsed the CI workflow (the new
code needed no change to it). README: status line, directive row, transient-method row and the "time step is fixed" limitation updated; every image exists.
Fixed: the CLI printed a numpy "divide by zero in log10" warning for AC-quiet nodes such as `vdd` (now -inf dB without a warning). Added edge-case tests: MOSFET
W / L missing (ngspice defaults) or zero, floating gate and bulk, gate through a resistor, `.ic` on a nonexistent node, `.ic` without uic, `.ic` on a
capacitor-less node, UIC without capacitors, tstep > tstop (fixed and adaptive), tstep = tstop adaptive.

## Things you should know
- **Merge order.** `main` lacks M7; merging this branch brings M5-M9 in one go (the earlier merge/tag/push was denied by the permission classifier and never run).
- **CI has still never run** (D12): apt's ngspice is not 41. The new MOSFET and adaptive comparisons were measured against 41 only.
- **A forward-biased bulk junction is not modelled** (D17): a MOSFET whose bulk sits more than ~0.6 V above a channel terminal conducts in ngspice, not here. One test
  sweep is deliberately kept at Vs >= 0 for this reason. No Cgs/Cgd/Cbd, so inverter delay comes only from the load capacitor.
- **Default `rtol` is 1e-4** (D26), tighter than SPICE's 1e-3, because oscillators accumulate error; loosen it if speed matters more than phase accuracy.
- Adaptive stepping is **opt-in** (D23). A zero-rise-time source leaves the trapezoidal history stale for one step (shortcut, D25).
- Two test-selection edits: example filters now use `.nonlinear()` instead of `.diodes()` (D21), and `stiff_adaptive` is excluded from the generic ngspice
  transient loop and has its own test (D28). No test was deleted, skipped or loosened; the new tolerances are all for new circuits.
- Line endings: git warns LF will become CRLF on this machine; there is still no `.gitattributes`.

## Skipped or blocked
Nothing blocked. Skipped by design: intrinsic MOS capacitances, bulk junction diodes, LEVEL 2/3 models, sparse Newton, a backward-Euler start-up step after a
source corner, and tolerances settable from the netlist (only via `StepControl`).

## Suggested next steps
1. Push the branch and watch the first CI run. 2. Add the Cgs/Cgd/Cbd capacitances (needed for believable inverter delay). 3. A netlist way to set `rtol`.
4. Sparse Newton for large MOS/diode circuits. 5. The two README sections still missing from the earlier report ("How MNA works", "What I learned").
