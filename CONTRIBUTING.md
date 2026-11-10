# Contributing

spice-lite is a learning project, but issues and small pull requests are welcome.

## Set up

```
pip install -e .[dev]
pytest -q            # the ngspice comparison tests need ngspice: put it on PATH or set NGSPICE to the executable
ruff check .
```

Without ngspice the comparison tests skip with a message; CI requires zero skips, so please run them before sending a change.
For the browser UI: `cd web && npm ci && npm test && npm run build` (see the README).

## Ground rules

- **Correctness first.** A change that alters a simulation result must say so and explain why; the golden outputs in `tests/golden_refactor/` fail on any unintended change.
- **Test first for bugs.** Add a test that fails, then fix it. Don't weaken or delete a test to make a change pass.
- **Say what is validated.** Claim agreement with ngspice only if the comparison test ran and passed, and write the tolerance in the test with the reason for it.
- **Keep it readable.** Comments explain the circuit theory, not the syntax. New element stamps live in `src/spicelite/elements.py` with the stamp pattern in the docstring.
- **No new dependencies** without opening an issue first.
- Unsupported netlist features must raise `NetlistError` with a line number, never be ignored.

Commit messages are short and in the imperative ("Add capacitor AC stamp").
