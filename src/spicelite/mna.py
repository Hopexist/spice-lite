"""Build and solve the MNA system  A x = b  for a DC circuit."""
from __future__ import annotations

import numpy as np

from .circuit import (GROUND, Circuit, CurrentSource, Resistor, SingularCircuitError,
                      VoltageSource)
from .elements import stamp_current_source, stamp_resistor, stamp_voltage_source


def build(circuit: Circuit) -> tuple[np.ndarray, np.ndarray]:
    """Return (A, b). Size is n_nodes + n_voltage_sources."""
    idx = circuit.node_index()
    vsrcs = circuit.voltage_sources()
    n = len(idx)
    A = np.zeros((n + len(vsrcs), n + len(vsrcs)))
    b = np.zeros(n + len(vsrcs))
    for e in circuit.elements:
        if isinstance(e, Resistor):
            stamp_resistor(A, idx, e)
        elif isinstance(e, VoltageSource):
            stamp_voltage_source(A, b, idx, n + vsrcs.index(e), e)
        elif isinstance(e, CurrentSource):
            stamp_current_source(b, idx, e)
    return A, b


def _find(parent: dict[str, str], x: str) -> str:
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def check_topology(circuit: Circuit) -> None:
    """Explain WHY a DC circuit is unsolvable, instead of a bare LinAlgError.

    Floating node: no path of resistors/voltage sources to ground. A current source
    does not count as a path (it forces current but sets no voltage), so such a
    node's voltage is undetermined.
    Voltage-source loop: sources forming a closed loop over-constrain the voltages
    (their constraint rows are linearly dependent).
    """
    nodes = {GROUND} | {n for e in circuit.elements
                        for n in ((e.n1, e.n2) if isinstance(e, Resistor) else (e.n_plus, e.n_minus))}
    # Loop check uses voltage-source edges ONLY (a source in parallel with a resistor is fine).
    vparent = {n: n for n in nodes}
    for e in circuit.voltage_sources():
        a, b = _find(vparent, e.n_plus), _find(vparent, e.n_minus)
        if a == b:
            raise SingularCircuitError(
                f"voltage source {e.name} closes a loop of voltage sources "
                f"(between {e.n_plus!r} and {e.n_minus!r}); their voltages are over-constrained")
        vparent[a] = b
    # Floating check: resistors and voltage sources both give a DC path.
    parent = {n: n for n in nodes}
    for e in circuit.elements:
        if isinstance(e, Resistor):
            parent[_find(parent, e.n1)] = _find(parent, e.n2)
        elif isinstance(e, VoltageSource):
            parent[_find(parent, e.n_plus)] = _find(parent, e.n_minus)
    root = _find(parent, GROUND)
    floating = sorted(n for n in parent if _find(parent, n) != root)
    if floating:
        raise SingularCircuitError(
            f"node(s) {', '.join(floating)} have no DC path to ground (node 0); "
            "connect them with a resistor or voltage source")


def solve(circuit: Circuit) -> np.ndarray:
    check_topology(circuit)
    A, b = build(circuit)
    try:
        return np.linalg.solve(A, b)
    except np.linalg.LinAlgError as err:  # topology looked fine but the matrix is singular
        raise SingularCircuitError(f"circuit matrix is singular: {err}") from err
