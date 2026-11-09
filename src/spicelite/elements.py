"""MNA stamps: how each element adds itself to  A x = b.

x = [node voltages (Circuit.node_index order) | branch currents (Circuit.branch_elements order)].
`idx` is Circuit.node_index(); ground ("0") is absent, so idx.get(node) is None
and its row/column is simply skipped (ground is the 0 V reference).

`s` is the complex frequency j*omega (AC) or 0 (DC). The same stamps serve both:
at DC a capacitor (admittance s*C = 0) vanishes and an inductor's row becomes v+ = v-.
"""
from __future__ import annotations

import math

import numpy as np

from .circuit import CCCS, CCVS, VCCS, VCVS, Capacitor, CurrentSource, Diode, DiodeModel, Inductor, Resistor, VoltageSource

# ngspice-41's constants (CODATA 2014) and default 27 C, so Vt = kT/q = 0.0258649170 V matches
# ngspice digit for digit; GMIN is the conductance SPICE puts across every diode junction.
VT = 1.38064852e-23 * 300.15 / 1.6021766208e-19
GMIN = 1e-12


def _stamp_admittance(A: np.ndarray, idx: dict[str, int], n1: str, n2: str, y: complex) -> None:
    p, q = idx.get(n1), idx.get(n2)
    if p is not None:
        A[p, p] += y
    if q is not None:
        A[q, q] += y
    if p is not None and q is not None:
        A[p, q] -= y
        A[q, p] -= y


def stamp_resistor(A: np.ndarray, idx: dict[str, int], r: Resistor) -> None:
    """Conductance g = 1/R between nodes p and q. KCL: current leaving p is g(vp - vq).

                 p    q
          p  [ +g   -g ]
          q  [ -g   +g ]
    """
    _stamp_admittance(A, idx, r.n1, r.n2, 1.0 / r.value)


def stamp_capacitor(A: np.ndarray, idx: dict[str, int], c: Capacitor, s: complex) -> None:
    """i = C dv/dt becomes I = sC V (s = j*omega): an admittance y = sC, stamped like a
    resistor with g replaced by y. No extra unknown, since I is a function of the node voltages.
    At DC s = 0, so y = 0: nothing is stamped (open circuit).

                 p     q
          p  [ +sC   -sC ]
          q  [ -sC   +sC ]
    """
    _stamp_admittance(A, idx, c.n1, c.n2, s * c.value)


def stamp_inductor(A: np.ndarray, idx: dict[str, int], row: int, l: Inductor, s: complex) -> None:
    """v = L di/dt becomes V = sL I. Written as an admittance this is 1/(sL), infinite at DC,
    so the current i (flowing n1 -> n2) is an extra unknown at index `row`, like a voltage
    source: the column puts i into KCL, the row is the constraint  v1 - v2 - sL i = 0.
    At DC s = 0 the row is v1 = v2: a 0 V source (short circuit).

                 n1   n2    i   |  b
          n1  [   0    0   +1   |  0 ]
          n2  [   0    0   -1   |  0 ]
          row [  +1   -1   -sL  |  0 ]
    """
    p, q = idx.get(l.n1), idx.get(l.n2)
    if p is not None:
        A[p, row] += 1.0
        A[row, p] += 1.0
    if q is not None:
        A[q, row] -= 1.0
        A[row, q] -= 1.0
    A[row, row] -= s * l.value


def stamp_voltage_source(A: np.ndarray, b: np.ndarray, idx: dict[str, int],
                         row: int, v: VoltageSource, value: complex | None = None) -> None:
    """Extra unknown i (the branch current, flowing n+ -> through source -> n-) at index `row`.

    The column puts i into KCL (it leaves n+, enters n-); the row is the
    constraint  v(n+) - v(n-) = V.   V is `value`, default the DC value (.ac passes the phasor).

                 n+   n-   i  |  b
          n+  [   0    0   +1 |  0 ]
          n-  [   0    0   -1 |  0 ]
          row [  +1   -1    0 |  V ]
    """
    p, q = idx.get(v.n_plus), idx.get(v.n_minus)
    if p is not None:
        A[p, row] += 1.0
        A[row, p] += 1.0
    if q is not None:
        A[q, row] -= 1.0
        A[row, q] -= 1.0
    b[row] += v.dc if value is None else value


def stamp_current_source(b: np.ndarray, idx: dict[str, int], i: CurrentSource,
                         value: complex | None = None) -> None:
    """Current I flows n+ -> through source -> n-: it is removed from n+ and injected into n-.
    Only b changes (b holds the current injected into each node). I is `value`, default DC.

          b[n+] -= I
          b[n-] += I
    """
    p, q = idx.get(i.n_plus), idx.get(i.n_minus)
    amps = i.dc if value is None else value
    if p is not None:
        b[p] -= amps
    if q is not None:
        b[q] += amps


def diode_iv(m: DiodeModel, vd: float) -> tuple[float, float]:
    """Shockley current and conductance at junction voltage vd, plus the GMIN shunt:
    i = IS (e^{vd/(N Vt)} - 1) + GMIN vd,   g = di/dvd = IS/(N Vt) e^{vd/(N Vt)} + GMIN.
    shortcut: the exponent is clipped at 700 to avoid overflow, so currents beyond ~18 V
    forward are wrong; Newton's voltage limiting keeps real iterates far below that."""
    nvt = m.N * VT
    e = math.exp(min(vd / nvt, 700.0))
    return m.IS * (e - 1.0) + GMIN * vd, m.IS / nvt * e + GMIN


def stamp_diode(A: np.ndarray, b: np.ndarray, idx: dict[str, int], d: Diode,
                vd: float) -> tuple[float, float]:
    """Newton companion model of a diode, linearised at junction voltage vd (anode - cathode):
    i(v) ~ g v + Ieq with g = di/dv at vd and Ieq = i(vd) - g vd. That is a conductance g in
    parallel with a current source Ieq flowing anode -> cathode. (Series resistance RS is a
    separate resistor, added by the Newton solver.) Returns (g, Ieq).

                  anode  cathode |  b
          anode  [  +g     -g    | -Ieq ]
          cathode[  -g     +g    | +Ieq ]
    """
    i, g = diode_iv(d.model, vd)
    ieq = i - g * vd
    _stamp_admittance(A, idx, d.anode, d.cathode, g)
    p, q = idx.get(d.anode), idx.get(d.cathode)
    if p is not None:
        b[p] -= ieq
    if q is not None:
        b[q] += ieq
    return g, ieq


def stamp_diode_small_signal(A: np.ndarray, idx: dict[str, int], d: Diode, g: float) -> None:
    """A diode in small-signal AC is just its conductance g = di/dv at the DC operating point:
    the constant part of the current (Ieq) is a DC quantity and vanishes for the AC deviation.

                  anode  cathode
          anode  [  +g     -g  ]
          cathode[  -g     +g  ]
    """
    _stamp_admittance(A, idx, d.anode, d.cathode, g)


def _stamp_voltage_output(A: np.ndarray, idx: dict[str, int], row: int, n_plus: str, n_minus: str) -> None:
    """The branch-current column and constraint-row skeleton shared by every element that fixes
    v(n+) - v(n-) (V, E, H): the unknown current i flows n+ -> through the element -> n-."""
    p, q = idx.get(n_plus), idx.get(n_minus)
    if p is not None:
        A[p, row] += 1.0
        A[row, p] += 1.0
    if q is not None:
        A[q, row] -= 1.0
        A[row, q] -= 1.0


def stamp_vcvs(A: np.ndarray, idx: dict[str, int], row: int, e: VCVS) -> None:
    """E: v(n+) - v(n-) = gain (v(nc+) - v(nc-)), with its own branch current i at index `row`.
    Same skeleton as a voltage source, but the constraint row also depends on the control nodes.

                 n+   n-   nc+    nc-    i
          n+  [   0    0    0      0    +1 ]
          n-  [   0    0    0      0    -1 ]
          row [  +1   -1  -gain  +gain   0 ]   (right-hand side 0)
    """
    _stamp_voltage_output(A, idx, row, e.n_plus, e.n_minus)
    cp, cm = idx.get(e.nc_plus), idx.get(e.nc_minus)
    if cp is not None:
        A[row, cp] -= e.gain
    if cm is not None:
        A[row, cm] += e.gain


def stamp_vccs(A: np.ndarray, idx: dict[str, int], e: VCCS) -> None:
    """G: a current gm (v(nc+) - v(nc-)) leaves n+ and enters n-. No extra unknown: the current
    is a function of node voltages, so it goes straight into the KCL rows.

                 nc+   nc-
          n+  [  +gm   -gm ]
          n-  [  -gm   +gm ]
    """
    for node, sign in ((e.n_plus, +1.0), (e.n_minus, -1.0)):
        r = idx.get(node)
        if r is None:
            continue
        for ctrl, csign in ((e.nc_plus, +1.0), (e.nc_minus, -1.0)):
            c = idx.get(ctrl)
            if c is not None:
                A[r, c] += sign * csign * e.gm


def stamp_cccs(A: np.ndarray, idx: dict[str, int], sense_row: int, e: CCCS) -> None:
    """F: a current gain * i(Vsense) leaves n+ and enters n-. i(Vsense) is already an unknown (the
    sense source's branch current, column `sense_row`), so no new unknown is needed.

                 i(Vsense)
          n+  [   +gain ]
          n-  [   -gain ]
    """
    p, q = idx.get(e.n_plus), idx.get(e.n_minus)
    if p is not None:
        A[p, sense_row] += e.gain
    if q is not None:
        A[q, sense_row] -= e.gain


def stamp_ccvs(A: np.ndarray, idx: dict[str, int], row: int, sense_row: int, e: CCVS) -> None:
    """H: v(n+) - v(n-) = rm * i(Vsense), with its own branch current i at index `row`.

                 n+   n-    i    i(Vsense)
          n+  [   0    0   +1       0 ]
          n-  [   0    0   -1       0 ]
          row [  +1   -1    0      -rm ]   (right-hand side 0)
    """
    _stamp_voltage_output(A, idx, row, e.n_plus, e.n_minus)
    A[row, sense_row] -= e.rm
