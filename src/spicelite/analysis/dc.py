"""`.op` DC operating point."""
from __future__ import annotations

from dataclasses import dataclass

from ..circuit import Circuit
from ..mna import solve


@dataclass
class OpResult:
    voltages: dict[str, float]  # node name -> volts (ground "0" omitted)
    currents: dict[str, float]  # voltage-source name -> amps, SPICE sign: into n+, through source


def op(circuit: Circuit) -> OpResult:
    x = solve(circuit)
    idx = circuit.node_index()
    n = len(idx)
    return OpResult(
        voltages={node: float(x[i]) for node, i in idx.items()},
        currents={v.name: float(x[n + k]) for k, v in enumerate(circuit.voltage_sources())},
    )
