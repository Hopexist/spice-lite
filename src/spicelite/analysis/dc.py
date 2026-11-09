"""`.op` DC operating point."""
from __future__ import annotations

from dataclasses import dataclass

from ..circuit import Circuit
from ..mna import solve


@dataclass
class OpResult:
    voltages: dict[str, float]  # node name -> volts (ground "0" omitted)
    currents: dict[str, float]  # V-source / inductor name -> amps, SPICE sign: into n+, through the element


def op(circuit: Circuit) -> OpResult:
    """DC solve: capacitors open, inductors shorted (0 V sources with a branch current)."""
    x = solve(circuit)
    idx = circuit.node_index()
    n = len(idx)
    return OpResult(
        voltages={node: float(x[i]) for node, i in idx.items()},
        currents={e.name: float(x[n + k]) for k, e in enumerate(circuit.branch_elements())},
    )
