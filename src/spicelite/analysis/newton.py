"""Newton-Raphson DC solve for circuits with diodes.

A diode current i = IS(e^{v/NVt} - 1) is not linear in v, so MNA can't solve it directly.
Newton linearises it around the current guess: a conductance g = di/dv in parallel with a
current source Ieq = i(v0) - g v0 (elements.stamp_diode). Stamp those, solve the now-linear
MNA system, move the guess to the solution, and repeat until it stops changing.

Three things keep it robust:
* Voltage limiting (`pnjlim`): e^{v/Vt} explodes if Newton jumps a junction by volts, so a
  junction's voltage is only allowed to creep up logarithmically per iteration.
* Convergence on voltages AND currents: every unknown must have settled (reltol/vntol for
  voltages, reltol/abstol for branch currents) and each diode's linearised current must match
  its true current at the new voltage (a nonlinear KCL residual). No limiting may have fired.
* gmin stepping as a fallback (see `solve_nonlinear`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from ..circuit import Circuit, ConvergenceError, Diode, Mosfet, Resistor, SingularCircuitError
from ..elements import VT, diode_iv, mos_current, mos_threshold, stamp_diode, stamp_mosfet
from ..mna import build, check_topology

# Same tight tolerances the ngspice runner uses for its transient reference (ngspice's own
# defaults are 1e-3 / 1e-12 / 1e-6); tight is cheap here because Newton converges quadratically.
RELTOL, ABSTOL, VNTOL = 1e-6, 1e-14, 1e-9
MAX_ITER = 100  # per Newton run; ngspice's ITL1 is also 100
GMIN_STAGES = [10.0**-k for k in range(2, 13)] + [0.0]  # 1e-2 ... 1e-12, then none
NEWTON_DEVICES = (Diode, Mosfet)  # the device types _newton linearises; anything else registered as newton is an error


@dataclass
class NewtonResult:
    """Converged Newton solution x with its node index, iteration count and strategy."""
    x: np.ndarray  # full unknown vector for the EXPANDED circuit (see _expand)
    idx: dict[str, int]  # node name -> index in x, including hidden RS nodes "<diode>#int"
    iterations: int  # total Newton iterations, including any failed first attempt
    strategy: str  # "newton" (plain) or "gmin" (the gmin-stepping fallback rescued it)


def pnjlim(vnew: float, vold: float, vt: float, vcrit: float) -> tuple[float, bool]:
    """SPICE's pn-junction voltage limiter. Returns (limited voltage, whether it limited).
    Above vcrit (where the diode's slope is so steep that Newton would overshoot) a jump of
    more than 2 vt is replaced by a logarithmic step, so the voltage creeps toward the answer
    instead of jumping and overflowing the exponential.
    shortcut: only the forward limit; ngspice also limits how fast a junction goes REVERSE."""
    if vnew > vcrit and abs(vnew - vold) > 2 * vt:
        if vold > 0:
            arg = (vnew - vold) / vt
            vnew = vold + vt * (2 + math.log(arg - 2)) if arg > 0 else vold - vt * (2 + math.log(2 - arg))
        else:
            vnew = vt * math.log(vnew / vt)
        return vnew, True
    return vnew, False


def fetlim(vnew: float, vold: float, vto: float) -> float:
    """SPICE's MOSFET gate-voltage limiter (DEVfetlim). Newton on a square-law device can jump the
    gate from deep cutoff to far above threshold in one step; this caps how fast Vgs may move
    near and above threshold (a step is limited to ~2 V above, and the voltage is not allowed to
    cross threshold by more than a controlled amount in one iteration)."""
    vtsthi = abs(2 * (vold - vto)) + 2
    vtstlo = vtsthi / 2 + 2
    vtox = vto + 3.5
    delv = vnew - vold
    if vold >= vto:
        if vold >= vtox:
            if delv <= 0:
                if vnew >= vtox:
                    if -delv > vtstlo:
                        vnew = vold - vtstlo
                else:
                    vnew = max(vnew, vto + 2)
            elif delv >= vtsthi:
                vnew = vold + vtsthi
        elif delv <= 0:
            vnew = max(vnew, vto - 0.5)
        else:
            vnew = min(vnew, vto + 4)
    elif delv <= 0:
        if -delv > vtsthi:
            vnew = vold - vtsthi
    else:
        vtemp = vto + 0.5
        if vnew <= vtemp:
            if delv > vtstlo:
                vnew = vold + vtstlo
        else:
            vnew = vtemp
    return vnew


def limvds(vnew: float, vold: float) -> float:
    """SPICE's drain-source voltage limiter (DEVlimvds): Vds may not triple per iteration."""
    if vold >= 3.5:
        if vnew > vold:
            return min(vnew, 3 * vold + 2)
        return max(vnew, 2.0) if vnew < 3.5 else vnew
    return min(vnew, 4.0) if vnew > vold else max(vnew, -0.5)


def limit_mos(raw: tuple[float, float, float], old: tuple[float, float, float], von: float):
    """Limit a MOSFET's (vgs, vds, vbs), all in the NMOS frame, as ngspice's mos1load does. In the
    reverse direction (vds < 0) the gate-DRAIN voltage plays the role of vgs. Returns (new, limited)."""
    vgs, vds, vbs = raw
    vgso, vdso, _ = old
    vgd, vgdo = vgs - vds, vgso - vdso
    if vdso >= 0:
        vgs = fetlim(vgs, vgso, von)
        vds = limvds(vgs - vgd, vdso)
    else:
        vgd = fetlim(vgd, vgdo, von)
        vds = -limvds(-(vgs - vgd), -vdso)
        vgs = vgd + vds
    # vgs and vds are rebuilt through vgd, so an unlimited value can differ from `raw` by round-off:
    # call it limited only if it moved by more than that, and then keep the exact raw value.
    changed = abs(vgs - raw[0]) > 1e-12 or abs(vds - raw[1]) > 1e-12
    return ((vgs, vds, vbs) if changed else raw), changed


def _expand(circuit: Circuit) -> Circuit:
    """Give each diode with series resistance RS > 0 a hidden internal node: the resistor
    runs anode -> "<name>#int" and the junction itself runs "<name>#int" -> cathode.
    Idempotent: the junction diode is left with RS = 0, so expanding twice changes nothing."""
    out = []
    for e in circuit.elements:
        if isinstance(e, Diode) and e.model.RS > 0:
            mid = f"{e.name}#int"
            out += [Resistor(f"{e.name}#rs", e.anode, mid, e.model.RS),
                    Diode(e.name, mid, e.cathode, e.model_name, replace(e.model, RS=0.0))]  # RS now lives in the resistor
        else:
            out.append(e)
    return replace(circuit, elements=out)


def _newton(A_lin, b_lin, idx, n, devices, names, x_start, gshunt, max_iter, reltol, abstol, vntol):
    """Plain Newton from x_start over the nonlinear `devices` (diodes and MOSFETs).
    Returns (x, iterations) or raises ConvergenceError."""
    size = len(b_lin)
    if unknown := [d.name for d in devices if not isinstance(d, NEWTON_DEVICES)]:
        raise TypeError(f"no Newton linearisation for {', '.join(unknown)}")
    diodes = [d for d in devices if isinstance(d, Diode)]
    mosfets = [d for d in devices if isinstance(d, Mosfet)]
    pa = [idx.get(d.anode) for d in diodes]
    pc = [idx.get(d.cathode) for d in diodes]
    nvt = [d.model.N * VT for d in diodes]
    vcrit = [v * math.log(v / (math.sqrt(2) * d.model.IS)) for v, d in zip(nvt, diodes)]
    abs_floor = np.array([vntol] * n + [abstol] * (size - n))
    pm = [[idx.get(node) for node in (m.drain, m.gate, m.source, m.bulk)] for m in mosfets]

    def vj(x, k):  # junction voltage of diode k at x
        return (x[pa[k]] if pa[k] is not None else 0.0) - (x[pc[k]] if pc[k] is not None else 0.0)

    def vnode(x, p):
        return x[p] if p is not None else 0.0

    def mos_v(x, k):  # actual (vgs, vds, vbs) of MOSFET k at x
        vd, vg, vs, vb = (vnode(x, p) for p in pm[k])
        return vg - vs, vd - vs, vb - vs

    x = x_start.copy()
    vd_used = [vj(x, k) for k in range(len(diodes))]  # voltage each junction was last linearised at
    mv_used = [tuple(mosfets[k].model.sign * v for v in mos_v(x, k)) for k in range(len(mosfets))]  # NMOS frame
    worst, worst_dx = names[0], 0.0
    for it in range(1, max_iter + 1):
        A, b = A_lin.copy(), b_lin.copy()
        if gshunt:
            A[np.arange(n), np.arange(n)] += gshunt
        limited, lin = False, []
        for k, d in enumerate(diodes):
            vd_used[k], lim = pnjlim(vj(x, k), vd_used[k], nvt[k], vcrit[k])
            limited |= lim
            lin.append(stamp_diode(A, b, idx, d, vd_used[k]))
        mlin = []
        for k, m in enumerate(mosfets):
            t = m.model.sign
            raw = tuple(t * v for v in mos_v(x, k))
            _, vdso, vbso = mv_used[k]
            von = mos_threshold(m.model, vbso - vdso if vdso < 0 else vbso)  # threshold at the effective bulk bias
            mv_used[k], lim = limit_mos(raw, mv_used[k], von)
            limited |= lim
            mlin.append(stamp_mosfet(A, b, idx, m, *(t * v for v in mv_used[k])))
        try:
            x_new = np.linalg.solve(A, b)
        except np.linalg.LinAlgError as err:
            raise SingularCircuitError(f"circuit matrix is singular: {err}") from err

        tol = reltol * np.maximum(np.abs(x_new), np.abs(x)) + abs_floor
        ratio = np.abs(x_new - x) / tol  # <= 1 means that unknown has settled
        k_worst = int(np.argmax(ratio))
        worst, worst_dx = names[k_worst], float(np.abs(x_new - x)[k_worst])
        ok = bool((ratio <= 1).all()) and not limited and it > 1
        for k, d in enumerate(diodes):  # current residual: linearised vs true diode current
            g, ieq = lin[k]
            i_lin = g * vj(x_new, k) + ieq
            i_true = diode_iv(d.model, vj(x_new, k))[0]
            if abs(i_lin - i_true) > reltol * max(abs(i_lin), abs(i_true)) + abstol:
                ok = False
        for k, m in enumerate(mosfets):  # same residual for the channel current, in the stamped direction
            reverse, gm, gds, gmbs, ieq = mlin[k]
            vgs, vds, vbs = mos_v(x_new, k)
            if reverse:
                vgs, vds, vbs = vgs - vds, -vds, vbs - vds
            i_lin = gm * vgs + gds * vds + gmbs * vbs + ieq
            i_true = mos_current(m, *mos_v(x_new, k)) * (-1 if reverse else 1)
            if abs(i_lin - i_true) > reltol * max(abs(i_lin), abs(i_true)) + abstol:
                ok = False
        x = x_new
        if ok:
            return x, it
    raise ConvergenceError(
        f"Newton-Raphson did not converge in {max_iter} iterations; worst unknown is {worst} "
        f"(still changing by {worst_dx:.3g} per iteration)", max_iter, worst)


def solve_nonlinear(circuit: Circuit, t: float | None = None, x0: np.ndarray | None = None,
                    max_iter: int = MAX_ITER, fallback: bool = True, reltol: float = RELTOL,
                    abstol: float = ABSTOL, vntol: float = VNTOL) -> NewtonResult:
    """DC solve of a circuit with diodes. `x0` is an initial guess (a previous NewtonResult.x
    for the same circuit; a .dc sweep passes the previous point's solution), default all zero.

    Fallback: gmin stepping. If plain Newton fails, a large conductance is added from every
    node to ground (1e-2 S), which makes the circuit nearly linear and trivially solvable, and
    is then shrunk by a decade at a time to 1e-12 and finally removed, each stage starting
    from the previous solution. Chosen over source stepping because the usual diode trouble
    is weakly-defined nodes (reverse-biased or cut-off junctions leave nodes floating), which
    gmin fixes directly, and it is ngspice's own first fallback.
    shortcut: source stepping (scale all sources 0 -> 100 %) is not implemented; add it if a
    circuit appears that gmin stepping cannot rescue.
    """
    check_topology(circuit, dc=True)
    ex = _expand(circuit)
    idx = ex.node_index()
    n = len(idx)
    A_lin, b_lin = build(ex, None, t, nonlinear_ok=True)
    names = list(idx) + [f"i({e.name})" for e in ex.branch_elements()]
    args = (A_lin, b_lin, idx, n, ex.nonlinear(), names)
    tol = (max_iter, reltol, abstol, vntol)
    start = np.zeros(len(b_lin)) if x0 is None else np.asarray(x0, dtype=float)
    try:
        x, it = _newton(*args, start, 0.0, *tol)
        return NewtonResult(x, idx, it, "newton")
    except ConvergenceError as first:
        if not fallback:
            raise
        total, x = first.iterations, np.zeros(len(b_lin))
    for g in GMIN_STAGES:
        try:
            x, it = _newton(*args, x, g, *tol)
        except ConvergenceError as err:
            raise ConvergenceError(
                f"gmin stepping failed at gmin = {g:g} S after {total + err.iterations} "
                f"iterations; worst unknown is {err.worst_node}",
                total + err.iterations, err.worst_node) from None
        total += it
    return NewtonResult(x, idx, total, "gmin")
