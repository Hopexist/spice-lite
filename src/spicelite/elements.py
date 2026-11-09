"""MNA stamps: how each element adds itself to  A x = b.

x = [node voltages (Circuit.node_index order) | branch currents (Circuit.branch_elements order)].
`idx` is Circuit.node_index(); ground ("0") is absent, so idx.get(node) is None
and its row/column is simply skipped (ground is the 0 V reference).

`s` is the complex frequency j*omega (AC) or 0 (DC). The same stamps serve both:
at DC a capacitor (admittance s*C = 0) vanishes and an inductor's row becomes v+ = v-.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from .circuit import (
    CCCS,
    CCVS,
    VCCS,
    VCVS,
    Capacitor,
    CurrentSource,
    Diode,
    DiodeModel,
    Inductor,
    Mosfet,
    MosModel,
    Resistor,
    VoltageSource,
)

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
    _stamp_voltage_output(A, idx, row, v.n_plus, v.n_minus)
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


# ---- MOSFET, level 1 (Shichman-Hodges) ----------------------------------------------------------
# shortcut: no intrinsic capacitances (Cgs, Cgd, Cgb, Cbd, Cbs) and the bulk-drain / bulk-source junction
# diodes are reduced to their GMIN conductance (no exponential, no leakage current, no forward
# conduction when the bulk is biased more than ~0.6 V above a channel terminal). The device is a
# voltage-controlled current source plus those two tiny conductances; circuits add explicit load caps.
# Upgrade when a transient needs gate charge (the inverter's switching delay is then underestimated).


def mos_threshold(m: MosModel, vbs: float) -> float:
    """Threshold voltage in the NMOS frame: Vth = VTO' + GAMMA (sqrt(PHI - Vbs) - sqrt(PHI)), VTO' = type * VTO.
    The body effect: a reverse-biased bulk (Vbs < 0) widens the depletion region and raises Vth. For
    Vbs > 0 the square root would fail at Vbs = PHI, so, like ngspice, it is continued by sqrt(PHI)/(1 + Vbs/2PHI)."""
    return m.sign * m.VTO + m.GAMMA * (_sarg(m, vbs)[0] - math.sqrt(m.PHI))


def _sarg(m: MosModel, vbs: float) -> tuple[float, float]:
    """sqrt(PHI - Vbs) and its derivative with respect to Vbs."""
    if vbs <= 0:
        s = math.sqrt(m.PHI - vbs)
        return s, -0.5 / s
    s = math.sqrt(m.PHI) / (1 + 0.5 * vbs / m.PHI)
    return s, -0.5 * s / (m.PHI * (1 + 0.5 * vbs / m.PHI))


def _shichman_hodges(m: MosModel, beta: float, vgs: float, vds: float, vbs: float):
    """NMOS-frame drain current and (gm, gds, gmbs) for vds >= 0. With Vov = Vgs - Vth and
    lam = 1 + LAMBDA Vds (channel-length modulation, applied in triode too, as ngspice does):
        cutoff     Vov <= 0       i = 0
        triode     Vds <  Vov     i = beta (Vov Vds - Vds^2/2) lam
        saturation Vds >= Vov     i = beta/2 Vov^2 lam
    gm = di/dVgs, gds = di/dVds, gmbs = di/dVbs = -gm dVth/dVbs."""
    sarg, dsarg = _sarg(m, vbs)
    vov = vgs - mos_threshold(m, vbs)
    if vov <= 0:
        return 0.0, 0.0, 0.0, 0.0
    lam = 1 + m.LAMBDA * vds
    if vds >= vov:
        i, gm, gds = 0.5 * beta * vov**2 * lam, beta * vov * lam, 0.5 * beta * vov**2 * m.LAMBDA
    else:
        core = vov * vds - 0.5 * vds**2
        i, gm, gds = beta * core * lam, beta * vds * lam, beta * (vov - vds) * lam + beta * core * m.LAMBDA
    return i, gm, gds, -gm * m.GAMMA * dsarg


def mos_eval(e: Mosfet, vgs: float, vds: float, vbs: float):
    """Evaluate a MOSFET at ACTUAL terminal voltages vgs = Vg - Vs, vds = Vd - Vs, vbs = Vb - Vs.
    Returns (i, gm, gds, gmbs, reverse, (vgs_e, vds_e, vbs_e)).

    PMOS is an NMOS with every voltage and current negated: evaluate at type * v, multiply the current
    by type; the derivatives gm, gds, gmbs keep their sign (two sign flips cancel).
    If Vds (in the NMOS frame) is negative the roles of drain and source swap: the channel is
    symmetric, so the device is evaluated with the source pin as the "drain" (reverse = True).
    `i` then flows from the effective drain dn to the effective source sn (the pins swapped if
    reverse), and the conductances are with respect to the effective voltages vgs_e = Vg - V(sn),
    vds_e = V(dn) - V(sn), vbs_e = Vb - V(sn), which are returned for the companion model."""
    t = e.model.sign
    reverse = t * vds < 0
    if reverse:
        vgs, vds, vbs = vgs - vds, -vds, vbs - vds
    i, gm, gds, gmbs = _shichman_hodges(e.model, e.model.KP * e.W / e.L, t * vgs, t * vds, t * vbs)
    return t * i, gm, gds, gmbs, reverse, (vgs, vds, vbs)


def mos_current(e: Mosfet, vgs: float, vds: float, vbs: float) -> float:
    """Current into the drain pin (out of the source pin), at actual voltages."""
    i, *_, reverse, _v = mos_eval(e, vgs, vds, vbs)
    return -i if reverse else i


def _stamp_mos_g(A, idx, e: Mosfet, reverse: bool, gm: float, gds: float, gmbs: float) -> None:
    """The conductance part of the companion model, shared by Newton (DC / transient) and AC.
    Both bulk junctions also contribute a GMIN conductance (bulk-drain, bulk-source).
    With dn the effective drain and sn the effective source, KCL at dn has the channel current
    gds (Vdn - Vsn) + gm (Vg - Vsn) + gmbs (Vb - Vsn) leaving it, and sn gets the negative:

                     dn      g     b       sn
              dn  [ +gds    +gm  +gmbs  -(gds+gm+gmbs) ]
              sn  [ -gds    -gm  -gmbs  +(gds+gm+gmbs) ]
    """
    _stamp_admittance(A, idx, e.bulk, e.drain, GMIN)  # what is left of the junctions (as in ngspice);
    _stamp_admittance(A, idx, e.bulk, e.source, GMIN)  # also keeps a node of only cut-off devices non-singular
    dn, sn = (e.source, e.drain) if reverse else (e.drain, e.source)
    cols = [(dn, gds), (e.gate, gm), (e.bulk, gmbs), (sn, -(gds + gm + gmbs))]
    for row, sign in ((dn, 1.0), (sn, -1.0)):
        r = idx.get(row)
        if r is None:
            continue
        for node, g in cols:
            c = idx.get(node)
            if c is not None:
                A[r, c] += sign * g


def stamp_mosfet(A: np.ndarray, b: np.ndarray, idx: dict[str, int], e: Mosfet,
                 vgs: float, vds: float, vbs: float):
    """Newton companion model of a MOSFET linearised at actual (vgs, vds, vbs): the conductances of
    `_stamp_mos_g` plus a current source Ieq = i - gm vgs_e - gds vds_e - gmbs vbs_e flowing dn -> sn
    (b[dn] -= Ieq, b[sn] += Ieq). Returns (reverse, gm, gds, gmbs, Ieq) for the convergence check."""
    i, gm, gds, gmbs, reverse, (vg, vd, vb) = mos_eval(e, vgs, vds, vbs)
    ieq = i - gm * vg - gds * vd - gmbs * vb
    _stamp_mos_g(A, idx, e, reverse, gm, gds, gmbs)
    dn, sn = (e.source, e.drain) if reverse else (e.drain, e.source)
    if (r := idx.get(dn)) is not None:
        b[r] -= ieq
    if (r := idx.get(sn)) is not None:
        b[r] += ieq
    return reverse, gm, gds, gmbs, ieq


def stamp_mosfet_small_signal(A: np.ndarray, idx: dict[str, int], e: Mosfet,
                              vgs: float, vds: float, vbs: float) -> None:
    """In small-signal AC a MOSFET is its transconductances at the DC bias: the same conductance
    stamp as Newton uses, without the constant current Ieq."""
    _i, gm, gds, gmbs, reverse, _v = mos_eval(e, vgs, vds, vbs)
    _stamp_mos_g(A, idx, e, reverse, gm, gds, gmbs)


# ---- the registry: how each element type enters each analysis -------------------------------------
# Every analysis assembles its system through STAMPS (via mna.stamp_matrix / mna.stamp_sources), so an
# element type has exactly one entry point here and cannot be stamped in one analysis and forgotten
# in another. tests/test_stamp_registry.py fails if an element the parser can produce is missing.

@dataclass(frozen=True)
class Stamp:
    """One element type's ways into MNA, split by what they depend on.

    matrix(A, idx, rows, e, s): the part of A that depends only on s, the complex frequency at AC, 0 at DC,
        and the companion-model coefficient 1/h (backward Euler) or 2/h (trapezoidal) in a transient. It does
        not depend on time or on the solution, so a transient can build and factor it once per step size.
    rhs(b, idx, rows, e, value): an independent source's value (DC, AC phasor or waveform at t) in b.
    newton: a nonlinear device, linearised at every Newton iteration by analysis.newton._newton instead.
    small_signal(idx, e, x_bias) -> stamp(A): a nonlinear device's AC model, linearised once at the DC bias
        x_bias; the returned function is then applied at every frequency.
    The transient history currents of C and L (their companion-model sources) live in analysis.tran:
    they are the integration method, not the element, and only the transient has them.
    """
    matrix: Callable | None = None
    rhs: Callable | None = None
    newton: bool = False
    small_signal: Callable | None = None


def _source_rhs_v(b, idx, rows, e: VoltageSource, value) -> None:
    b[rows[e.name]] += value  # the constraint row v(n+) - v(n-) = V


def _diode_small_signal(idx, d: Diode, x):
    p, q = idx.get(d.anode), idx.get(d.cathode)
    g = diode_iv(d.model, (x[p] if p is not None else 0.0) - (x[q] if q is not None else 0.0))[1]
    return lambda A: stamp_diode_small_signal(A, idx, d, g)


def _mosfet_small_signal(idx, m: Mosfet, x):
    vd, vg, vs, vb = (x[idx[n]] if n in idx else 0.0 for n in (m.drain, m.gate, m.source, m.bulk))
    return lambda A: stamp_mosfet_small_signal(A, idx, m, vg - vs, vd - vs, vb - vs)


STAMPS: dict[type, Stamp] = {
    Resistor: Stamp(matrix=lambda A, idx, rows, e, s: stamp_resistor(A, idx, e)),
    Capacitor: Stamp(matrix=lambda A, idx, rows, e, s: stamp_capacitor(A, idx, e, s)),
    Inductor: Stamp(matrix=lambda A, idx, rows, e, s: stamp_inductor(A, idx, rows[e.name], e, s)),
    VoltageSource: Stamp(matrix=lambda A, idx, rows, e, s: _stamp_voltage_output(A, idx, rows[e.name], e.n_plus, e.n_minus),
                         rhs=_source_rhs_v),
    CurrentSource: Stamp(matrix=lambda A, idx, rows, e, s: None,  # no matrix entries: it only injects current
                         rhs=lambda b, idx, rows, e, value: stamp_current_source(b, idx, e, value)),
    # controlled sources are memoryless: the same constant entries at DC, every frequency and every time step
    VCVS: Stamp(matrix=lambda A, idx, rows, e, s: stamp_vcvs(A, idx, rows[e.name], e)),
    VCCS: Stamp(matrix=lambda A, idx, rows, e, s: stamp_vccs(A, idx, e)),
    CCCS: Stamp(matrix=lambda A, idx, rows, e, s: stamp_cccs(A, idx, rows[e.sense], e)),
    CCVS: Stamp(matrix=lambda A, idx, rows, e, s: stamp_ccvs(A, idx, rows[e.name], rows[e.sense], e)),
    Diode: Stamp(newton=True, small_signal=_diode_small_signal),
    Mosfet: Stamp(newton=True, small_signal=_mosfet_small_signal),
}


def stamp_of(e) -> Stamp:
    """The registry entry for an element; a type nobody registered is an error, never a silent no-op."""
    try:
        return STAMPS[type(e)]
    except KeyError:
        raise TypeError(f"{getattr(e, 'name', e)!r}: no MNA stamp registered for {type(e).__name__} "
                        "(add it to elements.STAMPS)") from None
