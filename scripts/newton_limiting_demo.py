"""Why Newton-Raphson on a diode needs junction voltage limiting: bare Newton vs spicelite on V - R - diode.

    python scripts/newton_limiting_demo.py

Bare Newton here is the textbook iteration on the diode voltage v with f(v) = (Vs - v)/R - Is (e^(v/Vt) - 1), starting from
0 V, no limiting, converged when a step is smaller than 1e-9 V. spicelite's count comes from solve_nonlinear (which also
needs two iterations minimum and a current-residual check, so the two counts are not the same stopping rule; the gap is
what matters).
"""
from __future__ import annotations

import math

from spicelite import parse
from spicelite.analysis.newton import solve_nonlinear

IS, VT, R = 1e-14, 0.025864870, 1000.0  # VT = kT/q at 27 C with ngspice's constants, as in the simulator


def bare_newton(vs: float, tol: float = 1e-9, cap: int = 2000) -> tuple[int, float, str]:
    v = 0.0
    for k in range(1, cap + 1):
        try:
            i, g = IS * (math.exp(v / VT) - 1), IS / VT * math.exp(v / VT)
        except OverflowError:
            return k, v, "exp overflow"
        step = ((vs - v) / R - i) / (1 / R + g)
        v += step
        if abs(step) < tol:
            return k, v, "converged"
    return cap, v, "hit the iteration cap"


def main() -> None:
    print("| Vs (V) | bare Newton | spicelite |\n|---:|---|---|")
    for vs in (1.0, 5.0, 1000.0):
        k, v, state = bare_newton(vs)
        net = f"t\nV1 in 0 {vs}\nR1 in a 1k\nD1 a 0 dm\n.model dm D(IS=1e-14)\n.op\n"
        r = solve_nonlinear(parse(net))
        print(f"| {vs:g} | {k} iterations ({state}) | {r.iterations} iterations ({r.strategy}), diode at {r.x[1]:.6f} V |")


if __name__ == "__main__":
    main()
