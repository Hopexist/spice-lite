# Overnight report (branch `overnight-m5-m7`, cut from `main` at e641ad2)

Nothing was pushed, tagged or forced; `main` is untouched. Commits: `M5: controlled sources and op-amp`,
`M7: CLI, sparse solver, CI`, `Audit pass: docs, consistency, edge cases` (hashes: `git log --oneline`).

## Tests
| Run | Result |
|---|---|
| Baseline (main @ e641ad2), ngspice via `$NGSPICE` | 309 passed, 0 skipped |
| End of Phase 1 | 425 passed, 0 skipped |
| End of Phase 2 | 497 passed, 0 skipped |
| **Final, ngspice enabled** | **520 passed, 0 skipped** |
| Final, ngspice absent | 463 passed, 57 skipped (all skips are the ngspice comparisons, with a message) |
| `ruff check .` | clean |

`which ngspice` finds nothing on this machine; ngspice 41 (bundled with another application) is reached through `NGSPICE`
(DECISIONS D1). Every committing run required 0 skips, which proves the comparisons ran.

## Phase 1: M5 controlled sources
- Parser, stamps, DC/AC/transient/Newton support for `E`, `G`, `F`, `H`; ngspice sign convention (documented in the
  README and checked in both orientations against ngspice). Line-numbered errors for a missing / non-V / self sense
  source, wrong field counts and nonnumeric gains.
- Op-amp = VCVS, gain 1e6 (`spicelite.opamp()`); `OpenLoopWarning` for an op-amp with no feedback path.
- Examples: `inv_amp`, `integrator`, `sallen_key_lp`, `vcvs_e`, `vccs_g`, `cccs_f`, `ccvs_h`. Docs: Sallen-Key Bode and
  integrator waveform overlays.
- `tests/test_regression.py` compares all 19 pre-M5 examples to golden values generated from the v0.6 tag's own
  source: M1-M6 results are unchanged (1e-9 relative).

## Phase 2: M7 CLI, sparse, CI
- `spicelite run NETLIST [--csv DIR] [--plot DIR] [--solver auto|dense|sparse] [-q]`, `--version`, `--help`; exit codes
  0 / 1 (netlist or simulation error, with line number) / 2 (usage or unreadable file); console script in pyproject.
- Sparse assembly (`sparse.py`) reuses the existing stamps; dense and sparse agree to 1e-9 on every linear example
  (`tests/test_sparse.py`). `auto` goes sparse from 60 unknowns. Diode circuits stay dense (shortcut, documented).
- CI: `.github/workflows/ci.yml` (Python 3.10/3.11/3.12, apt ngspice, ruff, pytest failing on any skip, CLI smoke
  test) and a README badge.

### Benchmark (RC ladder, best of 3, 1 for 10 000; Windows 11, Python 3.12, scipy 1.18)
| sections | unknowns | .op dense | .op sparse | speed-up | .tran dense | .tran sparse | speed-up |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 102 | 0.0480 s | 0.0013 s | 37.5x | 0.2205 s | 0.0237 s | 9.3x |
| 1000 | 1002 | 0.8634 s | 0.0113 s | 76.7x | 2.9051 s | 0.2560 s | 11.3x |
| 10000 | 10002 | 5.2920 s | 0.1183 s | 44.7x | 43.3431 s | 3.2395 s | 13.4x |

Below ~60 unknowns dense is as fast or faster (12 unknowns `.op`: 0.2 ms vs 0.5 ms). Small-size timings are noisy.

## ngspice agreement and tolerances (all measured, all in the tests with rationale comments)
| Analysis | Tolerance | Observed worst |
|---|---|---|
| `.op` linear (all examples incl. controlled) | 1e-9 relative | round-off (~1e-15) |
| `.dc` linear sweep | 1e-9 of peak | 0 |
| `.ac` | 1e-6 relative (ngspice run with tightened options) | linear 2e-13 (rlc_bandpass), Sallen-Key 3e-15, inv_amp 2e-16; diode_ac 6e-11 |
| `.tran` rc_step / vcvs_e / vccs_g / cccs_f / ccvs_h | 5e-5 of peak | 1.0e-5 (O(h^2) trapezoidal error) |
| `.tran` integrator | 2.5e-6 | 4.9e-7 |
| `.tran` rlc_ring / sin_rl | 1e-3 / 5e-4 | 2.4e-4 / 1.2e-4 |
| `.tran` diode rectifier / clamp, UIC RC / RLC | 5e-3 / 5e-4, 5e-5 / 1e-3 | 1.2e-3, 1.1e-4, 1.0e-5, 2.4e-4 |

## Phase 3: audit
Checked: full suite, every example through the CLI (a test does this), the README quick-start code (runs, outputs
match), every README image exists and is used, AC accuracy claims re-measured, supported-features table vs parser,
debug prints (none outside CLI/plot output), dead code (ruff), the `10u` regression test (still there).
Fixed: public classes/functions lacking docstrings (16 added); empty-circuit now gives a clear error instead of an empty
result; CLAUDE.md pointed at a command that never existed. Added `tests/test_edge_cases.py` (empty / title-only netlist,
duplicate names incl. case, floating nodes, missing ground, zero and negative passives, zero-valued sources, 1e-15..1e12
values, self-looped resistor, unsupported features with line numbers).

## Things you should know
- **CI has never run.** apt's ngspice is not 41 (the version the tolerances were measured against), so a comparison may
  fail on GitHub. First push will tell; fix the tolerance rationale, don't loosen blindly.
- `pip install ruff` was run; it is in the `dev` extra (D10). ruff config: line length 125, E741 ignored; `ruff --fix` re-sorted
  imports in 9 files (including three test files, order only).
- Version is now 0.7.0 from `spicelite.__version__` (pyproject said 0.1.0). No tag was created.
- A netlist with no directive runs `.op` in the CLI with a note (D8). `parse()` still accepts an element-less netlist
  because existing tests rely on it; the analyses reject it (D13).
- Line endings: git warns LF will become CRLF on this Windows machine; no `.gitattributes` exists.

## Skipped / not done
- Op-amp has no bandwidth, slew, saturation or port impedance. The open-loop warning does not see G/F feedback.
- Sparse does not cover diode circuits (Newton is dense). Source stepping, diode breakdown/capacitance, adaptive time step: not done.
- No "What I learned" README section and no "How MNA works" worked example check was done beyond the claims above; CLAUDE.md lists both
  as README requirements, so confirm they exist and are in your voice.

## Suggested next steps
1. Push the branch and watch the first CI run. 2. `spicelite run --compare` (spicelite vs ngspice) to replace the missing
`python -m spicelite.ngspice`. 3. Sparse Newton. 4. Op-amp with finite gain-bandwidth (one-pole VCVS). 5. Adaptive step.
