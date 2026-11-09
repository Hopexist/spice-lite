"""Build and solve the MNA system  A x = b, for DC (real) or one AC frequency (complex)."""
from __future__ import annotations

import warnings

import numpy as np

from .circuit import (
    CCCS,
    CCVS,
    GROUND,
    VCCS,
    VCVS,
    Capacitor,
    Circuit,
    CurrentSource,
    Inductor,
    OpenLoopWarning,
    SingularCircuitError,
    element_nodes,
)
from .elements import STAMPS, stamp_of
from .sparse import Triplets, factor, use_sparse


def build(circuit: Circuit, omega: float | None = None, t: float | None = None,
          nonlinear_ok: bool = False, solver: str = "dense") -> tuple[np.ndarray, np.ndarray]:
    """Return (A, b). omega=None builds the real DC system (C open, L a 0 V source) with
    sources at their DC value, or at their waveform value at time t if t is given (the
    initial condition of .tran); otherwise the complex system at s = j*omega (sources use
    their AC phasor). Size is n_nodes + n_branches. Diodes and MOSFETs are skipped only when the Newton
    solver asks (nonlinear_ok): it stamps their companion models itself. `solver` ("dense",
    "sparse" or "auto") picks the storage of A: a numpy array, or a scipy CSC matrix (b is
    always a dense vector)."""
    ac = omega is not None
    idx = circuit.node_index()
    branches = circuit.branch_elements()
    rows = {e.name: len(idx) + k for k, e in enumerate(branches)}
    size = len(idx) + len(branches)
    dtype = complex if ac else float
    sparse = use_sparse(size, solver)
    A = Triplets(size, dtype) if sparse else np.zeros((size, size), dtype=dtype)
    b = np.zeros(size, dtype=dtype)
    stamp_matrix(A, idx, rows, circuit.elements, 1j * omega if ac else 0.0, nonlinear_ok)
    stamp_sources(b, idx, rows, circuit.elements, lambda e: e.ac if ac else e.at(t))
    return (A.tocsc() if sparse else A), b


def stamp_matrix(A, idx: dict[str, int], rows: dict[str, int], elements, s: complex,
                 nonlinear_ok: bool = False) -> None:
    """Add every element's s-dependent matrix part (elements.STAMPS) to A, in netlist order. A diode or
    MOSFET has none: the Newton solver (nonlinear_ok) or the small-signal path stamps it, and anywhere
    else it is an error rather than an element that silently stamps nothing."""
    for e in elements:
        st = STAMPS.get(type(e)) or stamp_of(e)  # direct lookup on the assembly path; stamp_of raises for a stranger
        if st.matrix is not None:
            st.matrix(A, idx, rows, e, s)
        elif st.newton and not nonlinear_ok:
            raise NotImplementedError(
                f"{e.name}: diodes and MOSFETs need the Newton solver or the small-signal path; "
                "use analysis.dc / analysis.ac / analysis.tran instead of mna.build directly")


def stamp_sources(b, idx: dict[str, int], rows: dict[str, int], elements, value_of) -> None:
    """Add every independent source's value to b; value_of(e) picks DC, the AC phasor or the waveform at t."""
    for e in elements:
        if (rhs := (STAMPS.get(type(e)) or stamp_of(e)).rhs) is not None:
            rhs(b, idx, rows, e, value_of(e))


def _find(parent: dict[str, str], x: str) -> str:
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def check_topology(circuit: Circuit, dc: bool = True) -> None:
    """Explain WHY a circuit is unsolvable, instead of a bare LinAlgError.

    Floating node: no path of conducting elements to ground. A current source is not a
    path (it forces current but sets no voltage). At DC a capacitor is open and does not
    conduct; at AC it does.
    Loop of voltage sources: over-constrains the voltages (dependent constraint rows).
    At DC an inductor is a 0 V source, so it counts; at AC it has impedance, so it doesn't.
    """
    if not circuit.elements:
        raise SingularCircuitError("the circuit has no elements: nothing to solve")
    nodes = {GROUND} | {n for e in circuit.elements for n in element_nodes(e)}
    vparent = {n: n for n in nodes}
    for e in circuit.branch_elements():
        # E and H are not independent: their voltage depends on other unknowns, so a loop through
        # one can be perfectly solvable. At AC/transient an inductor has impedance, so skip it too.
        if isinstance(e, (VCVS, CCVS)) or (isinstance(e, Inductor) and not dc):
            continue
        n1, n2 = element_nodes(e)[:2]
        a, b = _find(vparent, n1), _find(vparent, n2)
        if a == b:
            raise SingularCircuitError(
                f"{e.name} closes a loop of voltage sources "
                f"(between {n1!r} and {n2!r}"
                f"{'; inductors act as 0 V sources at DC' if dc else ''}); "
                "their voltages are over-constrained")
        vparent[a] = b
    parent = {n: n for n in nodes}
    for e in circuit.elements:
        if isinstance(e, Capacitor) and dc or isinstance(e, (CurrentSource, VCCS, CCCS)):
            continue  # open at DC / current outputs: they force current but set no voltage
        n1, n2 = element_nodes(e)[:2]  # an E or H fixes its output voltage, so it IS a path
        parent[_find(parent, n1)] = _find(parent, n2)
    root = _find(parent, GROUND)
    floating = sorted(n for n in parent if _find(parent, n) != root)
    if floating:
        raise SingularCircuitError(
            f"node(s) {', '.join(floating)} have no {'DC ' if dc else ''}path to ground (node 0); "
            "connect them with a resistor or voltage source")
    _warn_open_loop(circuit)


def _warn_open_loop(circuit: Circuit) -> None:
    """Warn about a high-gain E (an op-amp) with no feedback path.

    With gain ~1e6 and no path from its output back to its inputs, v(out) is just gain times the
    differential input: well-posed for the solver but almost never what the user means. A path
    counts if it avoids ground (ground connects everything) and the E itself, and may go through
    any two-terminal element, a capacitor included (an integrator's feedback is a capacitor).
    shortcut: feedback made only of controlled sources (G, F) is not seen and would warn."""
    for amp in circuit.elements:
        if not isinstance(amp, VCVS) or abs(amp.gain) < 1e3 or amp.n_plus == GROUND:
            continue
        targets = {amp.nc_plus, amp.nc_minus} - {GROUND}
        if not targets:
            continue
        adj: dict[str, set[str]] = {}
        for e in circuit.elements:
            if e is amp or isinstance(e, (VCCS, CCCS)):  # G and F are current outputs: not a feedback wire
                continue
            a, b = element_nodes(e)[:2]
            if GROUND not in (a, b):
                adj.setdefault(a, set()).add(b)
                adj.setdefault(b, set()).add(a)
        seen, stack = {amp.n_plus}, [amp.n_plus]
        while stack:
            for nxt in adj.get(stack.pop(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        if not seen & targets:
            warnings.warn(
                f"{amp.name}: no feedback path from its output node {amp.n_plus!r} to its inputs "
                f"({', '.join(sorted(targets))}); the circuit is open loop, so v({amp.n_plus}) is "
                f"{amp.gain:g} x the differential input",
                OpenLoopWarning, stacklevel=4)


def solve(circuit: Circuit, omega: float | None = None, t: float | None = None,
          solver: str = "auto") -> np.ndarray:
    """Solve the linear MNA system. solver="auto" goes sparse for large circuits (see
    sparse.SPARSE_MIN_SIZE); both paths use a direct LU, so they agree to round-off."""
    check_topology(circuit, dc=omega is None)
    A, b = build(circuit, omega, t, solver=solver)
    if not isinstance(A, np.ndarray):
        return factor(A).solve(b)
    try:
        return np.linalg.solve(A, b)
    except np.linalg.LinAlgError as err:  # topology looked fine but the matrix is singular
        raise SingularCircuitError(f"circuit matrix is singular: {err}") from err
