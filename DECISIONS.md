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
