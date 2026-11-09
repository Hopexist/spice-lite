"""Circuit data model: plain data, no matrices.

Node names are lowercase strings; "0" is ground. All values are SI units;
source phases are radians here (degrees only exist in the netlist text).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

GROUND = "0"


class NetlistError(Exception):
    """Unsupported or malformed netlist. `line` is the 1-based source line."""

    def __init__(self, message: str, line: int | None = None):
        self.line = line
        super().__init__(f"line {line}: {message}" if line is not None else message)


class SingularCircuitError(Exception):
    """The circuit has no unique solution (floating node, voltage-source loop)."""


@dataclass
class Resistor:
    name: str
    n1: str
    n2: str
    value: float  # ohms


@dataclass
class Capacitor:
    name: str
    n1: str
    n2: str
    value: float  # farads


@dataclass
class Inductor:
    name: str
    n1: str
    n2: str
    value: float  # henries; its branch current flows n1 -> n2


@dataclass
class VoltageSource:
    name: str
    n_plus: str
    n_minus: str
    dc: float  # volts, v(n_plus) - v(n_minus), used by .op
    ac: complex = 0j  # phasor (magnitude * e^{j phase}), used by .ac


@dataclass
class CurrentSource:
    """SPICE convention: current flows from n_plus, through the source, to n_minus."""

    name: str
    n_plus: str
    n_minus: str
    dc: float  # amps
    ac: complex = 0j


Element = Resistor | Capacitor | Inductor | VoltageSource | CurrentSource


@dataclass
class AcSweep:
    """`.ac dec|oct|lin points fstart fstop`. Raises ValueError on an invalid sweep."""

    kind: str
    points: int  # per decade/octave for dec/oct, total for lin
    fstart: float
    fstop: float

    def __post_init__(self) -> None:
        if self.kind not in ("dec", "oct", "lin"):
            raise ValueError(f"sweep type must be dec, oct or lin, got {self.kind!r}")
        if self.points < 1:
            raise ValueError(f"number of points must be at least 1, got {self.points}")
        if self.fstart <= 0 or self.fstop <= 0:
            raise ValueError(f"frequencies must be positive, got {self.fstart} and {self.fstop}")
        if self.fstop < self.fstart:
            raise ValueError(f"fstop ({self.fstop}) is below fstart ({self.fstart})")

    def frequencies(self) -> np.ndarray:
        if self.kind == "lin":
            return np.linspace(self.fstart, self.fstop, self.points)
        base = 10.0 if self.kind == "dec" else 2.0
        # Same point count as ngspice (floor(...+0.25) tolerates round-off in the log).
        n = int(np.floor(self.points * np.log(self.fstop / self.fstart) / np.log(base) + 0.25)) + 1
        return self.fstart * base ** (np.arange(n) / self.points)


@dataclass
class Circuit:
    title: str = ""
    elements: list[Element] = field(default_factory=list)
    op: bool = False  # a `.op` directive was present
    ac: AcSweep | None = None  # the `.ac` directive, if any

    def node_index(self) -> dict[str, int]:
        """Map each non-ground node to an MNA row/column 0..n-1 (first-appearance order).

        Ground has no entry: its voltage is fixed at 0 V, so it gets no unknown.
        """
        index: dict[str, int] = {}
        for e in self.elements:
            for node in element_nodes(e):
                if node != GROUND and node not in index:
                    index[node] = len(index)
        return index

    def voltage_sources(self) -> list[VoltageSource]:
        return [e for e in self.elements if isinstance(e, VoltageSource)]

    def branch_elements(self) -> list[VoltageSource | Inductor]:
        """Elements that carry an extra MNA unknown (their branch current), in netlist order.

        Branch k owns unknown (and row) n_nodes + k. Voltage sources and inductors both
        need one: neither current can be written as a conductance times a voltage
        (a voltage source fixes v; an inductor's admittance 1/(s*L) is infinite at DC).
        """
        return [e for e in self.elements if isinstance(e, (VoltageSource, Inductor))]


def element_nodes(e: Element) -> tuple[str, str]:
    if isinstance(e, (VoltageSource, CurrentSource)):
        return e.n_plus, e.n_minus
    return e.n1, e.n2
