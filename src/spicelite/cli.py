"""Command line: `spicelite run netlist.cir`.

Runs every analysis the netlist asks for (.op, .dc, .ac, .tran), prints the results, and can
write one CSV and one PNG per analysis. A netlist with no analysis directive runs .op (with a note).

Exit codes: 0 success; 1 the netlist or the simulation failed (bad netlist with its line number,
singular circuit, Newton did not converge); 2 usage or file problems
(unknown option, missing file). Warnings (e.g. an open-loop op-amp) go to stderr and do not
change the exit code.
"""
from __future__ import annotations

import argparse
import csv
import sys
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np

from . import __version__
from .analysis.ac import ac, magnitude_db, phase_degrees
from .analysis.dc import dc_sweep, op
from .analysis.tran import tran
from .circuit import Circuit, ConvergenceError, NetlistError, SingularCircuitError
from .parser import parse
from .sparse import SOLVERS

ROWS_SHOWN = 12  # tables longer than this print their first and last rows; --csv has every row


class CliError(Exception):
    """A problem with how the tool was used or what it was asked to do (not a simulator bug).
    `code` is the process exit status: 2 for file problems, 1 otherwise."""

    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


def build_parser() -> argparse.ArgumentParser:
    """The argparse parser for `spicelite`."""
    p = argparse.ArgumentParser(prog="spicelite", description="A small SPICE-style circuit simulator.")
    p.add_argument("--version", action="version", version=f"spicelite {__version__}")
    sub = p.add_subparsers(dest="command", required=True, metavar="command")
    run = sub.add_parser("run", help="run the analyses in a netlist",
                         description="Run every analysis (.op, .dc, .ac, .tran) the netlist requests.")
    run.add_argument("netlist", help="path to a SPICE netlist (.cir)")
    run.add_argument("--csv", metavar="DIR", help="also write one CSV per analysis into DIR")
    run.add_argument("--plot", metavar="DIR", help="also write one PNG per analysis into DIR")
    run.add_argument("--solver", choices=SOLVERS, default="auto",
                     help="linear solver: dense, sparse, or auto (sparse for large circuits; default)")
    run.add_argument("-q", "--quiet", action="store_true", help="do not print result tables")
    return p


# ---- results as plain tables: (column names, rows of floats) --------------------------------

def _table_op(r) -> tuple[list[str], list]:
    names = [f"v({n})" for n in r.voltages] + [f"i({n})" for n in r.currents]
    return ["signal", "value"], [(n, v) for n, v in zip(names, [*r.voltages.values(), *r.currents.values()])]


def _table_sweep(x, x_name: str, voltages: dict, currents: dict):
    cols = {x_name: x, **{f"v({n})": v for n, v in voltages.items()},
            **{f"i({n})": v for n, v in currents.items()}}
    return list(cols), np.column_stack(list(cols.values()))


def _table_ac(r):
    cols = {"freq": r.freqs}
    for n, z in r.voltages.items():
        cols[f"mag_db(v({n}))"], cols[f"phase_deg(v({n}))"] = magnitude_db(z), phase_degrees(z)
    for n, z in r.currents.items():
        cols[f"mag_db(i({n}))"], cols[f"phase_deg(i({n}))"] = magnitude_db(z), phase_degrees(z)
    return list(cols), np.column_stack(list(cols.values()))


def _fmt(v) -> str:
    return v if isinstance(v, str) else f"{v:.6g}"


def _print_table(title: str, header: list[str], rows) -> None:
    rows = [[_fmt(v) for v in row] for row in rows]
    shown = rows if len(rows) <= ROWS_SHOWN else rows[:5] + [["..."] * len(header)] + rows[-5:]
    widths = [max(len(h), *(len(r[k]) for r in shown)) for k, h in enumerate(header)]
    print(f"\n== {title} ==")
    print("  ".join(h.rjust(w) for h, w in zip(header, widths)))
    for r in shown:
        print("  ".join(c.rjust(w) for c, w in zip(r, widths)))
    if len(rows) > ROWS_SHOWN:
        print(f"({len(rows)} rows; use --csv DIR to save all of them)")


def _write_csv(path: Path, header: list[str], rows) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows([[repr(float(v)) if not isinstance(v, str) else v for v in row] for row in rows])


# ---- driver ---------------------------------------------------------------------------------

def _plot(kind: str, header: list[str], data: np.ndarray, path: Path, title: str) -> None:
    from .plotting import signals_plot  # matplotlib is slow to import: only when --plot is used
    signals_plot(kind, header, data, path, title)


def run_netlist(circuit: Circuit, stem: str, solver: str, quiet: bool,
                csv_dir: Path | None, plot_dir: Path | None) -> int:
    """Run all requested analyses; return how many ran."""
    jobs = []  # (suffix, title, header, rows, plot kind)
    if not (circuit.op or circuit.dc or circuit.ac or circuit.tran):
        print("spicelite: note: no analysis directive in the netlist; running .op", file=sys.stderr)
        circuit = replace(circuit, op=True)
    if circuit.op:
        h, rows = _table_op(op(circuit, solver=solver))
        jobs.append(("op", ".op operating point", h, rows, None))
    if circuit.dc:
        r = dc_sweep(circuit, solver=solver)
        h, rows = _table_sweep(r.sweep, circuit.dc.source, r.voltages, r.currents)
        jobs.append(("dc", f".dc sweep of {circuit.dc.source}", h, rows, "dc"))
    if circuit.ac:
        h, rows = _table_ac(ac(circuit, solver=solver))
        jobs.append(("ac", ".ac frequency sweep", h, rows, "ac"))
    if circuit.tran:
        r = tran(circuit, solver=solver)
        h, rows = _table_sweep(r.time, "time", r.voltages, r.currents)
        jobs.append(("tran", f".tran ({len(r.time) - 1} steps)", h, rows, "tran"))
    for suffix, title, header, rows, kind in jobs:
        if not quiet:
            _print_table(title, header, rows)
        if csv_dir:
            _write_csv(csv_dir / f"{stem}_{suffix}.csv", header, rows)
        if plot_dir and kind:
            _plot(kind, header, np.asarray(rows), plot_dir / f"{stem}_{suffix}.png", f"{stem}: {title}")
    return len(jobs)


def _run(args: argparse.Namespace) -> None:
    path = Path(args.netlist)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as err:
        raise CliError(f"cannot read {args.netlist}: {err.strerror or err}", 2) from err
    except UnicodeDecodeError as err:
        raise CliError(f"{args.netlist} is not UTF-8 text", 2) from err
    circuit = parse(text)
    dirs = []
    for d in (args.csv, args.plot):
        if d:
            Path(d).mkdir(parents=True, exist_ok=True)
        dirs.append(Path(d) if d else None)
    run_netlist(circuit, path.stem, args.solver, args.quiet, *dirs)


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns the process exit status (see the module docstring)."""
    args = build_parser().parse_args(argv)  # exits with status 2 on a usage error
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("always")
            warnings.showwarning = lambda message, *_a, **_k: print(f"warning: {message}", file=sys.stderr)
            _run(args)
    except CliError as err:
        print(f"spicelite: error: {err}", file=sys.stderr)
        return err.code
    except (NetlistError, SingularCircuitError, ConvergenceError, ValueError) as err:
        print(f"spicelite: error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
