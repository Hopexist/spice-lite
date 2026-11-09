"""MNA stamps: how each element adds itself to  A x = b.

x = [node voltages (Circuit.node_index order) | branch currents (Circuit.branch_elements order)].
`idx` is Circuit.node_index(); ground ("0") is absent, so idx.get(node) is None
and its row/column is simply skipped (ground is the 0 V reference).

`s` is the complex frequency j*omega (AC) or 0 (DC). The same stamps serve both:
at DC a capacitor (admittance s*C = 0) vanishes and an inductor's row becomes v+ = v-.
"""
from __future__ import annotations

import numpy as np

from .circuit import Capacitor, CurrentSource, Inductor, Resistor, VoltageSource


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
