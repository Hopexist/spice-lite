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
