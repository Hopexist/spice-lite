"""`.op` DC operating point and `.dc` source sweep."""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from ..circuit import Circuit, DcSweep
from ..mna import solve
from ..sparse import check_solver
from .newton import solve_nonlinear


@dataclass
class OpResult:
    """Operating-point node voltages and branch currents."""
    voltages: dict[str, float]  # node name -> volts (ground "0" omitted)
    currents: dict[str, float]  # V-source / inductor name -> amps, SPICE sign: into n+, through the element
    iterations: int = 0  # Newton iterations (0 for a linear circuit: one direct solve)
    strategy: str = "linear"  # "linear", "newton", or "gmin" (the fallback was needed)


@dataclass
class DcSweepResult:
    """Node voltages and branch currents at each swept source value."""
    sweep: np.ndarray  # swept source values
    voltages: dict[str, np.ndarray]  # node name -> volts at each sweep point
    currents: dict[str, np.ndarray]  # V-source / inductor name -> amps at each sweep point
    iterations: np.ndarray  # Newton iterations per point (0 for a linear circuit)


def _solve_point(circuit: Circuit, x0: np.ndarray | None, solver: str = "auto"):
    """One DC solution -> (x, node index, iterations, strategy). Linear circuits take the
    direct path (one dense or sparse LU solve); circuits with diodes go through Newton-Raphson."""
    if circuit.nonlinear():
        r = solve_nonlinear(circuit, x0=x0)
        return r.x, r.idx, r.iterations, r.strategy
    return solve(circuit, solver=solver), circuit.node_index(), 0, "linear"


def _unpack(circuit: Circuit, x: np.ndarray, idx: dict[str, int]):
    """Pick the user-visible unknowns out of x (hidden diode-RS nodes are left out)."""
    n = len(idx)  # branch currents follow ALL node unknowns
    voltages = {node: float(x[idx[node]]) for node in circuit.node_index()}
    currents = {e.name: float(x[n + k]) for k, e in enumerate(circuit.branch_elements())}
    return voltages, currents


def op(circuit: Circuit, solver: str = "auto") -> OpResult:
    """DC solve: capacitors open, inductors shorted, diodes by Newton-Raphson.
    `solver` is "auto", "dense" or "sparse" (see sparse.py)."""
    check_solver(circuit, solver)
    x, idx, iters, strategy = _solve_point(circuit, None, solver)
    return OpResult(*_unpack(circuit, x, idx), iters, strategy)


def dc_sweep(circuit: Circuit, sweep: DcSweep | None = None, solver: str = "auto") -> DcSweepResult:
    """Sweep one source's DC value; each point starts Newton from the previous solution."""
    check_solver(circuit, solver)
    sweep = sweep or circuit.dc
    if sweep is None:
        raise ValueError("no .dc directive in the circuit and no sweep given")
    values = sweep.values()
    points, x = [], None
    for v in values:
        swept = replace(circuit, elements=[replace(e, dc=v) if e.name == sweep.source else e
                                           for e in circuit.elements])
        x, idx, iters, _ = _solve_point(swept, x, solver)
        points.append((*_unpack(circuit, x, idx), iters))
    return DcSweepResult(
        values,
        {n: np.array([p[0][n] for p in points]) for n in points[0][0]},
        {n: np.array([p[1][n] for p in points]) for n in points[0][1]},
        np.array([p[2] for p in points]),
    )
