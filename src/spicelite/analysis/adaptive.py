"""Adaptive time-step control for `.tran` (`.options step=adaptive`, or `tran(adaptive=True | StepControl(...))`).

A fixed step must be small enough for the FASTEST thing that ever happens, so a circuit with widely
separated time constants wastes almost every step. Adaptive stepping keeps the local truncation error
(LTE) of each step near a tolerance instead.

* Estimate. The LTE of the trapezoidal rule is h^3 x3 / 12 and of backward Euler h^2 x2 / 2 (x3, x2 = the
  third and second time derivative of the solution). Both derivatives come from DIVIDED DIFFERENCES of the
  last accepted points (DD3 ~ x3 / 6, DD2 ~ x2 / 2), so the estimate needs no extra solve:
      trap  |LTE| ~ h^3 |DD3| / 2          BE  |LTE| ~ h^2 |DD2|
  Chosen over step doubling (three solves per step) and over a predictor-corrector difference (the same
  quantity, but needs an explicit predictor for every element type); this is the estimator SPICE itself uses.
* Accept a step if, for every unknown, |LTE| <= rtol max(|x|, |x_prev|) + floor (error ratio r <= 1);
  otherwise reject it and retry smaller. The next step is h (0.9 r^(-1/(p+1))) limited to [0.5, 2] x h
  (p = 1 for BE, 2 for trap), then rounded DOWN to hmax / 2^k so only a few step sizes ever occur and their
  factored matrices can be reused (grow factor 2, shrink factors 1/2 or more).
* Breakpoints. Steps land exactly on every PULSE / SIN corner (so an edge is never straddled). After a corner
  the history is discarded, because the derivatives jump there and would fool the estimator, and h restarts
  at the netlist's tstep.
* Guards. h < hmin, or more than max_steps accepted steps, raises a ConvergenceError that says where.

The matrix depends on h, so a linear circuit is re-factored whenever h changes (cached per size); a
fixed-step run keeps the factor-once fast path. Adaptive wins when it saves more steps than the extra
factorisations cost, which is what happens on circuits with widely separated time constants.
shortcut: a source that JUMPS (zero rise time) leaves the trapezoidal capacitor-current history stale for
one step; use a nonzero rise time or method=be there.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..circuit import Circuit, ConvergenceError, CurrentSource, TranSpec, VoltageSource


@dataclass
class StepControl:
    """Adaptive-step settings. For `.tran tstep tstop`, tstep is the INITIAL step and the restart step after
    every breakpoint; the step never exceeds `hmax` (default tstop / 50) nor falls below `hmin`
    (default tstop * 1e-9). `rtol`, `vabs`, `iabs` set the per-step error target: rtol of the
    unknown's size plus an absolute floor (volts for node voltages, amps for branch currents)."""

    rtol: float = 1e-4
    vabs: float = 1e-6
    iabs: float = 1e-9
    hmin: float | None = None
    hmax: float | None = None
    max_steps: int = 200_000

    def __post_init__(self) -> None:
        if min(self.rtol, self.vabs, self.iabs) <= 0 or self.max_steps < 1:
            raise ValueError("StepControl needs rtol, vabs, iabs > 0 and max_steps >= 1")
        if self.hmin is not None and self.hmax is not None and self.hmin > self.hmax:
            raise ValueError(f"StepControl hmin {self.hmin:g} is larger than hmax {self.hmax:g}")


def breakpoints(circuit: Circuit, tstop: float) -> list[float]:
    """Sorted times in (0, tstop] where a source waveform has a corner, always ending with tstop."""
    pts = {tstop}
    for e in circuit.elements:
        if isinstance(e, (VoltageSource, CurrentSource)) and e.tran is not None:
            pts.update(e.tran.breakpoints(tstop))
    return sorted(pts)


def divided_difference(ts: list[float], xs: list[np.ndarray]) -> np.ndarray:
    """The (len - 1)-th divided difference of x over the (non-uniform) times ts."""
    d = list(xs)
    for level in range(1, len(ts)):
        d = [(d[i + 1] - d[i]) / (ts[i + level] - ts[i]) for i in range(len(d) - 1)]
    return d[0]


def adaptive_loop(advance, state, spec: TranSpec, bps: list[float], ctl: StepControl, trap: bool, floor: np.ndarray):
    """Run the controller. `advance(state, t0, h, 0)` takes one step of size h and returns
    (x, capacitor currents, inductor voltages, Newton iterations); state is the first three.
    Returns (times, xs, iterations, rejected)."""
    tstop = spec.tstop
    hmin = ctl.hmin if ctl.hmin is not None else tstop * 1e-9
    hmax = max(ctl.hmax if ctl.hmax is not None else tstop / 50, hmin)
    order = 2 if trap else 1
    need = order + 1  # accepted points the divided difference needs besides the new one: 3 (trap) or 2 (BE)

    def quantise(h: float) -> float:  # the largest hmax / 2^k that is <= h
        return hmax * 2.0 ** -max(0, math.ceil(math.log2(hmax / h) - 1e-9))

    def factor(ratio: float) -> float:  # step-size multiplier for an error ratio, in [0.5, 2]
        return 2.0 if ratio == 0 else min(2.0, max(0.5, 0.9 * ratio ** (-1 / (order + 1))))

    h_restart = max(quantise(min(spec.tstep, hmax)), hmin)  # a tstep below hmin is raised to it
    times, xs, its = [0.0], [state[0]], [0]
    hist = [(0.0, state[0])]
    h, t, j, rejected = h_restart, 0.0, 0, 0
    while t < tstop:
        if len(times) > ctl.max_steps:
            raise ConvergenceError(
                f"adaptive transient needed more than max_steps = {ctl.max_steps} accepted steps "
                f"(reached t = {t:.6g} s of {tstop:g} s); raise max_steps or loosen rtol", len(times), "time")
        while bps[j] <= t + 1e-12 * tstop:
            j += 1
        remaining = bps[j] - t
        lands = h >= remaining * (1 - 1e-9)
        hh = remaining if lands else (remaining / 2 if remaining - h < 0.5 * h else h)  # never leave a sliver
        new = advance(state, t, hh, 0)
        x_new = new[0]
        ratio = None
        if len(hist) >= need:
            pts = hist[-need:]
            dd = divided_difference([p[0] for p in pts] + [t + hh], [p[1] for p in pts] + [x_new])
            lte = (hh**3 / 2 if trap else hh**2) * np.abs(dd)
            ratio = float(np.max(lte / (ctl.rtol * np.maximum(np.abs(x_new), np.abs(state[0])) + floor)))
        if ratio is not None and ratio > 1:
            rejected += 1
            h = min(quantise(hh * factor(ratio)), hh / 2)  # strictly smaller than the step that failed
            if h < hmin:
                raise ConvergenceError(
                    f"adaptive time step fell below hmin = {hmin:g} s at t = {t:.6g} s: the local error target "
                    "cannot be met (a discontinuity? loosen rtol or lower hmin)", 0, "time")
            continue
        t = bps[j] if lands else t + hh
        state = new[:3]
        times.append(t)
        xs.append(x_new)
        its.append(new[3])
        hist = ([(t, x_new)] if lands else hist + [(t, x_new)])[-need:]
        if lands:  # corner: the derivatives jump here, so forget the past and restart small
            h = h_restart
        elif ratio is not None:
            h = quantise(hh * factor(ratio))
    return np.array(times), np.array(xs), np.array(its), rejected
