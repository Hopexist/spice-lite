"""`.tran` time stepping with companion models.

Replace d/dt by a finite difference over one fixed step h and each C and L becomes a
resistor-like term plus a source built from the PREVIOUS step. Every step is then the
same linear MNA solve, and since h is fixed the matrix is factored (LU) only once.

  Capacitor  i = C dv/dt          BE:   i_n = (C/h)(v_n - v_p)
                                  trap: i_n = (2C/h)(v_n - v_p) - i_p
             -> conductance G = sC with s = 1/h (BE) or 2/h (trap), plus a history current.
  Inductor   v = L di/dt          BE:   v_n - (L/h) i_n   = -(L/h) i_p
                                  trap: v_n - (2L/h) i_n  = -(2L/h) i_p - v_p
             -> the branch row of Milestone 3 with s*L, plus a history right-hand side.
  (p = previous time point, n = new one.)

BE: first-order accurate (error ~ h), damps everything, never rings.
Trapezoidal: second-order (error ~ h^2), no damping, so when h is much larger than the
circuit's time constants a sudden input change makes the answer ring numerically.
"""
from __future__ import annotations

import math
import warnings
from dataclasses import dataclass

import numpy as np
from scipy.linalg import lu_factor, lu_solve

from ..circuit import (Capacitor, Circuit, CurrentSource, Inductor, Pulse, Resistor,
                       SingularCircuitError, TranSpec, VoltageSource)
from ..elements import (stamp_capacitor, stamp_current_source, stamp_inductor, stamp_resistor,
                        stamp_voltage_source)
from ..mna import check_topology, solve


class ResolutionWarning(UserWarning):
    """The time step is coarser than a PULSE edge, so the edge may be under-resolved."""


@dataclass
class TranResult:
    time: np.ndarray  # seconds
    voltages: dict[str, np.ndarray]  # node name -> volts at each time point
    currents: dict[str, np.ndarray]  # V-source / inductor name -> amps (SPICE sign)


def _warn_if_edges_unresolved(circuit: Circuit, h: float) -> None:
    for e in circuit.elements:
        if isinstance(e, (VoltageSource, CurrentSource)) and isinstance(e.tran, Pulse):
            edge = min(e.tran.tr, e.tran.tf)
            if h > edge * (1 + 1e-9):  # tolerance: h = tstop/n can exceed an equal edge by round-off
                warnings.warn(f"{e.name}: time step {h:g} s is larger than the PULSE rise/fall "
                              f"time {edge:g} s; the edge may be under-resolved",
                              ResolutionWarning, stacklevel=3)


def tran(circuit: Circuit, spec: TranSpec | None = None, method: str | None = None) -> TranResult:
    """Fixed-step transient. `method` is "trap" (default) or "be"; None uses the circuit's
    `.options method=`. The step is the largest h <= tstep that divides tstop evenly.
    shortcut: the t=0 state is the DC solution with sources at their t=0 value (no `.ic`/UIC),
    so circuits with no DC path to ground (e.g. only capacitors) are rejected; add UIC if needed."""
    spec = spec or circuit.tran
    if spec is None:
        raise ValueError("no .tran directive in the circuit and no spec given")
    if circuit.diodes():
        raise NotImplementedError("diodes are not supported in .tran yet (nonlinear transient is the next milestone)")
    method = method or circuit.method
    if method not in ("trap", "be"):
        raise ValueError(f"method must be 'trap' or 'be', got {method!r}")
    trap = method == "trap"

    n_steps = math.ceil(spec.tstop / spec.tstep - 1e-9)
    h = spec.tstop / n_steps
    _warn_if_edges_unresolved(circuit, h)

    check_topology(circuit, dc=False)  # companion models make C conduct, L finite
    idx = circuit.node_index()
    branches = circuit.branch_elements()
    n = len(idx)
    row_of = {e.name: n + k for k, e in enumerate(branches)}
    size = n + len(branches)
    s = (2.0 if trap else 1.0) / h

    A = np.zeros((size, size))
    scratch = np.zeros(size)  # voltage-source stamps write b; b is rebuilt each step anyway
    caps = [e for e in circuit.elements if isinstance(e, Capacitor)]
    inds = [e for e in circuit.elements if isinstance(e, Inductor)]
    for e in circuit.elements:
        if isinstance(e, Resistor):
            stamp_resistor(A, idx, e)
        elif isinstance(e, Capacitor):
            stamp_capacitor(A, idx, e, s)
        elif isinstance(e, Inductor):
            stamp_inductor(A, idx, row_of[e.name], e, s)
        elif isinstance(e, VoltageSource):
            stamp_voltage_source(A, scratch, idx, row_of[e.name], e, 0.0)
    lu = lu_factor(A)
    if np.any(np.diag(lu[0]) == 0):
        raise SingularCircuitError("transient matrix is singular")

    def vdiff(x: np.ndarray, n1: str, n2: str) -> float:
        p, q = idx.get(n1), idx.get(n2)
        return (x[p] if p is not None else 0.0) - (x[q] if q is not None else 0.0)

    x = solve(circuit, t=0.0)  # initial condition: DC state, C open, L short
    cap_i = np.zeros(len(caps))  # capacitor currents; zero in a DC state
    xs = np.empty((n_steps + 1, size))
    xs[0] = x
    for k in range(1, n_steps + 1):
        t = k * h
        b = np.zeros(size)
        for e in circuit.elements:
            if isinstance(e, VoltageSource):
                b[row_of[e.name]] += e.at(t)
            elif isinstance(e, CurrentSource):
                stamp_current_source(b, idx, e, e.at(t))
        for j, c in enumerate(caps):  # history current injected into n1, drawn from n2
            hist = s * c.value * vdiff(x, c.n1, c.n2) + (cap_i[j] if trap else 0.0)
            p, q = idx.get(c.n1), idx.get(c.n2)
            if p is not None:
                b[p] += hist
            if q is not None:
                b[q] -= hist
        for l in inds:
            r = row_of[l.name]
            b[r] = -s * l.value * x[r] - (vdiff(x, l.n1, l.n2) if trap else 0.0)
        x_new = lu_solve(lu, b)
        for j, c in enumerate(caps):
            dv = vdiff(x_new, c.n1, c.n2) - vdiff(x, c.n1, c.n2)
            cap_i[j] = s * c.value * dv - (cap_i[j] if trap else 0.0)
        x = xs[k] = x_new

    return TranResult(
        np.arange(n_steps + 1) * h,
        {node: xs[:, i] for node, i in idx.items()},
        {e.name: xs[:, n + k] for k, e in enumerate(branches)},
    )
