# Changelog

Built from the git tags and commit history (`git log --oneline`), with test counts taken from the run reports (`REPORT*.md`, `STATUS.md`).
Dates are commit dates. Only the first six milestones were tagged; everything after `v0.6-nonlinear-tran` is listed under Unreleased
although the package reports `__version__ = "0.7.0"`. The milestone numbers in commit messages (`M5`, `M7` ...) follow the roadmap in
`CLAUDE.md`, which numbers controlled sources as M5 and nonlinear devices as M6, so they differ from the tag names.

## Unreleased (after `v0.6-nonlinear-tran`)

### Added
- **Controlled sources and op-amp** (`eb9b339`): `E` (VCVS), `G` (VCCS), `F` (CCCS), `H` (CCVS) in DC, AC and transient; an op-amp is an `E` with gain 1e6
  (`spicelite.opamp()`), with an `OpenLoopWarning` when it has no feedback path. Examples: inverting amplifier, integrator, Sallen-Key low-pass.
  Tests grew from 309 to 425 in this step.
- **Command line, sparse solver, CI workflow** (`bdb76ca`): `spicelite run NETLIST [--csv DIR] [--plot DIR] [--solver auto|dense|sparse] [-q]`; sparse
  SuperLU solves for linear circuits from 60 unknowns up; GitHub Actions workflow (tests on Python 3.10 to 3.12 with ngspice, fails on any skipped test).
  520 tests passed after the audit pass `d6e40c1`.
- **Level-1 MOSFET** (`ae729a6`): Shichman-Hodges NMOS and PMOS with channel-length modulation and body effect, Newton-Raphson with SPICE-style
  voltage limiting, AC at the bias point. Examples: `nmos_iv`, `cmos_inverter_vtc`, `cmos_inverter_tran`, `nmos_common_source`.
- **Adaptive time stepping** (`e61537d`): `.options step=adaptive`, local-truncation-error control with breakpoints at source corners; `.ic` /
  `uic` examples. 648 tests passed after the audit pass `f850d15`.
- **Browser UI** (`28a3ad4` to `c1d1df4`): spicelite runs in Pyodide inside a Web Worker (Vite + TypeScript, CodeMirror editor, uPlot plots); a JSON entry point
  (`web_api.py`); precomputed ngspice reference overlay for every bundled example; GitHub Pages workflow; Vitest and Playwright tests.
  Python tests: 718 after the web API.
- **MIT licence** (`936a944`).
- **Portfolio polish** (branch `portfolio-polish`): README front door with validation and limitations sections, `docs/convergence.md`,
  `docs/benchmark_sparse.md`, `docs/writeup.md`, About section, social preview card, 404 page and `robots.txt` for the site, changelog,
  contributing guide and issue templates.
- **MOSFET capacitances** (`e3f1f58`): overlap (`CGSO`, `CGDO`, `CGBO`) and fixed junction (`CBD`, `CBS`) capacitances, in AC and transient.
  Examples `cmos_inverter_overlap`, `nmos_cs_bandwidth`.
- **Web UI design pass** (`2d730b5` to `eb1db37`): design system, motion, landing section with a live demo, element spec sheets generated from a
  data file that a test ties to the parser. 824 Python tests passed.

### Changed
- **One stamping path** (`c873495`): DC, AC, transient and Newton all build their matrices through one registry of per-element stamps
  (`elements.STAMPS`), replacing duplicated dispatch; results are unchanged (golden outputs compared at 1e-12 relative, `8969fa7`).

### Fixed
- `mna.build` silently dropped MOSFETs (found in the stamping audit, `474fdd8`; test first).
- `.tran ... uic` failed on two capacitors in parallel with a spurious "loop of voltage sources" error (`e3f1f58`; test first).
- Ctrl/Cmd+Enter in the web editor ran the netlist twice (`eb1db37`).

### Fixed (docs and site)
- The 25 plots in `docs/` that the README describes as spicelite vs ngspice had been generated without ngspice and showed no overlay; regenerated.
- The site's capability card said 809 tests; it is 824. The theme button's accessible name now contains its visible text.

### Known issues
- Fixed-step trapezoidal rings on a capacitor current between ideal voltage sources (documented in the README limitations).

## v0.6-nonlinear-tran (2026-11-09, `805e627`)
Nonlinear transient and AC, `.ic` / `uic`, and consistent initial conditions: capacitor currents and inductor voltages at t = 0+ are solved
from the held state, which restores second-order accuracy for ideal steps. 309 tests passed at this commit.

## v0.5-nonlinear (2026-11-08, `caa3664`)
Diodes with Newton-Raphson (junction voltage limiting, gmin-stepping fallback), the `.dc` sweep, and comparison against ngspice.

## v0.4-tran (2026-11-08, `a9f6890`)
Transient analysis with companion models for C and L: trapezoidal and backward Euler, `PULSE` and `SIN` sources, convergence-order tests.

## v0.3-ac (2026-11-08, `eee4200`)
AC small-signal analysis (complex MNA), capacitors and inductors, Bode plots, comparison against ngspice `.ac`.

## v0.2-dc (2026-11-08, `cde51af`)
DC operating point and the first comparison against ngspice.

## v0.1 (2026-11-08, `d97fa29`)
Netlist parser and data model: R, V and I elements, SI suffixes, line-numbered `NetlistError`.
