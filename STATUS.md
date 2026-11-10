# STATUS (overnight run, branch `overnight-m5-m7`)

Cut from `main` at ce2d9c8 (Milestone 6). Nothing pushed, nothing tagged, `main` untouched.

Test command for every committing run: `NGSPICE=<bundled ngspice_con.exe> python -m pytest -q -rs`
(0 failures AND 0 skips required).

| Phase | State | Last commit | Tests (ngspice on) |
|---|---|---|---|
| Preflight | done | - | main @ ce2d9c8: 309 passed, 0 skipped |
| 1. M5 controlled sources | done | (see git log) | 425 passed, 0 skipped (368 passed, 57 skipped without ngspice) |
| 2. M7 CLI / sparse / CI | done (CI workflow written, not run: no push allowed) | (see git log) | 497 passed, 0 skipped |
| 3. Audit | done | (see git log) | 520 passed, 0 skipped (463 passed, 57 skipped without ngspice) |

## Blocked / failed items
(none yet)


# M8-M9 run (branch `m8-mosfet-adaptive`, cut from `overnight-m5-m7` @ 8b6b62a because main lacks M7)

Started: Mon Nov 9 10:20:54 EST 2026. Brief was pasted twice; the second copy is the complete one.
Test command: `. NGSPICE=<bundled ngspice_con.exe> python -m pytest -q -rs` (0 failures and 0 skips required).
Baseline at start: 520 passed, 0 skipped.

| Phase | State | Last commit | Tests (ngspice on) |
|---|---|---|---|
| 1. M8 MOSFET | done | (see git log) | 602 passed, 0 skipped (537 passed, 65 skipped without ngspice) |
| 2. M9 adaptive stepping | done | (see git log) | 635 passed, 0 skipped (564 passed, 71 skipped without ngspice) |
| 3. Audit | done | (see git log) | 648 passed, 0 skipped (577 passed, 71 skipped without ngspice) |
| 4. Report | done (REPORT.md; previous run kept as REPORT_M5_M7.md) | (see git log) | - |


# Web UI run (branch `web-ui`, cut from main @ cb67a6c)

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
| 3. Design system | done | tokens, both themes, every component restyled, fonts self-hosted (D49); CSS 4.54 kB gzip (was 4.08) |
| 4. Motion | done | D50 table; no library; e2e 20 passed (4 new motion tests), npm test 106; also fixed the double run on Ctrl+Enter |
| 5. Landing and spec sheets | done | hero + live demo from rc_step data, capability table, 11 element sheets (D51); e2e 24, pytest 824 |
| 6. Audit | done | 35 examples clean; contrast AA both themes; keyboard and focus; sizes -22 kB net; e2e 24, npm test 106, pytest 824 (D52) |

Baseline size and load: JS 375.7 kB (129.4 kB gzip), CSS 13.9 kB (4.1 kB gzip), index.html 1.4 kB gzip; dist/ 1.71 MB in total
(includes 0.9 MB of reference JSON fetched only on demand, the 54 kB wheel and the font files). First results 10.3 s on a cold browser
cache (Pyodide + numpy + scipy from the CDN), measured by shots.mjs.


# Portfolio polish run (branch `portfolio-polish`, cut from main @ 2d01fd6)

Started: Mon Nov  9 19:26:54 EST 2026 (per `date`). Time box about 2 h; at 1 h 40 m (21:06) skip to the final report.
Preflight: `git status` clean on main apart from an untracked `.claude-flow/` tool-state folder (ignored in this branch);
`pytest -q` on main with ngspice 41 via `NGSPICE`: **824 passed, 0 skipped**.

Branch state at start (`git branch --merged main` / `--no-merged main`):
- merged into main: `m8-mosfet-adaptive`, `overnight-m5-m7`, `refactor-stamping`, `ui-polish`, `web-ui`
- NOT merged: `harden-inputs` (2 commits: input validation for `.tran` / sweeps / out-of-range values, and an ignore rule for `.claude-flow/`).
  This run was cut from main as instructed, so nothing written here describes `harden-inputs`.
- main is 16 commits ahead of `origin/main`; nothing from this run is pushed.

| Phase | State | Last commit | Notes |
|---|---|---|---|
| 1. Repo front door | done | (see git log) | README rewritten (front door, what it simulates, quick start, architecture diagram, Validation, Limitations; detailed sections kept and reordered); docs/convergence.md (generated by scripts/convergence_table.py); sparse benchmark re-run (docs/benchmark_sparse.md); hero image docs/hero.png (web/scripts/hero.mjs); CHANGELOG.md from the 6 tags and commits; CONTRIBUTING.md; issue templates; .gitignore. 824 passed, 0 skipped; ruff clean; web build ok |

Suggested GitHub topics (set by hand under Settings, or the gear next to About): `spice`, `circuit-simulator`, `modified-nodal-analysis`,
`ngspice`, `electronics`, `electrical-engineering`, `analog-circuits`, `eda`, `python`, `numpy`, `scipy`, `pyodide`, `webassembly`,
`newton-raphson`, `transient-analysis`, `mosfet`, `cmos`.
Suggested repository description: "SPICE-style circuit simulator in Python (MNA, Newton-Raphson, DC/AC/transient), checked against ngspice, runs in the browser".
| 2. Technical write-up | done | (see git log) | docs/writeup.md: about 1,900 words of prose; 4 [EDIT: ...] markers; scripts/newton_limiting_demo.py backs the Newton table; 824 passed, 0 skipped; ruff clean; web build ok |
| 3. Site polish | done | (see git log) | og/twitter metadata + social-preview.png; About section; 404.html; robots.txt; theme-button label fix; stale test count fixed; 25 docs plots regenerated with the ngspice overlay. Lighthouse desktop (before the last two fixes): a11y 100, best practices 100, SEO 92; not re-run. 824 pytest, 106 vitest, 24 e2e (full run before the label fix; 4 relevant re-run after), ruff clean, build ok |
| 4. Resume notes | done | (see git log) | resume-notes.md (personal; removed from the repository in the privacy cleanup below); 2 [EDIT] markers |
| Final report | done | (last commit) | REPORT_PORTFOLIO.md: numbers with sources, privacy findings, 6 [EDIT] markers, manual steps, what was not verified |


# Privacy cleanup run (history rewrite, local only)

Purpose: make the repository safe to make public. No features, nothing pushed. Done on the checked-out `portfolio-polish` branch; every branch and tag was rewritten.

| Step | Result |
|---|---|
| Safety net | full folder copy `../spice-lite-backup`, a bundle of every ref `../spice-lite-all-refs.bundle` (verified), and local branches `backup-before-rewrite/<branch>` for all 8 branches. 824 tests passed before the rewrite |
| Resume notes | removed from every commit (`git filter-repo --invert-paths --path docs/resume-notes.md`); the file lives in `../private-notes/resume-notes.md`; `docs/resume-notes.md` is in `.gitignore` |
| Identity | author and committer e-mail of all 44 commits (8 branches, 6 tags, remote-tracking ref) replaced by the GitHub noreply address `101818557+Hopexist@users.noreply.github.com` using a mailmap; author name and the `Co-Authored-By: Claude` trailers kept. The address was derived from the account id that `gh api user` reports for the logged-in account; confirm it under GitHub Settings > Emails before relying on it |
| Full-history scan | all revisions and all commit messages searched for e-mail addresses, home paths, machine names, tokens and keys, and for risky file names. Found only: the personal e-mail address in commit metadata (fixed above) and the name "Ethaa" (author name and `LICENSE` holder, kept on purpose). No home paths, machine names, tokens, keys or credential files ever existed in the history (the only home-path pattern match was the filename `desktop-dark`, a false positive). The 6 quoted commit hashes that changed were updated in `CHANGELOG.md` and the reports |
| Tool | `git filter-repo` 2.47.0 (`a40bce548d2c`), installed with `pip install --user git-filter-repo` (not system-wide). A first attempt with `--refs` was a no-op, because filter-repo leaves alone commits that an excluded ref (my backup branches) still reaches; the backup branches were removed, the rewrite was run on all refs, and the backups were restored from the untouched folder copy. filter-repo removes the `origin` remote; it was re-added with the same URL |

Verification after the rewrite: `git log --format=%ae --all` over the real branches and tags gives only the noreply address (the `backup-before-rewrite/*` branches deliberately still hold the old data); the tree of every branch and tag is identical to before except the removed file on `portfolio-polish`; commit counts and every commit message are unchanged; pytest 824 passed, Vitest 106 passed, `npm run build` ok, ruff clean.

Tags (same commits, new hashes; the trees are identical):

| tag | original (before any rewrite) | now |
|---|---|---|
| v0.1 | adc02e1 | e69761a |
| v0.2-dc | a2a0d4a | 77f0903 |
| v0.3-ac | 1d8a55f | 762103e |
| v0.4-tran | 9692950 | ef60a91 |
| v0.5-nonlinear | ceaf1f1 | b2dcb3a |
| v0.6-nonlinear-tran | e641ad2 | ce2d9c8 |

(Those backups were deleted after the repository was recreated; see the next section.)


# Second privacy pass and repository recreation

The force-push replaced the history on GitHub, but GitHub still served the old `main` commit by its hash (checked through the API), with the
personal e-mail address in it. The repository had also been public all along. Deleting and recreating the repository is the only way to make
GitHub drop those objects, so the history was cleaned once more before the new push:

| Item | Before | After |
|---|---|---|
| University named in `CLAUDE.md` (every commit since the first) | present | removed from every revision (`git filter-repo --replace-text`) |
| Name of the desktop application that bundles ngspice (reports and decisions) | present | replaced by "another (desktop) application" in every revision |
| Commit timezones | -0500 on all 92 author and committer dates | +0000; the instants are unchanged (epoch seconds compared before and after) |
| Author and committer e-mail | noreply address only | unchanged |

Checks against a bundle taken just before this pass: only `CLAUDE.md`, `DECISIONS.md`, `REPORT_M5_M7.md` and `REPORT_M8_M9.md` differ, on every
branch; commit messages and timestamps are identical; none of the replaced strings remains in any revision. Commit hashes quoted in the
documents were mapped to the new commits by matching timestamp and message.

Outcome: the GitHub repository was deleted and recreated (public, same name) and the cleaned history pushed: `main`, 7 other branches and
6 tags. Through the API, the old commits now answer "No commit found", and all 468 author and committer entries across the branches are the
noreply address. Pages was re-enabled (GitHub Actions source) and deployed; the live site answers HTTP 200. The local backups that held the
old data (folder copy and both bundles) were deleted and the old objects purged from the local `.git` (no unreachable objects remain).

First CI run on GitHub (never run before): the web job passed; the Python jobs ran 824 tests on 3.10, 3.11 and 3.12 with ngspice 42 and
**823 passed, 1 failed**: the full-precision golden test for `diode_rectifier_tran` (`tests/test_regression.py`, rtol 1e-12, atol 1e-18),
where 91 of 10,004 samples of a small current differ by at most 8.4e-15 A between Linux and the Windows machine that wrote the goldens
(Newton stops at a rounding-dependent point inside its tolerance). Every ngspice comparison passed, against ngspice 42. Not fixed: making it
pass means loosening a test, which the project rules leave to the owner.
