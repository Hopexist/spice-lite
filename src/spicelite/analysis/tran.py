"""`.tran` time stepping with companion models (and Newton-Raphson when there are diodes).

Replace d/dt by a finite difference over one fixed step h and each C and L becomes a
resistor-like term plus a source built from the PREVIOUS step. Every step is then a MNA solve
of the same matrix:

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

Linear circuits: the matrix is constant, so it is LU-factored once and each step is a
back-substitution. With diodes each step runs the Newton-Raphson loop of `newton.py` (the diode
stamps change every iteration) starting from the previous time point; if a step fails to
converge it is split in two, recursively, up to `max_cuts` times (the output stays on the
fixed grid).

Initial state. The trapezoidal rule needs each capacitor's current and each inductor's voltage
at t = 0+, not just the state variables (capacitor voltage, inductor current). They are found
by solving the circuit at t = 0+ with every capacitor held at its voltage (a voltage source)
and every inductor at its current (a current source). This makes trapezoidal second-order even
when a source steps at t = 0.
"""
from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, replace

import numpy as np
from scipy.linalg import lu_factor, lu_solve

from ..circuit import (
    Capacitor,
    Circuit,
    ConvergenceError,
    CurrentSource,
    Inductor,
    Pulse,
    SingularCircuitError,
    TranSpec,
    VoltageSource,
)
from ..elements import stamp_of
from ..mna import check_topology, solve, stamp_matrix
from ..sparse import Triplets, check_solver, factor, use_sparse
from .adaptive import StepControl, adaptive_loop, breakpoints
from .newton import ABSTOL, MAX_ITER, RELTOL, VNTOL, _expand, _newton, solve_nonlinear

MAX_CUTS = 8  # a failing step may be halved up to 8 times: down to 1/256 of the nominal step
_T0_PLUS = 1e-300  # "just after t = 0": a source that steps at t = 0 already shows its new value


class ResolutionWarning(UserWarning):
    """The time step is coarser than a PULSE edge, so the edge may be under-resolved."""


@dataclass
class TranResult:
    """Time grid with node voltages, branch currents, Newton iterations per step and step halvings."""
    time: np.ndarray  # seconds
    voltages: dict[str, np.ndarray]  # node name -> volts at each time point
    currents: dict[str, np.ndarray]  # V-source / inductor name -> amps (SPICE sign)
    iterations: np.ndarray | None = None  # Newton iterations per step (0 if linear); None if not run
    cuts: int = 0  # how many times a step had to be halved to converge
    rejected: int = 0  # adaptive stepping: steps thrown away because their error estimate was too big


def _warn_if_edges_unresolved(circuit: Circuit, h: float) -> None:
    for e in circuit.elements:
        if isinstance(e, (VoltageSource, CurrentSource)) and isinstance(e.tran, Pulse):
            edge = min(e.tran.tr, e.tran.tf)
            if h > edge * (1 + 1e-9):  # tolerance: h = tstop/n can exceed an equal edge by round-off
                warnings.warn(f"{e.name}: time step {h:g} s is larger than the PULSE rise/fall "
                              f"time {edge:g} s; the edge may be under-resolved",
                              ResolutionWarning, stacklevel=3)


def _frozen_state_system(ex: Circuit, vc: dict[str, float], il: dict[str, float], t: float,
                         solver: str = "auto"):
    """Solve `ex` at time t with every capacitor held at voltage vc[name] and every inductor
    at current il[name]. Returns (node voltages, branch currents by name); a held capacitor's
    branch current is its current n1 -> n2, and an inductor's voltage is v(n1) - v(n2).
    Raises SingularCircuitError if the held circuit has a source/capacitor loop."""
    # Capacitors in parallel share one voltage: hold the node pair with ONE source (two would be a loop of voltage
    # sources) and split its current by capacitance, since every one of them sees the same dv/dt.
    groups: dict[frozenset, list[Capacitor]] = {}
    for e in ex.elements:
        if isinstance(e, Capacitor):
            groups.setdefault(frozenset((e.n1, e.n2)), []).append(e)
    elements = []
    for e in ex.elements:
        if isinstance(e, Capacitor):
            if groups[frozenset((e.n1, e.n2))][0] is e:
                elements.append(VoltageSource(e.name, e.n1, e.n2, vc[e.name]))
        else:
            elements.append(CurrentSource(e.name, e.n1, e.n2, il[e.name]) if isinstance(e, Inductor) else e)
    held = replace(ex, elements=elements)
    if held.nonlinear():
        r = solve_nonlinear(held, t=t)
        x, idx = r.x, r.idx
    else:
        x, idx = solve(held, t=t, solver=solver), held.node_index()
    n = len(idx)
    currents = {e.name: float(x[n + k]) for k, e in enumerate(held.branch_elements())}
    for caps in groups.values():
        lead, total = caps[0], sum(c.value for c in caps)
        for c in caps[1:]:  # same orientation as the held one, or reversed (n1/n2 swapped)
            currents[c.name] = currents[lead.name] * c.value / total * (1 if c.n1 == lead.n1 else -1)
        currents[lead.name] *= lead.value / total
    return {node: float(x[i]) for node, i in idx.items()}, currents


def tran(circuit: Circuit, spec: TranSpec | None = None, method: str | None = None,
         max_iter: int = MAX_ITER, max_cuts: int = MAX_CUTS, solver: str = "auto",
         adaptive: bool | StepControl | None = None) -> TranResult:
    """Transient analysis, fixed-step unless `adaptive` (see adaptive.py). `method` is "trap" (default) or "be";
    None uses the circuit option `.options method=`. Fixed step: the largest h <= tstep that divides tstop
    evenly. `adaptive` is a StepControl, True (its defaults) or False; None uses `.options step=`.
    The t = 0 state is the DC solution (sources at their t = 0 value), or with `uic` the `.ic`
    capacitor voltages and zero inductor currents. `max_iter` caps each Newton run and
    `max_cuts` the step halvings (diodes only). `solver` is "auto", "dense" or "sparse":
    a linear circuit factors its matrix once, with dense LU or sparse LU (SuperLU).
    shortcut: a loop of only voltage sources and capacitors (or a cut-set of only inductors and
    current sources) has no t = 0+ capacitor current / inductor voltage; those histories then
    start at zero, as before, which is fine for smooth sources and first-order for a step."""
    spec = spec or circuit.tran
    if spec is None:
        raise ValueError("no .tran directive in the circuit and no spec given")
    method = method or circuit.method
    if method not in ("trap", "be"):
        raise ValueError(f"method must be 'trap' or 'be', got {method!r}")
    if circuit.ic and not spec.uic:
        raise ValueError(".ic is only used with uic: pass a TranSpec with uic=True (.tran ... uic)")
    trap = method == "trap"
    check_solver(circuit, solver)
    if adaptive is None:
        adaptive = circuit.step_control == "adaptive"
    ctl = adaptive if isinstance(adaptive, StepControl) else (StepControl() if adaptive else None)

    n_steps = math.ceil(spec.tstop / spec.tstep - 1e-9)
    h = spec.tstop / n_steps
    if ctl is None:  # adaptive stepping lands on every PULSE edge instead
        _warn_if_edges_unresolved(circuit, h)

    check_topology(circuit, dc=False)  # companion models make C conduct, L finite
    ex = _expand(circuit)  # diodes with RS get a hidden internal node (no-op for linear circuits)
    diodes = ex.nonlinear()  # diodes and MOSFETs: anything that needs Newton at every step
    idx = ex.node_index()
    branches = ex.branch_elements()
    n = len(idx)
    row_of = {e.name: n + k for k, e in enumerate(branches)}
    size = n + len(branches)
    names = list(idx) + [f"i({e.name})" for e in branches]
    caps = [e for e in ex.elements if isinstance(e, Capacitor)]
    inds = [e for e in ex.elements if isinstance(e, Inductor)]
    sources = [(st.rhs, e) for e in ex.elements if (st := stamp_of(e)).rhs is not None]  # looked up once, not per step

    def vdiff(x: np.ndarray, n1: str, n2: str) -> float:
        p, q = idx.get(n1), idx.get(n2)
        return (x[p] if p is not None else 0.0) - (x[q] if q is not None else 0.0)

    matrices: dict[float, tuple] = {}  # step size -> (A, LU or None): halved steps need their own

    def matrix(hh: float):
        if hh not in matrices:
            if len(matrices) >= 64:  # adaptive runs visit many step sizes: keep the cache bounded
                matrices.clear()
            s = (2.0 if trap else 1.0) / hh
            sparse = not diodes and use_sparse(size, solver)
            A = Triplets(size, float) if sparse else np.zeros((size, size))
            # the shared stamps with s = 1/h or 2/h: C and L become their companion conductances
            stamp_matrix(A, idx, row_of, ex.elements, s, nonlinear_ok=True)
            lu = None
            if sparse:
                A = A.tocsc()
                lu = factor(A)
            elif not diodes:
                lu = lu_factor(A)
                if np.any(np.diag(lu[0]) == 0):
                    raise SingularCircuitError("transient matrix is singular")
            matrices[hh] = (A, lu)
        return matrices[hh]

    def step(x, cap_i, ind_v, t_new, hh):
        """One step of size hh to time t_new -> (x_new, cap_i_new, ind_v_new, newton iterations)."""
        A, lu = matrix(hh)
        s = (2.0 if trap else 1.0) / hh
        b = np.zeros(size)
        for rhs, e in sources:
            rhs(b, idx, row_of, e, e.at(t_new))
        for j, c in enumerate(caps):  # history current injected into n1, drawn from n2
            hist = s * c.value * vdiff(x, c.n1, c.n2) + (cap_i[j] if trap else 0.0)
            p, q = idx.get(c.n1), idx.get(c.n2)
            if p is not None:
                b[p] += hist
            if q is not None:
                b[q] -= hist
        for j, l in enumerate(inds):
            r = row_of[l.name]
            b[r] = -s * l.value * x[r] - (ind_v[j] if trap else 0.0)
        if diodes:
            x_new, its = _newton(A, b, idx, n, diodes, names, x, 0.0, max_iter, RELTOL, ABSTOL, VNTOL)
        else:
            x_new, its = (lu.solve(b) if hasattr(lu, "solve") else lu_solve(lu, b)), 0
        cap_new = np.array([s * c.value * (vdiff(x_new, c.n1, c.n2) - vdiff(x, c.n1, c.n2))
                            - (cap_i[j] if trap else 0.0) for j, c in enumerate(caps)])
        ind_new = np.array([vdiff(x_new, l.n1, l.n2) for l in inds])
        return x_new, cap_new, ind_new, its

    cuts = 0

    def advance(state, t0, hh, depth):
        """Step from t0 to t0 + hh; if Newton fails, do it as two half steps (recursively)."""
        nonlocal cuts
        try:
            return step(*state, t0 + hh, hh)
        except ConvergenceError as err:
            if depth >= max_cuts:
                raise ConvergenceError(
                    f"transient Newton failed at t = {t0 + hh:.6g} s after halving the step "
                    f"{depth} times (to {hh:.3g} s); worst unknown is {err.worst_node}",
                    err.iterations, err.worst_node) from None
            cuts += 1
            *mid, its1 = advance(state, t0, hh / 2, depth + 1)
            *end, its2 = advance(tuple(mid), t0 + hh / 2, hh / 2, depth + 1)
            return (*end, its1 + its2)

    # ---- initial state: x (reported at t = 0) and the t = 0+ capacitor/inductor histories ----
    x = np.zeros(size)
    if spec.uic:
        touched = {nd for c in caps for nd in (c.n1, c.n2)}
        if stray := [nd for nd in circuit.ic if nd not in touched]:
            raise ValueError(f".ic on node(s) {', '.join(stray)} has no effect: only capacitor voltages "
                             "can be initialised, and no capacitor touches them")
        vc = {c.name: circuit.ic.get(c.n1, 0.0) - circuit.ic.get(c.n2, 0.0) for c in caps}
        il = {l.name: 0.0 for l in inds}
        nodes0, br0 = _frozen_state_system(ex, vc, il, 0.0, solver)
        for node, i in idx.items():
            x[i] = nodes0[node]
        for e in branches:
            x[row_of[e.name]] = il[e.name] if isinstance(e, Inductor) else br0[e.name]
    else:
        if diodes:
            r = solve_nonlinear(circuit, t=0.0)
            x = r.x
        else:
            x = solve(circuit, t=0.0, solver=solver)
        vc = {c.name: vdiff(x, c.n1, c.n2) for c in caps}
        il = {l.name: float(x[row_of[l.name]]) for l in inds}
    cap_i, ind_v = np.zeros(len(caps)), np.zeros(len(inds))
    if trap and (caps or inds):
        try:
            nodes1, br1 = _frozen_state_system(ex, vc, il, _T0_PLUS, solver)
            cap_i = np.array([br1[c.name] for c in caps])
            ind_v = np.array([nodes1.get(l.n1, 0.0) - nodes1.get(l.n2, 0.0) for l in inds])  # ground is absent = 0 V
        except SingularCircuitError:
            pass  # see the shortcut note in the docstring

    if ctl is not None:
        floor = np.array([ctl.vabs] * n + [ctl.iabs] * (size - n))
        times, xa, iters, rejected = adaptive_loop(advance, (x, cap_i, ind_v), spec, breakpoints(circuit, spec.tstop),
                                                   ctl, trap, floor)
        return TranResult(times, {node: xa[:, idx[node]] for node in circuit.node_index()},
                          {e.name: xa[:, n + k] for k, e in enumerate(branches)}, iters, cuts, rejected)

    xs = np.empty((n_steps + 1, size))
    iters = np.zeros(n_steps + 1, dtype=int)
    xs[0] = x
    state = (x, cap_i, ind_v)
    for k in range(1, n_steps + 1):
        *state, iters[k] = advance(tuple(state), (k - 1) * h, h, 0)
        xs[k] = state[0]

    return TranResult(
        np.arange(n_steps + 1) * h,
        {node: xs[:, idx[node]] for node in circuit.node_index()},
        {e.name: xs[:, n + k] for k, e in enumerate(branches)},
        iters, cuts,
    )
