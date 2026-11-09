# STATUS (overnight run, branch `overnight-m5-m7`)

Cut from `main` at e641ad2 (Milestone 6). Nothing pushed, nothing tagged, `main` untouched.

Test command for every committing run: `NGSPICE=<bundled ngspice_con.exe> python -m pytest -q -rs`
(0 failures AND 0 skips required).

| Phase | State | Last commit | Tests (ngspice on) |
|---|---|---|---|
| Preflight | done | - | main @ e641ad2: 309 passed, 0 skipped |
| 1. M5 controlled sources | done | (see git log) | 425 passed, 0 skipped (368 passed, 57 skipped without ngspice) |
| 2. M7 CLI / sparse / CI | done (CI workflow written, not run: no push allowed) | (see git log) | 497 passed, 0 skipped |
| 3. Audit | done | (see git log) | 520 passed, 0 skipped (463 passed, 57 skipped without ngspice) |

## Blocked / failed items
(none yet)


# M8-M9 run (branch `m8-mosfet-adaptive`, cut from `overnight-m5-m7` @ 35ecdb5 because main lacks M7)

Started: Mon Nov 9 10:20:54 EST 2026. Brief was pasted twice; the second copy is the complete one.
Test command: `. NGSPICE=<bundled ngspice_con.exe> python -m pytest -q -rs` (0 failures and 0 skips required).
Baseline at start: 520 passed, 0 skipped.

| Phase | State | Last commit | Tests (ngspice on) |
|---|---|---|---|
| 1. M8 MOSFET | done | (see git log) | 602 passed, 0 skipped (537 passed, 65 skipped without ngspice) |
| 2. M9 adaptive stepping | done | (see git log) | 635 passed, 0 skipped (564 passed, 71 skipped without ngspice) |
| 3. Audit | done | (see git log) | 648 passed, 0 skipped (577 passed, 71 skipped without ngspice) |
| 4. Report | done (REPORT.md; previous run kept as REPORT_M5_M7.md) | (see git log) | - |


# Web UI run (branch `web-ui`, cut from main @ 3eacd63)

Started: Mon Nov  9 13:09:54 EST 2026. Test command: `NGSPICE=<bundled ngspice_con.exe> python -m pytest -q -rs`.
Baseline at start: 648 passed, 0 skipped (`which ngspice` finds nothing; ngspice 41 reached through NGSPICE, same as DECISIONS D1).

| Phase | State | Last commit | Notes |
|---|---|---|---|
| 1. Feasibility spike | **GO** | (see git log) | Pyodide 314.0.7 = Python 3.14.2, numpy 2.4.6, scipy 1.18.0; spicelite (>=3.10) overlaps. rc_lowpass runs headlessly in Node; matplotlib not imported. |
| 2. JSON API | done | (see git log) | 718 passed, 0 skipped (70 new web_api tests: every example strict-JSON, errors with line numbers, guards, warnings, CLI golden output unchanged) |
| 3. UI | done | (see git log) | Vite 8 + TypeScript; typecheck and build clean; headless Edge run: no console errors, first results 11.7 s on a cold cache; verified dark/light, 1440 and 360 px, error state, .op, table view |
| 4. ngspice reference overlay | done | (see git log) | scripts/gen_reference.py: 33 examples, 893 kB of committed JSON; toggle + error panel verified in Edge; toggle disappears after an edit |
| 5. Tests, build, deploy | done | (see git log) | web: 64 unit tests + 37 real-Pyodide example tests (vitest); 16 Playwright e2e tests (Edge locally, Chromium in CI) incl. serving dist under /spice-lite/; pages.yml + ci.yml `web` job; README section + docs/web_ui_*.png |
| 6. Audit | done | (see git log) | scripts/audit.mjs: all 33 examples through the built site in Edge, no console errors or HTTP failures; e2e covers error on first/last line, empty editor, guard limit, rapid Run clicks, 360 and 1440 px |

Spike result (`web/scripts/pyodide-spike.mjs`; run: `cd web && npm install && node scripts/pyodide-spike.mjs <dir with spicelite wheel> ../examples/rc_lowpass.cir`):
pyodide boot 3.1 s, numpy+scipy load 3.6 s (first run, CDN downloads), total 10.7 s in Node; result -0.000434 dB at 10 Hz and -40.0004 dB at 100 kHz, identical to the CLI.

# Stamping refactor run (branch `refactor-stamping`)

Started Mon Nov 9 15:26:52 EST 2026 (per `date`); time box ~2 h (final report by 17:06 at the latest).
`which ngspice`: not on PATH; ngspice 41 reached through `NGSPICE` as in every earlier run (D1/D16). Baseline `pytest -q`: **718 passed, 0 skipped**.

| Phase | State | Notes |
|---|---|---|
| 0. Safety net | done | tests/golden_refactor/: CLI `--csv` output (repr floats) for all 33 examples (51 files) + sparse-solver output for the 21 linear ones (37 files); compared at rtol 1e-12, atol 1e-18 |
| 1. Audit | done | DECISIONS D39 table; bug: `mna.build` silently dropped MOSFETs (test first, fixed) |
| 2. Single stamping path | done | elements.STAMPS registry (D40); 791 passed; goldens match to 1e-12; A/B timings within ±6% (D41) |
| 3. MOSFET capacitances | done | CGSO/CGDO/CGBO/CBD/CBS via Stamp.expand (D42); 2 examples; AC vs ngspice 9e-13, tran 4.4e-4 of peak; bug: parallel C with uic (D43, test first) |
| 4. Audit and report | done | 809 passed, 0 skipped; 35 examples via CLI; npm test 103, build, e2e 16 passed; REPORT.md |

### Baseline timings (before the refactor; best of 7, this machine)
`python benchmarks/bench_sparse.py --sizes 10 100 1000 --repeat 7` (now also times adaptive `.tran`):

| sections | unknowns | .op dense | .op sparse | speed-up | .tran dense | .tran sparse | speed-up | adaptive dense | adaptive sparse | speed-up |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 12 | 0.0001 s | 0.0003 s | 0.4x | 0.0042 s | 0.0038 s | 1.1x | 0.0074 s | 0.0079 s | 0.9x |
| 100 | 102 | 0.0142 s | 0.0012 s | 11.7x | 0.0919 s | 0.0231 s | 4.0x | 0.0779 s | 0.0315 s | 2.5x |
| 1000 | 1002 | 0.1344 s | 0.0110 s | 12.3x | 0.7024 s | 0.2189 s | 3.2x | 1.5586 s | 0.2664 s | 5.9x |

`python benchmarks/bench_examples.py` (best of 5; AC best of 20):

| workload | time |
|---|---:|
| diode_rectifier_tran .tran | 0.1919 s |
| cmos_inverter_tran .tran | 0.4645 s |
| stiff_adaptive .tran | 0.0104 s |
| rlc_ring_adaptive .tran | 0.1081 s |
| nmos_common_source .ac | 0.0019 s |

# UI polish run (branch `ui-polish`)

Started Mon Nov 9 16:27:12 EST 2026 (per `date`); time box ~3 h (final report by 19:07 at the latest). Baseline: `pytest -q` 809 passed,
0 skipped (ngspice via `NGSPICE`); `npm test` 103 passed.

| Phase | State | Notes |
|---|---|---|
| 0. Baseline | done | docs/ui-before/: 7 states x 360/1440 x dark/light = 28 shots (web/scripts/shots.mjs, Edge, reduced motion); no console errors |
| 1. Tools and skills | done | DECISIONS D45 (tool table) and D46 (no animation library, measured costs); 3 MIT skills installed in .claude/skills |
| 2. Design direction | done | A Datasheet chosen 23 vs 18 vs 17 (D47); mark, favicons, palette and type (D48) |
| 3. Design system | not started | |
| 4. Motion | not started | |
| 5. Landing and spec sheets | not started | |
| 6. Audit | not started | |

Baseline size and load: JS 375.7 kB (129.4 kB gzip), CSS 13.9 kB (4.1 kB gzip), index.html 1.4 kB gzip; dist/ 1.71 MB in total
(includes 0.9 MB of reference JSON fetched only on demand, the 54 kB wheel and the font files). First results 10.3 s on a cold browser
cache (Pyodide + numpy + scipy from the CDN), measured by shots.mjs.
