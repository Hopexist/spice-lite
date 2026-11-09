# CLAUDE.md

## Project: spice-lite

A small SPICE-style circuit simulator written in Python. It parses a subset of the SPICE netlist format and solves DC operating point, AC small-signal, and transient analyses using Modified Nodal Analysis (MNA). Every result is validated against ngspice.

This is a learning and portfolio project by an EE student. The goals, in order:
1. Correctness: results match ngspice within stated tolerances.
2. Clarity: code and docs should teach MNA, not hide it.
3. Polish: tests, plots, and a README that stand up on GitHub.

## Working style

- Work in small milestones (see Roadmap). Finish, test, and commit one before starting the next.
- Before writing a new module, briefly explain the EE/math idea behind it (for example, why a voltage source adds an extra MNA row). I want to understand every line I push.
- Prefer simple, readable code over clever code. Comments should explain the circuit theory, not restate the code.
- Ask before adding any dependency beyond the ones listed below.
- Never claim a result is validated unless the ngspice comparison test actually ran and passed.

## Tech stack

- Python 3.10+
- numpy, scipy (linear solvers, sparse matrices later)
- matplotlib (plots)
- pytest (tests)
- ngspice (reference simulator, run in batch mode: `ngspice -b`). If ngspice is not installed, skip comparison tests with a clear message instead of failing.
- Optional later: ruff for linting, mypy for typing.

## Directory layout

```
spice-lite/
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── src/spicelite/
│   ├── __init__.py
│   ├── parser.py        # netlist text -> Circuit object
│   ├── circuit.py       # Circuit, Node map, Element dataclasses
│   ├── elements.py      # MNA stamps per element type
│   ├── mna.py           # builds and solves the MNA system
│   ├── analysis/
│   │   ├── dc.py        # .op and .dc sweep
│   │   ├── ac.py        # .ac frequency sweep (complex MNA)
│   │   └── tran.py      # .tran time stepping
│   ├── ngspice.py       # runs ngspice, parses its output for comparison
│   ├── plotting.py      # Bode, waveform, and comparison plots
│   └── cli.py           # `spicelite file.cir`
├── examples/            # .cir netlists (RC lowpass, divider, RLC, etc.)
├── tests/
│   ├── test_parser.py
│   ├── test_stamps.py
│   ├── test_dc.py
│   ├── test_ac.py
│   ├── test_tran.py
│   └── test_vs_ngspice.py
└── docs/                # derivations, plots, results
```

## Supported netlist subset (v1)

- Title line (first line), comments (`*` at line start, `;` inline), `.end`
- Elements: `R`, `C`, `L`, `V` (DC, AC, and PULSE/SIN sources), `I` (DC, AC)
- Controlled sources (milestone 5): `E` (VCVS), `G` (VCCS), `F` (CCCS), `H` (CCVS)
- Nonlinear (milestone 6): `D` (diode, Shockley model)
- Values with SI suffixes: `f p n u m k meg g t` (case-insensitive; note `m` = milli, `meg` = mega)
- Node `0` is ground
- Directives: `.op`, `.dc`, `.ac dec|lin|oct`, `.tran`
- Line continuation with `+`

Unsupported features must raise a clear `NetlistError` with the line number. Never silently ignore something in a netlist.

## Algorithms

- **MNA**: unknown vector is node voltages (excluding ground) plus branch currents for voltage sources and inductors. Each element contributes a "stamp" to matrix `A` and vector `b` in `A x = b`. Keep stamps in `elements.py`, one function per element, each with a docstring showing the stamp pattern.
- **DC**: capacitors are open, inductors are shorts (stamp as 0 V sources). Solve with `numpy.linalg.solve`. Detect singular matrices (floating nodes, voltage-source loops) and report a helpful error.
- **AC**: linearize at the operating point, build a complex MNA matrix with `jωC` and `jωL`, and sweep frequency. Output magnitude (dB) and phase.
- **Transient**: companion models for C and L. Start with backward Euler, then add trapezoidal. Fixed time step first, adaptive step later. Document the accuracy and stability tradeoff between the two methods.
- **Nonlinear**: Newton-Raphson iteration with linearized companion models for diodes. Add voltage limiting and a convergence check on both the voltage and current residuals.

## Validation against ngspice

- Each example netlist in `examples/` has a corresponding comparison test.
- `ngspice.py` writes a temporary netlist with a `.control` / `wrdata` block, runs `ngspice -b`, and parses the output into numpy arrays.
- Tolerances: DC to 1e-9 relative (linear circuits), AC to 1e-6 relative, transient to a documented per-circuit tolerance (it depends on time step and method). Record tolerances in the test, with a comment on why.
- Interpolate onto a common time or frequency grid before comparing transient and AC results.
- Generate overlay plots (spicelite vs. ngspice, plus the error curve) into `docs/` for the README.

## Testing rules

- Every element stamp gets a unit test with a hand-computed expected matrix.
- Use analytic references wherever possible, for example RC step response `v(t) = V(1 - e^{-t/RC})`, RC lowpass corner at `1/(2πRC)`, and RLC resonance. Compare against both the analytic answer and ngspice.
- Run `pytest -q` before every commit. Do not commit with failing tests.

## Code conventions

- Type hints on all public functions. Dataclasses for `Circuit` and elements.
- SI units internally, always. No unit conversion outside the parser.
- No global state. Analyses take a `Circuit` and return a result object (arrays plus node names).
- Errors: `NetlistError` (parse problems), `SingularCircuitError` (unsolvable topology), `ConvergenceError` (Newton failure).
- Keep functions short. If a function needs a long comment block to explain itself, split it.

## Roadmap

1. **Parser + data model**: parse R, V, I and SI suffixes. Tests for parsing edge cases.
2. **DC operating point**: resistor networks, voltage dividers, current sources. First ngspice comparison.
3. **AC analysis**: add C and L. RC/RL filters, Bode plots, compare against ngspice `.ac`.
4. **Transient**: backward Euler, then trapezoidal. Step and pulse responses, compare against ngspice `.tran`.
5. **Controlled sources**: E, G, F, H. Build an ideal op-amp model and an active filter example.
6. **Nonlinear DC and transient**: diode with Newton-Raphson. Rectifier example.
7. **Polish**: CLI, sparse matrices for larger circuits, README with results, CI via GitHub Actions.

## Commands

```
pip install -e .[dev]        # install in editable mode with dev deps
pytest -q                    # run tests
spicelite run examples/rc_lowpass.cir      # run a netlist from the CLI
pytest -q -k rc_lowpass tests/test_vs_ngspice.py   # run one ngspice comparison (needs ngspice, or set NGSPICE)
```

## README requirements (for GitHub)

- One-paragraph pitch and a feature list
- Install and quick-start in under five commands
- Overlay plots showing spicelite vs. ngspice for at least three circuits
- A short "How MNA works" section with one worked example
- A table of supported elements and analyses, plus known limitations
- "What I learned" section

## Git conventions

- Small commits, imperative messages (for example "Add capacitor AC stamp").
- One milestone per branch or tag (`v0.1-dc`, `v0.2-ac`, ...).
- Do not commit generated ngspice output files or `__pycache__`. Keep `.gitignore` current.