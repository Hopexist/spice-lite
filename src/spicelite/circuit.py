"""Circuit data model: plain data, no matrices.

Node names are lowercase strings; "0" is ground. All values are SI units.
"""
from __future__ import annotations

from dataclasses import dataclass, field

GROUND = "0"


class NetlistError(Exception):
    """Unsupported or malformed netlist. `line` is the 1-based source line."""

    def __init__(self, message: str, line: int | None = None):
        self.line = line
        super().__init__(f"line {line}: {message}" if line is not None else message)


@dataclass
class Resistor:
    name: str
    n1: str
    n2: str
    value: float  # ohms


@dataclass
class VoltageSource:
    name: str
    n_plus: str
    n_minus: str
    dc: float  # volts, v(n_plus) - v(n_minus)


@dataclass
class CurrentSource:
    """SPICE convention: current flows from n_plus, through the source, to n_minus."""

    name: str
    n_plus: str
    n_minus: str
    dc: float  # amps


Element = Resistor | VoltageSource | CurrentSource


@dataclass
class Circuit:
    title: str = ""
    elements: list[Element] = field(default_factory=list)

    def node_index(self) -> dict[str, int]:
        """Map each non-ground node to an MNA row/column 0..n-1 (first-appearance order).

        Ground has no entry: its voltage is fixed at 0 V, so it gets no unknown.
        """
        index: dict[str, int] = {}
        for e in self.elements:
            for node in _nodes(e):
                if node != GROUND and node not in index:
                    index[node] = len(index)
        return index

    def voltage_sources(self) -> list[VoltageSource]:
        """Voltage sources in MNA order: source k owns unknown (and row) n_nodes + k.

        Each one adds a branch-current unknown plus the constraint v+ - v- = V.
        """
        return [e for e in self.elements if isinstance(e, VoltageSource)]


def _nodes(e: Element) -> tuple[str, str]:
    if isinstance(e, Resistor):
        return e.n1, e.n2
    return e.n_plus, e.n_minus
