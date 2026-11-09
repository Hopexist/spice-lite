"""Adaptive time stepping and initial conditions: accuracy against analytic answers, step counts against
fixed-step runs, breakpoints, guards, and the fixed-step path staying unchanged."""
import math
import warnings
from pathlib import Path

import numpy as np
import pytest

import spicelite.analysis.tran as tran_module
from spicelite import ConvergenceError, NetlistError, parse
from spicelite.analysis.adaptive import StepControl, breakpoints, divided_difference
from spicelite.analysis.tran import tran
from spicelite.circuit import TranSpec
from spicelite.ngspice import find_ngspice, run_tran

EXAMPLES = Path(__file__).parent.parent / "examples"
needs_ngspice = pytest.mark.skipif(
    find_ngspice() is None,
    reason="ngspice not found: put ngspice_con.exe/ngspice.exe on PATH or set NGSPICE=<path to exe>")

# the fixed-step runs below deliberately use a 1 us step against 1 ns source edges
pytestmark = pytest.mark.filterwarnings("ignore::spicelite.analysis.tran.ResolutionWarning")

RC = "RC step\nV1 in 0 PULSE(0 1 0 1n 1n 1 2)\nR1 in out 1k\nC1 out 0 1u\n.tran 1u 5m\n.end\n"  # tau = 1 ms


def rc_exact(t):
    return 1 - np.exp(-(t - 0.5e-9) / 1e-3)  # the 1 ns ramp delays the step by half its length


# ---- option and spec parsing ------------------------------------------------------------------

def test_options_step_and_method_can_be_combined():
    c = parse(RC.replace(".tran", ".options method=be step=adaptive\n.tran"))
    assert (c.method, c.step_control) == ("be", "adaptive")
    assert parse(RC).step_control == "fixed"
    assert parse(RC.replace(".tran", ".options step = fixed\n.tran")).step_control == "fixed"


@pytest.mark.parametrize("opt", ["step=sometimes", "tolerance=1e-3", "method=gear"])
def test_unknown_options_are_errors_with_line_numbers(opt):
    with pytest.raises(NetlistError, match=r"line 5: unsupported option .*supported: method=trap\|be, step=fixed\|adaptive"):
        parse(RC.replace(".tran", f".options {opt}\n.tran"))


def test_step_control_validation():
    for bad in (dict(rtol=0), dict(vabs=-1), dict(iabs=0), dict(max_steps=0), dict(hmin=1e-3, hmax=1e-6)):
        with pytest.raises(ValueError):
            StepControl(**bad)


# ---- the pieces ------------------------------------------------------------------------------

def test_divided_differences_recover_derivatives():
    ts = [0.0, 0.3, 0.7, 1.5]
    x = [np.array([t**3]) for t in ts]
    assert divided_difference(ts, x)[0] == pytest.approx(1.0)  # third divided difference of t^3 is 1 (= x3 / 6)
    assert divided_difference(ts[:3], [np.array([2 * t * t]) for t in ts[:3]])[0] == pytest.approx(2.0)


def test_breakpoints_collect_every_pulse_corner_and_the_sin_delay():
    c = parse("t\nV1 a 0 PULSE(0 1 1m 0.1m 0.2m 1m 3m)\nV2 b 0 SIN(0 1 1k 2m)\nR1 a 0 1k\nR2 b 0 1k\n.tran 1u 8m\n")
    got = breakpoints(c, 8e-3)
    want = [1e-3, 1.1e-3, 2.1e-3, 2.3e-3, 4e-3, 4.1e-3, 5.1e-3, 5.3e-3, 7e-3, 7.1e-3, 8e-3]  # PULSE corners ...
    want = sorted(set(want) | {2e-3, 8e-3})  # ... plus the SIN start at 2 ms and tstop
    assert got == pytest.approx(want, abs=1e-12) and got[-1] == 8e-3


# ---- accuracy and step counts ------------------------------------------------------------------

@pytest.mark.parametrize("method,tol,steps_max", [("trap", 3e-4, 120), ("be", 5e-3, 900)])
def test_rc_step_matches_the_analytic_response(method, tol, steps_max):
    # Observed (default StepControl, rtol 1e-4): trap 6.8e-5 with 94 steps, BE 1.2e-3 with 607 (67 rejected);
    # tolerances ~4x the error and ~1.3-1.5x the step count. BE is first order: more steps for a worse error.
    r = tran(parse(RC), method=method, adaptive=True)
    assert np.abs(r.voltages["out"] - rc_exact(r.time)).max() <= tol
    assert len(r.time) <= steps_max < 5001  # the fixed 1 us grid has 5001 points


def test_tighter_tolerance_means_more_steps_and_less_error():
    # series RLC (R 10, L 10 mH, C 100 nF; f0 ~ 5 kHz, Q ~ 10) step response, capacitor voltage, analytic
    net = "t\nV1 in 0 PULSE(0 1 0 1n 1n 1 2)\nR1 in a 10\nL1 a b 10m\nC1 b 0 100n\n.tran 2u 2m\n"
    alpha, wd = 10 / (2 * 10e-3), math.sqrt(1 / (10e-3 * 100e-9) - (10 / (2 * 10e-3)) ** 2)

    def exact(t):
        t = t - 0.5e-9
        return 1 - np.exp(-alpha * t) * (np.cos(wd * t) + alpha / wd * np.sin(wd * t))

    errs, counts = [], []
    for rtol in (1e-3, 1e-4, 1e-5):
        r = tran(parse(net), adaptive=StepControl(rtol=rtol))
        errs.append(np.abs(r.voltages["b"] - exact(r.time)).max())
        counts.append(len(r.time))
    assert errs[0] > errs[1] > errs[2] and counts[0] < counts[1] < counts[2]
    # global error is the per-step error accumulated over ~10 periods; it falls roughly as rtol^(2/3)
    # observed 3.9e-2, 9.2e-3, 2.2e-3 (about 20x less error for 100x less rtol)
    assert errs[1] < 2e-2 and errs[2] < 5e-3


def test_stiff_circuit_uses_far_fewer_steps_than_a_fixed_step_that_is_still_less_accurate():
    # tau = 1 us and 10 ms on one 1 ns-edge source over 50 ms. Observed: adaptive 191 steps, error 5e-4;
    # a fixed grid of 5000 steps (10 us, 26x more) has error 0.17, and no fixed step below 5e5 steps reaches 5e-2.
    c = parse((EXAMPLES / "stiff_adaptive.cir").read_text())

    def err(r):
        t = r.time - 0.5e-9
        return max(np.abs(r.voltages["fast"] - (1 - np.exp(-t / 1e-6))).max(),
                   np.abs(r.voltages["slow"] - (1 - np.exp(-t / 1e-2))).max())

    a = tran(c)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the 10 us fixed step is deliberately too coarse for the 1 ns edge
        f = tran(c, TranSpec(10e-6, 50e-3), adaptive=False)
    assert len(a.time) < 250 and err(a) < 1e-3
    assert len(f.time) > 20 * len(a.time) and err(f) > 50 * err(a)


def test_linear_matrices_are_reused_across_steps(monkeypatch):
    calls = []
    real = tran_module.lu_factor
    monkeypatch.setattr(tran_module, "lu_factor", lambda A: calls.append(1) or real(A))
    r = tran(parse((EXAMPLES / "stiff_adaptive.cir").read_text()))
    assert len(calls) < len(r.time) / 2  # step sizes are hmax / 2^k, so each factorisation serves many steps


def test_adaptive_with_diodes_matches_a_fine_fixed_step_run():
    c = parse((EXAMPLES / "diode_rectifier_tran.cir").read_text())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        a = tran(c, adaptive=True)
        f = tran(c, adaptive=False)
    peak = np.abs(f.voltages["out"]).max()
    out = np.interp(f.time, a.time, a.voltages["out"])  # Newton ran at every adaptive step too
    assert np.abs(out - f.voltages["out"]).max() <= 2e-2 * peak  # observed ~5e-3 (linear interpolation of a coarse grid)
    assert a.iterations.max() >= 1


# ---- breakpoints -------------------------------------------------------------------------------

def test_every_pulse_corner_is_a_time_point_exactly():
    net = "t\nV1 in 0 PULSE(0 1 1m 0.1m 0.2m 1m 3m)\nR1 in out 1k\nC1 out 0 1u\n.tran 5u 9m\n"
    c = parse(net)
    r = tran(c, adaptive=True)
    for corner in breakpoints(c, 9e-3):
        assert corner in r.time  # exact equality, not approx: the controller lands on it
    assert r.time[-1] == 9e-3 and np.all(np.diff(r.time) > 0)
    assert np.diff(r.time).max() <= 9e-3 / 50 * (1 + 1e-12)  # hmax


def test_steps_never_straddle_an_edge():
    c = parse("t\nV1 in 0 PULSE(0 1 1m 0.1m 0.1m 1m 5m)\nR1 in out 1k\nC1 out 0 1u\n.tran 5u 3m\n")
    r = tran(c, adaptive=True)
    t = r.time
    for edge in (1e-3, 1.1e-3, 2.1e-3, 2.2e-3):
        k = np.searchsorted(t, edge)
        assert t[k] == pytest.approx(edge, abs=1e-15)  # a time point sits on every corner, so no step crosses one


# ---- guards -----------------------------------------------------------------------------------

def test_hmin_guard_gives_a_clear_error():
    with pytest.raises(ConvergenceError, match=r"fell below hmin = 0.0005 s at t = .*loosen rtol or lower hmin"):
        tran(parse(RC), adaptive=StepControl(rtol=1e-12, vabs=1e-15, iabs=1e-15, hmin=5e-4))


def test_max_steps_guard_gives_a_clear_error():
    with pytest.raises(ConvergenceError, match=r"more than max_steps = 20 accepted steps \(reached t = .*of 0.005 s\)"):
        tran(parse(RC), adaptive=StepControl(max_steps=20))


# ---- fixed-step behaviour is unchanged ----------------------------------------------------------

def test_fixed_step_is_still_the_default_and_adaptive_false_overrides_the_option():
    c = parse(RC)
    fixed = tran(c)
    assert len(fixed.time) == 5001 and np.allclose(np.diff(fixed.time), 1e-6) and fixed.rejected == 0
    c2 = parse(RC.replace(".tran", ".options step=adaptive\n.tran"))
    assert len(tran(c2).time) < 200  # the option turns it on ...
    assert np.array_equal(tran(c2, adaptive=False).voltages["out"], fixed.voltages["out"])  # ... a kwarg turns it off


def test_adaptive_run_does_not_disturb_a_following_fixed_run():
    c = parse(RC)
    before = tran(c).voltages["out"].copy()
    tran(c, adaptive=True)
    assert np.array_equal(tran(c).voltages["out"], before)


# ---- initial conditions (UIC) -----------------------------------------------------------------

def test_rc_ic_discharge_matches_the_analytic_exponential():
    c = parse((EXAMPLES / "rc_ic_discharge.cir").read_text())
    assert c.tran.uic and c.ic == {"out": 5.0}
    for adaptive, tol in ((False, 5e-5), (True, 5e-4)):
        r = tran(c, adaptive=adaptive)
        assert r.voltages["out"][0] == 5.0  # starts exactly at the initial condition, no DC solve
        assert np.abs(r.voltages["out"] - 5 * np.exp(-r.time / 1e-3)).max() <= tol * 5  # fraction of the 5 V start


def test_ic_on_a_capacitor_only_loop_is_accepted():
    # the Milestone 4 limitation: no DC path to ground (C alone across a source-free loop) was rejected without UIC
    c = parse("t\nC1 a b 1u\nC2 b 0 1u\nR1 a 0 1k\n.ic v(a)=2\n.tran 10u 2m uic\n")
    r = tran(c, adaptive=True)
    assert r.voltages["a"][0] == 2.0 and abs(r.voltages["a"][-1]) < 0.5  # a discharges through R1


# ---- ngspice ----------------------------------------------------------------------------------

@needs_ngspice
def test_stiff_adaptive_matches_ngspice():
    # ngspice needs tmax = 10 us here: the default tstep / 10 = 0.1 ns would be 5e8 points. Observed worst 3.3e-4
    # of peak (v(fast)) at the default rtol 1e-4; tolerance 1.5e-3 (adaptive accuracy is per-step, so it is
    # looser than the fixed-step 1e-5 rows).
    text = (EXAMPLES / "stiff_adaptive.cir").read_text()
    mine, ref = tran(parse(text)), run_tran(text, tmax_fraction=1e4)
    for kind in ("voltages", "currents"):
        for k, a in getattr(mine, kind).items():
            b = np.interp(mine.time, ref.time, getattr(ref, kind)[k])
            assert np.abs(a - b).max() <= 1.5e-3 * max(np.abs(b).max(), 1e-12), k
