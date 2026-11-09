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
| 4. ngspice reference overlay | not started | - | - |
| 5. Tests, build, deploy | not started | - | - |
| 6. Audit | not started | - | - |

Spike result (`web/scripts/pyodide-spike.mjs`; run: `cd web && npm install && node scripts/pyodide-spike.mjs <dir with spicelite wheel> ../examples/rc_lowpass.cir`):
pyodide boot 3.1 s, numpy+scipy load 3.6 s (first run, CDN downloads), total 10.7 s in Node; result -0.000434 dB at 10 Hz and -40.0004 dB at 100 kHz, identical to the CLI.
