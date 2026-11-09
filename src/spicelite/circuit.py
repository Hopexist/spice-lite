"""Circuit data model: plain data, no matrices.

Node names are lowercase strings; "0" is ground. All values are SI units;
source phases are radians here (degrees only exist in the netlist text).
"""
from __future__ import annotations

import math
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


class OpenLoopWarning(UserWarning):
    """A high-gain controlled source (an op-amp) has no feedback path, so its output is just
    gain times the differential input."""


@dataclass
class Resistor:
    """Resistor between n1 and n2; value in ohms."""
    name: str
    n1: str
    n2: str
    value: float  # ohms


@dataclass
class Capacitor:
    """Capacitor between n1 and n2; value in farads (open at DC)."""
    name: str
    n1: str
    n2: str
    value: float  # farads


@dataclass
class Inductor:
    """Inductor between n1 and n2; value in henries (a 0 V source at DC, adds a branch current)."""
    name: str
    n1: str
    n2: str
    value: float  # henries; its branch current flows n1 -> n2


@dataclass
class Pulse:
    """PULSE(v1 v2 td tr tf pw per): v1 until td, ramp to v2 over tr, hold pw, ramp back over tf,
    repeat every per. At t <= td the value is v1, so a zero-rise step happens just after t=0."""

    v1: float
    v2: float
    td: float
    tr: float
    tf: float
    pw: float
    per: float

    def __post_init__(self) -> None:
        if min(self.td, self.tr, self.tf, self.pw) < 0:
            raise ValueError("PULSE td, tr, tf and pw must be >= 0")
        if self.per <= 0 or self.per < self.tr + self.pw + self.tf:
            raise ValueError("PULSE period must be positive and at least tr + pw + tf")

    def value(self, t: float) -> float:
        t -= self.td
        if t <= 0:
            return self.v1
        t %= self.per
        if t < self.tr:
            return self.v1 + (self.v2 - self.v1) * t / self.tr
        if t < self.tr + self.pw:
            return self.v2
        if t < self.tr + self.pw + self.tf:
            return self.v2 + (self.v1 - self.v2) * (t - self.tr - self.pw) / self.tf
        return self.v1


@dataclass
class Sin:
    """SIN(vo va freq [td theta]): vo until td, then vo + va e^{-theta (t-td)} sin(2 pi f (t-td))."""

    vo: float
    va: float
    freq: float
    td: float = 0.0
    theta: float = 0.0

    def __post_init__(self) -> None:
        if self.freq <= 0:
            raise ValueError(f"SIN frequency must be positive, got {self.freq}")
        if self.td < 0:
            raise ValueError("SIN delay must be >= 0")

    def value(self, t: float) -> float:
        if t <= self.td:
            return self.vo
        dt = t - self.td
        return self.vo + self.va * math.exp(-dt * self.theta) * math.sin(2 * math.pi * self.freq * dt)


@dataclass
class VoltageSource:
    """Independent voltage source n1(+) to n2(-): DC value, AC phasor and optional transient waveform."""
    name: str
    n_plus: str
    n_minus: str
    dc: float  # volts, v(n_plus) - v(n_minus), used by .op
    ac: complex = 0j  # phasor (magnitude * e^{j phase}), used by .ac
    tran: Pulse | Sin | None = None  # time-domain waveform, used by .tran

    def at(self, t: float | None) -> float:
        """Source value at time t; t=None (or no waveform) means the DC value."""
        return self.dc if t is None or self.tran is None else self.tran.value(t)


@dataclass
class CurrentSource:
    """SPICE convention: current flows from n_plus, through the source, to n_minus."""

    name: str
    n_plus: str
    n_minus: str
    dc: float  # amps
    ac: complex = 0j
    tran: Pulse | Sin | None = None

    at = VoltageSource.at


@dataclass
class DiodeModel:
    """`.model name D(IS=.. N=.. RS=..)`. Defaults match SPICE: IS = 1e-14 A, N = 1, RS = 0 ohm."""

    name: str
    IS: float = 1e-14  # saturation current (A)
    N: float = 1.0  # emission coefficient
    RS: float = 0.0  # series (ohmic) resistance (ohm)

    def __post_init__(self) -> None:
        if self.IS <= 0 or self.N <= 0 or self.RS < 0:
            raise ValueError("diode model needs IS > 0, N > 0 and RS >= 0")


@dataclass
class Diode:
    """Shockley diode, current flows anode -> cathode. `model` is filled in by the parser."""

    name: str
    anode: str
    cathode: str
    model_name: str
    model: DiodeModel | None = field(default=None, compare=False, repr=False)


@dataclass
class VCVS:
    """`E name n+ n- nc+ nc- gain`: v(n+) - v(n-) = gain (v(nc+) - v(nc-)). Has a branch current."""

    name: str
    n_plus: str
    n_minus: str
    nc_plus: str
    nc_minus: str
    gain: float


@dataclass
class VCCS:
    """`G name n+ n- nc+ nc- gm`: a current gm (v(nc+) - v(nc-)) flows n+ -> through the source -> n-."""

    name: str
    n_plus: str
    n_minus: str
    nc_plus: str
    nc_minus: str
    gm: float


@dataclass
class CCCS:
    """`F name n+ n- Vsense gain`: a current gain * i(Vsense) flows n+ -> through the source -> n-.
    i(Vsense) is the sense source's branch current: flowing into its + terminal, through it."""

    name: str
    n_plus: str
    n_minus: str
    sense: str
    gain: float


@dataclass
class CCVS:
    """`H name n+ n- Vsense rm`: v(n+) - v(n-) = rm * i(Vsense). Has a branch current."""

    name: str
    n_plus: str
    n_minus: str
    sense: str
    rm: float


Element = (Resistor | Capacitor | Inductor | VoltageSource | CurrentSource | Diode
           | VCVS | VCCS | CCCS | CCVS)

OPAMP_GAIN = 1e6  # default open-loop gain of the op-amp model


def opamp(name: str, out: str, in_plus: str, in_minus: str, gain: float = OPAMP_GAIN) -> VCVS:
    """An op-amp is a high-gain VCVS: v(out) = gain (v(in+) - v(in-)). It reuses the VCVS stamp
    instead of a new element, and the finite gain makes the finite-gain error of a closed loop
    visible. In a netlist write it as `E1 out 0 in+ in- 1e6`."""
    return VCVS(name.lower(), out, "0", in_plus, in_minus, gain)


@dataclass
class TranSpec:
    """`.tran tstep tstop [uic]`. Raises ValueError on an invalid spec. With `uic` the run starts
    from the `.ic` capacitor voltages (and zero inductor currents) instead of a DC solution."""

    tstep: float
    tstop: float
    uic: bool = False

    def __post_init__(self) -> None:
        if self.tstep <= 0 or self.tstop <= 0:
            raise ValueError(f"tstep and tstop must be positive, got {self.tstep} and {self.tstop}")
        if self.tstop < self.tstep:
            raise ValueError(f"tstop ({self.tstop}) is below tstep ({self.tstep})")


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
class DcSweep:
    """`.dc source start stop step`: sweep a V or I source's DC value. Raises ValueError if invalid."""

    source: str
    start: float
    stop: float
    step: float

    def __post_init__(self) -> None:
        if self.step == 0:
            raise ValueError("step must be nonzero")
        if (self.stop - self.start) * self.step < 0:
            raise ValueError(f"step {self.step:g} has the wrong sign to go from {self.start:g} to {self.stop:g}")

    def values(self) -> np.ndarray:
        n = int(np.floor((self.stop - self.start) / self.step + 1e-9)) + 1  # 1e-9: round-off guard
        return self.start + self.step * np.arange(n)


class ConvergenceError(Exception):
    """Newton-Raphson did not converge. `worst_node` is the unknown that was still moving most."""

    def __init__(self, message: str, iterations: int, worst_node: str):
        self.iterations = iterations
        self.worst_node = worst_node
        super().__init__(message)


@dataclass
class Circuit:
    """A parsed netlist: elements plus the analysis directives that were present."""
    title: str = ""
    elements: list[Element] = field(default_factory=list)
    op: bool = False  # a `.op` directive was present
    ac: AcSweep | None = None  # the `.ac` directive, if any
    tran: TranSpec | None = None  # the `.tran` directive, if any
    method: str = "trap"  # `.options method=trap|be`: integration method for .tran
    dc: DcSweep | None = None  # the `.dc` directive, if any
    models: dict[str, DiodeModel] = field(default_factory=dict)  # `.model` cards by name
    ic: dict[str, float] = field(default_factory=dict)  # `.ic v(node)=volts` initial conditions (UIC only)

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

    def diodes(self) -> list[Diode]:
        return [e for e in self.elements if isinstance(e, Diode)]

    def branch_elements(self) -> list[VoltageSource | Inductor]:
        """Elements that carry an extra MNA unknown (their branch current), in netlist order.

        Branch k owns unknown (and row) n_nodes + k. Voltage sources, inductors, and the two
        voltage-output controlled sources (E, H) need one: none of their currents can be written
        as a conductance times a voltage (a voltage source fixes v; an inductor's admittance
        1/(s*L) is infinite at DC). G and F are current outputs and need none.
        """
        return [e for e in self.elements if isinstance(e, (VoltageSource, Inductor, VCVS, CCVS))]


def element_nodes(e: Element) -> tuple[str, ...]:
    """Every node the element touches. The first two are its main terminals (the pair it
    conducts or drives); an E or G also lists its two control nodes after them."""
    if isinstance(e, (VCVS, VCCS)):
        return e.n_plus, e.n_minus, e.nc_plus, e.nc_minus
    if isinstance(e, (VoltageSource, CurrentSource, CCCS, CCVS)):
        return e.n_plus, e.n_minus
    if isinstance(e, Diode):
        return e.anode, e.cathode
    return e.n1, e.n2
