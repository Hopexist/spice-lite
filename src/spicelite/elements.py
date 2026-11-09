"""MNA stamps: how each element adds itself to  A x = b.

x = [node voltages (Circuit.node_index order) | voltage-source branch currents].
`idx` is Circuit.node_index(); ground ("0") is absent, so idx.get(node) is None
and its row/column is simply skipped (ground is the 0 V reference).
"""
from __future__ import annotations

import numpy as np

from .circuit import CurrentSource, Resistor, VoltageSource


def stamp_resistor(A: np.ndarray, idx: dict[str, int], r: Resistor) -> None:
    """Conductance g = 1/R between nodes p and q. KCL: current leaving p is g(vp - vq).

                 p    q
          p  [ +g   -g ]
          q  [ -g   +g ]
    """
    g = 1.0 / r.value
    p, q = idx.get(r.n1), idx.get(r.n2)
    if p is not None:
        A[p, p] += g
    if q is not None:
        A[q, q] += g
    if p is not None and q is not None:
        A[p, q] -= g
        A[q, p] -= g


def stamp_voltage_source(A: np.ndarray, b: np.ndarray, idx: dict[str, int],
                         row: int, v: VoltageSource) -> None:
    """Extra unknown i (the branch current, flowing n+ -> through source -> n-) at index `row`.

    The column puts i into KCL (it leaves n+, enters n-); the row is the
    constraint  v(n+) - v(n-) = V.

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
    b[row] += v.dc


def stamp_current_source(b: np.ndarray, idx: dict[str, int], i: CurrentSource) -> None:
    """Current I flows n+ -> through source -> n-: it is removed from n+ and injected into n-.
    Only b changes (b holds the current injected into each node).

          b[n+] -= I
          b[n-] += I
    """
    p, q = idx.get(i.n_plus), idx.get(i.n_minus)
    if p is not None:
        b[p] -= i.dc
    if q is not None:
        b[q] += i.dc
