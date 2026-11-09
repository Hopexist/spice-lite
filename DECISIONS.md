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
