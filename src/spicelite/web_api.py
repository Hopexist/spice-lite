"""JSON entry point for hosts that are not a terminal: the browser (spicelite runs inside Pyodide) or any server.

    run_netlist(text, options=None) -> dict      # never raises

On success:  {"ok": True, "title": str, "version": str, "warnings": [..], "analyses": [analysis, ...]}
On failure:  {"ok": False, "error": {"message": str, "line": int | None}}

Each analysis is
    {"type": "op" | "dc" | "ac" | "tran",
     "title": str,
     "x": {"name": str, "unit": str, "log": bool, "values": [...]} | None,   # None for .op (a table, not a curve)
     "signals": [{"name": "v(out)", "unit": "V", "values": [...], "part": "magnitude" | "phase" | None}, ...],
     "meta": {"runtime_ms", "points", "method", "solver", "warnings": [{"type", "message"}], ...}}
Values are plain lists of numbers; a non-finite value (for example -inf dB for an exactly zero AC signal)
becomes null, so the result is strictly valid JSON. AC signals come in magnitude (dB) / phase (degrees) pairs.

Guards (`Limits`) bound the size of what a request can ask for: netlist length, node count, points per analysis,
total work (points x elements) and wall-clock time. They are checked BEFORE running wherever the cost can be
predicted, so a runaway request fails fast with a message that says which limit and how to stay under it.
shortcut: a single analysis cannot be interrupted from inside Python (Pyodide has no threads or signals), so the
time limit is checked between analyses; the browser worker additionally terminates itself on a hard timeout.
"""
from __future__ import annotations

import math
import time
import warnings
from dataclasses import dataclass, fields, replace
from typing import Any

import numpy as np

from . import __version__
from .analysis.ac import ac, magnitude_db, phase_degrees
from .analysis.adaptive import StepControl
from .analysis.dc import dc_sweep, op
from .analysis.tran import tran
from .circuit import (
    Circuit,
    ConvergenceError,
    NetlistError,
    SingularCircuitError,
    VoltageSource,
)
from .parser import parse
from .sparse import SOLVERS


@dataclass(frozen=True)
class Limits:
    """Upper bounds on a request. Override any of them through `options`."""

    max_chars: int = 200_000  # netlist text
    max_nodes: int = 500  # circuit nodes
    max_nonlinear_nodes: int = 100  # nodes when the circuit has diodes or MOSFETs (dense Newton solves)
    max_points: int = 100_000  # sweep points, frequencies or time steps in one analysis
    max_work: int = 2_000_000  # points x elements, per analysis (x5 for nonlinear circuits: Newton iterations)
    max_seconds: float = 30.0  # wall-clock time for the whole run


class LimitError(Exception):
    """A request exceeds a guard; the message says which one and how to get under it."""


def run_netlist(text: str, options: dict | None = None) -> dict:
    """Parse and run every analysis in `text`. Never raises: see the module docstring for the result shape."""
    try:
        return _run(text, options or {})
    except NetlistError as err:
        return _error(_strip_line(str(err), err.line), err.line)
    except (LimitError, SingularCircuitError, ConvergenceError, ValueError) as err:
        return _error(str(err), None)
    except Exception as err:  # a bug, not a user error: still report it as data
        return _error(f"internal error: {type(err).__name__}: {err}", None)


def _error(message: str, line: int | None) -> dict:
    return {"ok": False, "error": {"message": message, "line": line}}


def _strip_line(message: str, line: int | None) -> str:
    prefix = f"line {line}: "
    return message[len(prefix):] if line is not None and message.startswith(prefix) else message


def _limits(options: dict) -> tuple[Limits, str]:
    known = {f.name for f in fields(Limits)} | {"solver"}
    unknown = sorted(set(options) - known)
    if unknown:
        raise ValueError(f"unknown option(s): {', '.join(unknown)}; supported: {', '.join(sorted(known))}")
    solver = options.get("solver", "auto")
    if solver not in SOLVERS:
        raise ValueError(f"solver must be one of {', '.join(SOLVERS)}, got {solver!r}")
    return replace(Limits(), **{k: v for k, v in options.items() if k != "solver"}), solver


def _run(text: str, options: dict) -> dict:
    limits, solver = _limits(options)
    if not isinstance(text, str):
        raise ValueError("the netlist must be text")
    if len(text) > limits.max_chars:
        raise LimitError(f"netlist is {len(text):,} characters; the limit is {limits.max_chars:,}")
    started = time.perf_counter()
    circuit = parse(text)
    _check_size(circuit, limits)
    notes: list[dict] = []
    if not (circuit.op or circuit.dc or circuit.ac or circuit.tran):
        notes.append({"type": "Note", "message": "no analysis directive in the netlist; ran .op"})
        circuit = replace(circuit, op=True)
    runners = [(circuit.op, "op", _op), (circuit.dc, "dc", _dc), (circuit.ac, "ac", _ac), (circuit.tran, "tran", _tran)]
    analyses = []
    for present, kind, fn in runners:
        if not present:
            continue
        if time.perf_counter() - started > limits.max_seconds:
            raise LimitError(f"the run exceeded its {limits.max_seconds:g} s time budget before the .{kind} analysis; "
                             "reduce the sweep or the circuit size")
        analyses.append(_timed(fn, circuit, limits, solver))
    return {"ok": True, "title": circuit.title, "version": __version__, "warnings": notes, "analyses": analyses}


def _check_size(circuit: Circuit, limits: Limits) -> None:
    nodes = len(circuit.node_index())
    nonlinear = bool(circuit.nonlinear())
    cap = limits.max_nonlinear_nodes if nonlinear else limits.max_nodes
    if nodes > cap:
        kind = "circuits with diodes or MOSFETs (dense Newton solves)" if nonlinear else "circuits"
        raise LimitError(f"the circuit has {nodes} nodes; the limit is {cap} for {kind}")


def _work_ok(kind: str, points: int, circuit: Circuit, limits: Limits) -> None:
    if points > limits.max_points:
        raise LimitError(f"the .{kind} analysis needs {points:,} points; the limit is {limits.max_points:,}")
    scale = 5 if circuit.nonlinear() else 1
    work = points * max(len(circuit.elements), 1) * scale
    if work > limits.max_work:
        raise LimitError(f"the .{kind} analysis is too large: {points:,} points x {len(circuit.elements)} elements"
                         f"{' x 5 (nonlinear)' if scale > 1 else ''} = {work:,} exceeds the limit of {limits.max_work:,}; "
                         "use fewer points or a smaller circuit")


def _clean(a: Any) -> list:
    """numpy array -> plain list with every non-finite value replaced by None (strict JSON)."""
    return [float(v) if math.isfinite(v) else None for v in np.asarray(a, dtype=float).ravel()]


def _timed(fn, circuit: Circuit, limits: Limits, solver: str) -> dict:
    t0 = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = fn(circuit, limits, solver)
    seen, collected = set(), []
    for w in caught:
        item = (w.category.__name__, str(w.message))
        if item not in seen:
            seen.add(item)
            collected.append({"type": item[0], "message": item[1]})
    result["meta"].update(runtime_ms=round((time.perf_counter() - t0) * 1000, 3), solver=solver, warnings=collected)
    return result


def _signals(voltages: dict, currents: dict, convert) -> list[dict]:
    out = []
    for name, v in voltages.items():
        out += convert(f"v({name})", "V", v)
    for name, i in currents.items():
        out += convert(f"i({name})", "A", i)
    return out


def _plain(name: str, unit: str, values) -> list[dict]:
    return [{"name": name, "unit": unit, "values": _clean(values), "part": None}]


def _complex(name: str, _unit: str, values) -> list[dict]:
    return [{"name": name, "unit": "dB", "values": _clean(magnitude_db(values)), "part": "magnitude"},
            {"name": name, "unit": "deg", "values": _clean(phase_degrees(values)), "part": "phase"}]


def _op(circuit: Circuit, limits: Limits, solver: str) -> dict:
    r = op(circuit, solver=solver)
    return {"type": "op", "title": ".op operating point", "x": None,
            "signals": _signals(r.voltages, r.currents, _plain),
            "meta": {"points": 1, "method": "direct" if r.strategy == "linear" else r.strategy,
                     "newton_iterations": r.iterations}}


def _dc(circuit: Circuit, limits: Limits, solver: str) -> dict:
    sweep = circuit.dc
    _work_ok("dc", sweep.count(), circuit, limits)
    src = next(e for e in circuit.elements if e.name == sweep.source)
    r = dc_sweep(circuit, solver=solver)
    unit = "V" if isinstance(src, VoltageSource) else "A"
    return {"type": "dc", "title": f".dc sweep of {sweep.source}",
            "x": {"name": sweep.source, "unit": unit, "log": False, "values": _clean(r.sweep)},
            "signals": _signals(r.voltages, r.currents, _plain),
            "meta": {"points": len(r.sweep), "method": "newton" if circuit.nonlinear() else "direct",
                     "newton_iterations_max": int(r.iterations.max()) if len(r.iterations) else 0}}


def _ac(circuit: Circuit, limits: Limits, solver: str) -> dict:
    _work_ok("ac", circuit.ac.count(), circuit, limits)
    r = ac(circuit, solver=solver)
    return {"type": "ac", "title": ".ac frequency sweep",
            "x": {"name": "frequency", "unit": "Hz", "log": True, "values": _clean(r.freqs)},
            "signals": _signals(r.voltages, r.currents, _complex),
            "meta": {"points": len(r.freqs), "method": "complex MNA"}}


def _tran(circuit: Circuit, limits: Limits, solver: str) -> dict:
    spec = circuit.tran
    adaptive = circuit.step_control == "adaptive"
    per_step = max(len(circuit.elements), 1) * (5 if circuit.nonlinear() else 1)
    if adaptive:
        ctl: StepControl | None = StepControl(max_steps=max(1, min(limits.max_points, limits.max_work // per_step)))
    else:
        ctl = None
        _work_ok("tran", math.ceil(spec.tstop / spec.tstep - 1e-9) + 1, circuit, limits)
    r = tran(circuit, solver=solver, adaptive=ctl if adaptive else False)
    meta = {"points": len(r.time), "steps": len(r.time) - 1, "method": circuit.method,
            "step_control": circuit.step_control, "rejected": r.rejected, "step_halvings": r.cuts}
    if r.iterations is not None and len(r.iterations):
        meta["newton_iterations_max"] = int(np.max(r.iterations))
    return {"type": "tran", "title": f".tran ({len(r.time) - 1} steps, {circuit.method}, {circuit.step_control})",
            "x": {"name": "time", "unit": "s", "log": False, "values": _clean(r.time)},
            "signals": _signals(r.voltages, r.currents, _plain), "meta": meta}
