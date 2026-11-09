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
| 2. M9 adaptive stepping | not started | - | - |
| 3. Audit | not started | - | - |
| 4. Report | not started | - | - |
