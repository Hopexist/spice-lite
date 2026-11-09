"""Milestone 6: diodes in .tran (Newton per step, step halving), diodes in .ac (small signal),
and .ic / UIC with consistent initial conditions."""
import math
import warnings
from dataclasses import replace
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

from spicelite import NetlistError, SingularCircuitError, TranSpec, parse
from spicelite.analysis.ac import ac
from spicelite.analysis.dc import op
from spicelite.analysis.tran import ResolutionWarning, tran
from spicelite.circuit import ConvergenceError, DiodeModel
from spicelite.elements import diode_iv
from test_diode import lambert, net

EXAMPLES = Path(__file__).parent.parent / "examples"


def example(name: str):
    return parse((EXAMPLES / f"{name}.cir").read_text())


# ---- parsing: .ic and uic ----
def test_tran_uic_flag():
    assert parse("t\n.tran 1u 1m uic\n.end").tran == TranSpec(1e-6, 1e-3, True)
    assert parse("t\n.tran 1u 1m UIC\n.end").tran.uic and not parse("t\n.tran 1u 1m\n.end").tran.uic


@pytest.mark.parametrize("line", [".tran 1u 1m foo", ".tran 1u 1m uic 5", ".tran 1u uic"])
def test_bad_tran_uic_lines(line):
    with pytest.raises(NetlistError):
        parse(f"t\nR1 a 0 1\n{line}\n.end")


def test_ic_forms():
    c = parse("t\nC1 a b 1u\nR1 b 0 1\nR2 a 0 1\n.IC V(A)=1.5 v(b) = -2m\n.end")
    assert c.ic == {"a": 1.5, "b": -2e-3}


@pytest.mark.parametrize("line", [
    ".ic", ".ic a=1", ".ic v(a)", ".ic v(a)=abc", ".ic v(0)=1", ".ic v(a)=1 v(a)=2",
    ".ic i(l1)=1", ".ic v(zzz)=1",                      # unknown node
])
def test_bad_ic_lines(line):
    with pytest.raises(NetlistError) as e:
        parse(f"t\nC1 a 0 1u\nR1 a 0 1\n{line}\n.end")
    assert e.value.line == 4


def test_ic_without_uic_is_an_error_not_silently_ignored():
    with pytest.raises(NetlistError, match="uic") as e:
        parse("t\nC1 a 0 1u\nR1 a 0 1\n.ic v(a)=1\n.tran 1u 1m\n.end")
    assert e.value.line == 4
    c = parse("t\nC1 a 0 1u\nR1 a 0 1\n.ic v(a)=1\n.end")  # no .tran at all: fine
    with pytest.raises(ValueError, match="uic"):  # and the API says the same
        tran(c, TranSpec(1e-6, 1e-5))


def test_ic_on_a_node_without_a_capacitor_is_rejected():
    c = parse("t\nC1 a 0 1u\nR1 a b 1k\nR2 b 0 1k\n.ic v(b)=1\n.tran 1u 10u uic\n.end")
    with pytest.raises(ValueError, match="no capacitor touches"):
        tran(c)


# ---- UIC against analytic solutions ----
def rc_discharge(h, method):
    c = parse(f"t\nR1 out 0 1k\nC1 out 0 1u\n.ic v(out)=5\n.tran {h!r} 5m uic\n.end")
    r = tran(c, method=method)
    return np.abs(r.voltages["out"] - 5 * np.exp(-r.time / 1e-3)).max(), r


@pytest.mark.parametrize("method,tol", [
    # tau = 1 ms, h = 10 us. Measured: BE 8.8e-3 (first order), trapezoidal 1.5e-5; tolerances ~2x.
    ("be", 1.8e-2), ("trap", 3e-5),
])
def test_rc_discharge_from_ic(method, tol):
    err, r = rc_discharge(1e-5, method)
    assert err < tol and r.voltages["out"][0] == 5.0  # t = 0 shows the .ic value, no DC solve


def test_uic_convergence_orders_are_2_and_4_again():
    be = np.array([rc_discharge(1e-4 / 2**k, "be")[0] for k in range(6)])
    trap = np.array([rc_discharge(1e-4 / 2**k, "trap")[0] for k in range(6)])
    assert np.allclose(be[:-1] / be[1:], 2, atol=0.1), be[:-1] / be[1:]
    assert np.allclose(trap[:-1] / trap[1:], 4, atol=0.1), trap[:-1] / trap[1:]


def test_rlc_ringdown_from_ic_matches_the_damped_cosine():
    alpha, wd = 5000.0, math.sqrt(1e9 - 5000.0**2)  # R/2L and sqrt(1/LC - alpha^2)
    r = tran(parse("t\nC1 a 0 1u\nL1 a b 1m\nR1 b 0 10\n.ic v(a)=1\n.tran 1u 1m uic\n.end"))
    t = r.time
    v_a = np.exp(-alpha * t) * (np.cos(wd * t) + alpha / wd * np.sin(wd * t))
    i_l = np.exp(-alpha * t) * np.sin(wd * t) / (wd * 1e-3)  # starts at 0: UIC sets inductor current 0
    # measured trapezoidal errors at h = 1 us (~200 steps per ring period): 1.9e-4 V and 6.2e-6 A
    assert np.abs(r.voltages["a"] - v_a).max() < 5e-4
    assert np.abs(r.currents["l1"] - i_l).max() < 2e-5
    assert r.currents["l1"][0] == 0.0


def test_uic_first_sample_keeps_ic_and_a_stepping_source_appears_after_t0():
    c = parse("t\nV1 in 0 PULSE(0 1 0 0 0 1 10)\nR1 in out 1k\nC1 out 0 1u\n.ic v(out)=0.5\n.tran 1u 1m uic\n.end")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResolutionWarning)
        r = tran(c)
    assert r.voltages["out"][0] == 0.5 and r.voltages["in"][0] == 0.0 and r.voltages["in"][1] == 1.0
    assert np.all(np.diff(r.voltages["out"][:50]) > 0)  # charging up from 0.5 V toward 1 V


def test_source_across_capacitor_falls_back_to_zero_histories_and_still_runs():
    # A cap directly across an ideal source has no t = 0+ capacitor current (shortcut in tran()).
    r = tran(parse("t\nV1 a 0 SIN(0 1 1k)\nC1 a 0 1u\nR1 a 0 1k\n.tran 10u 1m\n.end"))
    assert np.allclose(r.voltages["a"], np.sin(2 * np.pi * 1e3 * r.time), atol=1e-12)


# ---- diodes in .tran ----
def test_memoryless_diode_circuit_equals_the_dc_solution_at_every_time_point():
    """With no C or L, every time point is just a DC solve at the source's value then."""
    c = parse(net("V1 in 0 SIN(0 5 1k)\nR1 in out 1k\nD1 out 0 dm\nD2 0 out dm",
                  tail=".tran 20u 1m"))
    for method in ("trap", "be"):
        r = tran(c, method=method)
        for k in range(0, len(r.time), 7):
            static = replace(c, elements=[replace(e, dc=e.at(r.time[k]), tran=None) if e.name == "v1" else e
                                          for e in c.elements])
            assert r.voltages["out"][k] == pytest.approx(op(static).voltages["out"], abs=1e-8)


def test_half_wave_rectifier_physics():
    r = tran(example("diode_rectifier_tran"))
    out, t = r.voltages["out"], r.time
    late = t > 3e-3  # the last two periods, after the first charge-up
    assert 4.15 < out.max() < 4.35                       # peak = 5 V - one diode drop (+ the 1 ohm RS)
    assert out.min() >= -1e-6                            # the diode blocks the negative half cycle
    ripple = out[late].max() - out[late].min()
    # I_load (~4 mA) discharging 10 uF for most of a 1 ms period: ~I T / C = 0.4 V, a little less
    # because the diode conducts for part of each cycle; measured 0.367 V.
    assert 0.30 < ripple < 0.45
    assert "d1#int" not in r.voltages and set(r.voltages) == {"in", "out"}   # hidden RS node


# Observed worst Newton iterations per step: rectifier 6, clamp 7 (limits leave ~3 of margin).
@pytest.mark.parametrize("name,limit", [("diode_rectifier_tran", 9), ("diode_clamp_tran", 10)])
def test_newton_iterations_per_step_stay_bounded(name, limit):
    r = tran(example(name))
    assert r.iterations.max() <= limit and r.cuts == 0


def test_linear_circuits_never_run_newton():
    with mock.patch("spicelite.analysis.tran._newton") as newton:
        r = tran(example("rc_step"))
    newton.assert_not_called()
    assert (r.iterations == 0).all() and r.cuts == 0


COARSE = (EXAMPLES / "diode_rectifier_tran.cir").read_text().replace(".tran 2u 5m", ".tran 25u 5m")


def test_step_halving_rescues_a_step_newton_cannot_converge_in_time():
    c = parse(COARSE)  # 25 us steps: the first diode turn-on needs 6 iterations
    # Cap every Newton run at 5 iterations. With no halving allowed it fails, and says when ...
    with pytest.raises(ConvergenceError, match=r"t = 2\.5e-05 s.*worst unknown is \S+") as e:
        tran(c, max_iter=5, max_cuts=0)
    assert e.value.worst_node
    # ... with halving allowed the SAME cap succeeds, and the result records that it was used.
    cut = tran(c, max_iter=5)
    free = tran(c)  # uncapped, never halves
    assert cut.cuts > 0 and free.cuts == 0
    # Halved steps are finer than 25 us, so they land closer to a fine-step reference.
    fine = tran(parse(COARSE.replace(".tran 25u 5m", ".tran 5u 5m")))
    ref = np.interp(free.time, fine.time, fine.voltages["out"])
    assert np.abs(cut.voltages["out"] - ref).max() < np.abs(free.voltages["out"] - ref).max()


def test_halving_is_bounded_and_the_error_says_how_far_it_got():
    # with a 2-iteration cap even one halving cannot help, so the failure surfaces
    with pytest.raises(ConvergenceError, match=r"after halving the step 1 times"):
        tran(parse(COARSE), max_iter=2, max_cuts=1)


def test_diode_dc_start_is_the_initial_state():
    # A DC-biased diode circuit with a constant source must not move at all.
    c = parse(net("V1 in 0 5\nR1 in a 1k\nD1 a b dm\nC1 b 0 1u\nR2 b 0 10k", tail=".tran 5u 100u"))
    r = tran(c)
    assert np.allclose(r.voltages["b"], r.voltages["b"][0], rtol=1e-9)
    assert r.voltages["b"][0] == pytest.approx(op(c).voltages["b"], rel=1e-12)


# ---- diodes in .ac: small signal about the DC operating point ----
def gain_formula(vs, r, f, c_f=0.0, IS=1e-14, N=1.0, RS=0.0):
    """1 V AC source -> R -> (RS + diode conductance g) || C. g is taken at the EXACT bias (Lambert W)."""
    i_src, va = lambert(vs, r, IS, N, RS)
    vd = va - i_src * RS  # junction voltage, after the RS drop
    g = diode_iv(DiodeModel("m", IS=IS, N=N), vd)[1]
    y = 1 / (RS + 1 / g) + 2j * np.pi * f * c_f
    return (1 / y) / (r + 1 / y)


def test_ac_gain_of_a_biased_diode_is_the_divider_with_its_small_signal_resistance():
    c = parse(net("V1 in 0 DC 5 AC 1\nR1 in a 1k\nD1 a 0 dm", tail=".ac dec 1 10 1k"))
    r = ac(c)
    expect = np.array([gain_formula(5, 1e3, f) for f in r.freqs])
    assert np.allclose(r.voltages["a"], expect, rtol=1e-9)
    assert abs(r.voltages["a"][0]) == pytest.approx(0.00597, rel=2e-3)  # rd = N Vt / Id ~ 6 ohm


def test_ac_diode_with_capacitor_and_series_resistance():
    c = parse(net("V1 in 0 DC 5 AC 1\nR1 in a 1k\nD1 a 0 dm\nC1 a 0 100n",
                  model=".model dm D(IS=1e-14 N=1 RS=10)", tail=".ac dec 10 10 10meg"))
    r = ac(c)
    # the capacitor sits across the diode AND its series resistance (node a), as in gain_formula
    expect = np.array([gain_formula(5, 1e3, f, 100e-9, RS=10.0) for f in r.freqs])
    assert np.allclose(r.voltages["a"], expect, rtol=1e-9)
    assert set(r.voltages) == {"in", "a"}  # hidden RS node left out


def test_ac_of_a_diode_circuit_reports_a_source_loop():
    with pytest.raises(SingularCircuitError, match="loop of voltage sources"):
        ac(parse(net("V1 a 0 AC 1\nV2 a 0 AC 1\nD1 a 0 dm", tail=".ac dec 1 1 10")))
