"""Build and solve the MNA system  A x = b, for DC (real) or one AC frequency (complex)."""
from __future__ import annotations

import numpy as np

from .circuit import (GROUND, Capacitor, Circuit, CurrentSource, Inductor, Resistor,
                      SingularCircuitError, VoltageSource, element_nodes)
from .elements import (stamp_capacitor, stamp_current_source, stamp_inductor, stamp_resistor,
                       stamp_voltage_source)


def build(circuit: Circuit, omega: float | None = None,
          t: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Return (A, b). omega=None builds the real DC system (C open, L a 0 V source) with
    sources at their DC value, or at their waveform value at time t if t is given (the
    initial condition of .tran); otherwise the complex system at s = j*omega (sources use
    their AC phasor). Size is n_nodes + n_branches."""
    ac = omega is not None
    s = 1j * omega if ac else 0.0
    idx = circuit.node_index()
    branches = circuit.branch_elements()
    row_of = {e.name: len(idx) + k for k, e in enumerate(branches)}
    size = len(idx) + len(branches)
    A = np.zeros((size, size), dtype=complex if ac else float)
    b = np.zeros(size, dtype=A.dtype)
    for e in circuit.elements:
        if isinstance(e, Resistor):
            stamp_resistor(A, idx, e)
        elif isinstance(e, Capacitor):
            stamp_capacitor(A, idx, e, s)
        elif isinstance(e, Inductor):
            stamp_inductor(A, idx, row_of[e.name], e, s)
        elif isinstance(e, VoltageSource):
            stamp_voltage_source(A, b, idx, row_of[e.name], e, e.ac if ac else e.at(t))
        elif isinstance(e, CurrentSource):
            stamp_current_source(b, idx, e, e.ac if ac else e.at(t))
    return A, b


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
    nodes = {GROUND} | {n for e in circuit.elements for n in element_nodes(e)}
    vparent = {n: n for n in nodes}
    for e in circuit.branch_elements():
        if isinstance(e, Inductor) and not dc:
            continue
        a, b = _find(vparent, element_nodes(e)[0]), _find(vparent, element_nodes(e)[1])
        if a == b:
            raise SingularCircuitError(
                f"{e.name} closes a loop of voltage sources "
                f"(between {element_nodes(e)[0]!r} and {element_nodes(e)[1]!r}"
                f"{'; inductors act as 0 V sources at DC' if dc else ''}); "
                "their voltages are over-constrained")
        vparent[a] = b
    parent = {n: n for n in nodes}
    for e in circuit.elements:
        if isinstance(e, Capacitor) and dc or isinstance(e, CurrentSource):
            continue
        n1, n2 = element_nodes(e)
        parent[_find(parent, n1)] = _find(parent, n2)
    root = _find(parent, GROUND)
    floating = sorted(n for n in parent if _find(parent, n) != root)
    if floating:
        raise SingularCircuitError(
            f"node(s) {', '.join(floating)} have no {'DC ' if dc else ''}path to ground (node 0); "
            "connect them with a resistor or voltage source")


def solve(circuit: Circuit, omega: float | None = None, t: float | None = None) -> np.ndarray:
    check_topology(circuit, dc=omega is None)
    A, b = build(circuit, omega, t)
    try:
        return np.linalg.solve(A, b)
    except np.linalg.LinAlgError as err:  # topology looked fine but the matrix is singular
        raise SingularCircuitError(f"circuit matrix is singular: {err}") from err
