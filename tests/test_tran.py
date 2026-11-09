import math
import warnings

import numpy as np
import pytest

from spicelite import NetlistError, Pulse, Sin, SingularCircuitError, TranSpec, parse
from spicelite.analysis.tran import ResolutionWarning, tran

TAU = 1e-3  # R C = 1 kohm * 1 uF, and L/R = 1 H / 1 kohm


def ramp_step(t, tr, tau=TAU):
    """Exact unit-gain first-order response (tau y' + y = u) to u = a ramp 0 -> 1 over tr, then 1.
    Exact for both the RC voltage and the RL current. The ramp keeps the input continuous,
    which trapezoidal needs in order to show its second-order accuracy."""
    t = np.asarray(t, dtype=float)
    y = lambda x: (x - tau * (1 - np.exp(-x / tau))) / tr  # noqa: E731  (response during the ramp)
    return np.where(t <= tr, y(np.minimum(t, tr)), 1 + (y(tr) - 1) * np.exp(-(t - tr) / tau))


def rc_net(h, tr=0.5e-3, tstop=4e-3, source="V1 in 0 PULSE(0 1 0 {tr!r} 1m 1 10)"):
    return (f"t\n{source.format(tr=tr)}\nR1 in out 1k\nC1 out 0 1u\n.tran {h!r} {tstop!r}\n.end")


# ---- parsing ----
def test_tran_directive():
    assert parse("t\n.tran 10u 5m\n.end").tran == TranSpec(1e-5, 5e-3)


@pytest.mark.parametrize("line", [
    ".tran 1u", ".tran 1u 1m 0 1u", ".tran 0 1m", ".tran -1u 1m", ".tran 1m 1u", ".tran x 1m",
])
def test_bad_tran_lines(line):
    with pytest.raises(NetlistError) as e:
        parse(f"t\nR1 a 0 1\n{line}\n.end")
    assert e.value.line == 3


def test_duplicate_tran():
    with pytest.raises(NetlistError, match="duplicate .tran"):
        parse("t\n.tran 1u 1m\n.tran 1u 1m\n.end")


def test_method_option():
    assert parse("t\n.end").method == "trap"
    assert parse("t\n.options method=be\n.end").method == "be"
    assert parse("t\n.OPTION METHOD = TRAP\n.end").method == "trap"


@pytest.mark.parametrize("opt", [".options method=gear", ".options reltol=1e-6", ".options"])
def test_bad_options(opt):
    with pytest.raises(NetlistError, match="unsupported option"):
        parse(f"t\n{opt}\n.end")


def test_pulse_and_sin_parse():
    v = parse("t\nV1 a 0 PULSE(0 1 0 1n 1n 5u 10u)\nI1 0 a SIN(0 2 1k 1m 5)\n.end").elements
    assert v[0].tran == Pulse(0, 1, 0, 1e-9, 1e-9, 5e-6, 1e-5) and v[0].dc == 0
    assert v[1].tran == Sin(0, 2, 1e3, 1e-3, 5)
    assert parse("t\nV1 a 0 SIN(0 1 1k)\n.end").elements[0].tran == Sin(0, 1, 1e3)


def test_waveform_with_commas_and_dc_and_ac():
    e = parse("t\nV1 a 0 DC 2 AC 1 PULSE(0,1,0,1u,1u,1m,2m)\n.end").elements[0]
    assert e.dc == 2 and e.ac == 1 and e.tran == Pulse(0, 1, 0, 1e-6, 1e-6, 1e-3, 2e-3)


@pytest.mark.parametrize("spec", [
    "PULSE(0 1 0 1n 1n 5u)",          # needs all 7 values
    "PULSE(0 1 0 1n 1n 5u 1u)",       # period shorter than tr + pw + tf
    "PULSE(0 1 -1 1n 1n 5u 10u)",     # negative delay
    "SIN(0 1)",                       # too few
    "SIN(0 1 1k 0 0 0)",              # too many
    "SIN(0 1 0)",                     # zero frequency
    "SIN(0 1 xyz)",                   # bad number
    "SIN(0 1 1k) SIN(0 1 2k)",        # two waveforms
])
def test_bad_waveforms(spec):
    with pytest.raises(NetlistError) as e:
        parse(f"t\nR1 a 0 1\nV1 a 0 {spec}\n.end")
    assert e.value.line == 3


def test_pulse_values_hand_computed():
    p = Pulse(v1=0, v2=5, td=1, tr=2, tf=2, pw=3, per=10)
    #            before td | start | mid-rise | top | flat | mid-fall | after | next period
    cases = {0: 0, 1: 0, 2: 2.5, 3: 5, 5.5: 5, 7: 2.5, 8: 0, 11: 0, 12: 2.5}
    for t, v in cases.items():
        assert p.value(t) == pytest.approx(v), t


def test_zero_rise_pulse_starts_at_v1_then_jumps():
    p = Pulse(0, 1, 0, 0, 0, 1, 2)
    assert p.value(0) == 0 and p.value(1e-12) == 1 and p.value(1.5) == 0


def test_sin_values():
    s = Sin(1, 2, 1, td=0.5)
    assert s.value(0.25) == 1 and s.value(0.75) == pytest.approx(3)
    assert Sin(0, 1, 1, 0, 2).value(0.25) == pytest.approx(math.exp(-0.5))


# ---- accuracy against analytic solutions ----
@pytest.mark.parametrize("method,tol", [
    # RC, tau = 1 ms, ramp rise 0.5 ms, h = 10 us. Expected error ~ h/tau scale for BE
    # (first order, measured ~2.8e-3) and ~(h/tau)^2 for trapezoidal (measured ~5e-6).
    ("be", 5e-3), ("trap", 2e-5),
])
def test_rc_response(method, tol):
    r = tran(parse(rc_net(1e-5)), method=method)
    assert np.abs(r.voltages["out"] - ramp_step(r.time, 0.5e-3)).max() < tol


@pytest.mark.parametrize("method,tol", [("be", 5e-6), ("trap", 2e-8)])  # RC tolerances / 1 kohm
def test_rl_current_rise(method, tol):
    net = "t\nV1 in 0 PULSE(0 1 0 0.5m 1m 1 10)\nR1 in out 1k\nL1 out 0 1\n.tran 10u 4m\n.end"
    r = tran(parse(net), method=method)
    assert np.abs(r.currents["l1"] - ramp_step(r.time, 0.5e-3) / 1e3).max() < tol


def test_current_source_into_rc():
    # 1 mA ramp-step into R || C: v = R I_max * unit response, same math as the RC voltage.
    net = "t\nI1 0 a PULSE(0 1m 0 0.5m 1m 1 10)\nR1 a 0 1k\nC1 a 0 1u\n.tran 10u 4m\n.end"
    r = tran(parse(net), method="trap")
    assert np.abs(r.voltages["a"] - ramp_step(r.time, 0.5e-3)).max() < 2e-5


def test_underdamped_rlc_overshoot_and_ringing_period():
    net = ("t\nV1 in 0 PULSE(0 1 0 1u 1u 5m 10m)\nR1 in a 10\nL1 a out 1m\nC1 out 0 1u\n"
           ".tran 1u 1m\n.end")
    r = tran(parse(net))
    zeta = 5 * math.sqrt(1e-6 / 1e-3)  # (R/2) sqrt(C/L)
    wd = math.sqrt(1 / (1e-3 * 1e-6)) * math.sqrt(1 - zeta**2)
    peak = 1 + math.exp(-math.pi * zeta / math.sqrt(1 - zeta**2))
    v = r.voltages["out"]
    assert v.max() == pytest.approx(peak, rel=5e-3)
    # peak time is pi/wd after the step; the 1 us ramp delays the step's centre by 0.5 us
    assert r.time[v.argmax()] == pytest.approx(math.pi / wd + 0.5e-6, abs=2e-6)


def test_dc_state_is_a_fixed_point():
    # Capacitors open, inductors short at t = 0: nothing should move with constant sources.
    net = "t\nV1 in 0 5\nR1 in a 1k\nL1 a b 1m\nR2 b 0 1k\nC1 b 0 1u\n.tran 1u 100u\n.end"
    for method in ("be", "trap"):
        r = tran(parse(net), method=method)
        assert np.allclose(r.voltages["b"], 2.5, rtol=1e-12) and np.allclose(r.currents["l1"], 2.5e-3, rtol=1e-12)


def test_resistive_divider_follows_sine_exactly():
    r = tran(parse("t\nV1 in 0 SIN(0 2 1k)\nR1 in out 1k\nR2 out 0 1k\n.tran 10u 1m\n.end"))
    assert np.allclose(r.voltages["out"], np.sin(2 * np.pi * 1e3 * r.time), rtol=1e-9, atol=1e-12)


# ---- convergence order ----
def max_errors(method, ks, tr=0.5e-3, ideal=False):
    errs = []
    for k in ks:
        h = tr / 2**k
        if ideal:
            c = parse(rc_net(h, source="V1 in 0 PULSE(0 1 0 0 0 1 10)"))
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResolutionWarning)
                r = tran(c, method=method)
            exact = 1 - np.exp(-r.time / TAU)
        else:
            r = tran(parse(rc_net(h, tr)), method=method)
            exact = ramp_step(r.time, tr)
        errs.append(np.abs(r.voltages["out"] - exact).max())
    return np.array(errs)


def test_convergence_order_halving_h():
    """Halving h should cut the error ~2x for BE (order 1) and ~4x for trapezoidal (order 2).
    The ramp edge ends on a grid point for every h, so the kink doesn't pollute the order."""
    ks = range(2, 8)  # h = tr/4 ... tr/128
    be, trap = max_errors("be", ks), max_errors("trap", ks)
    assert np.allclose(be[:-1] / be[1:], 2, atol=0.15), be[:-1] / be[1:]
    assert np.allclose(trap[:-1] / trap[1:], 4, atol=0.2), trap[:-1] / trap[1:]


def test_trapezoidal_is_only_first_order_for_an_ideal_step():
    """Observed, and worth knowing: with a zero-rise step the trapezoid rule averages the
    capacitor current before the step (0) with the one after (V/R), so the first step is
    off by O(h) and trapezoidal degrades to first order -- slightly WORSE than BE here."""
    trap = max_errors("trap", range(2, 8), ideal=True)
    assert np.allclose(trap[:-1] / trap[1:], 2, atol=0.2), trap[:-1] / trap[1:]


# ---- trapezoidal ringing vs backward Euler damping ----
def test_trap_rings_and_be_does_not_for_large_steps():
    h = 20e-6  # tau = R C = 1 kohm * 1 nF = 1 us, so h = 20 tau
    net = (f"t\nV1 in 0 PULSE(0 1 0 0 0 {5 * h * (1 - 1e-9)!r} 1)\nR1 in out 1k\nC1 out 0 1n\n"
           f".tran {h!r} {15 * h!r}\n.end")
    with pytest.warns(ResolutionWarning):
        trap = tran(parse(net), method="trap").voltages["out"]
    with pytest.warns(ResolutionWarning):
        be = tran(parse(net), method="be").voltages["out"]
    assert trap.max() > 1.05  # true answer never exceeds 1 V
    assert trap[2:5].min() < 0.95  # ...and then swings back below
    # BE rises monotonically toward 1 V (points 0..4 are before the falling edge at t = 5h)
    assert be.max() <= 1 and (np.diff(be[:5]) >= 0).all()


# ---- warnings, options, edge cases ----
def test_warns_when_step_exceeds_pulse_edge():
    net = "t\nV1 a 0 PULSE(0 1 0 1u 1u 1m 2m)\nR1 a 0 1k\n.tran 10u 1m\n.end"
    with pytest.warns(ResolutionWarning, match="under-resolved"):
        tran(parse(net))


def test_no_warning_when_step_equals_or_is_below_edge():
    net = "t\nV1 a 0 PULSE(0 1 0 10u 10u 1m 2m)\nR1 a 0 1k\n.tran 10u 1m\n.end"  # h == tr
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        tran(parse(net))


def test_options_method_is_the_default_and_the_argument_overrides_it():
    net = rc_net(1e-4)
    c = parse(net.replace(".end", ".options method=be\n.end"))
    assert np.array_equal(tran(c).voltages["out"], tran(c, method="be").voltages["out"])
    assert not np.array_equal(tran(c).voltages["out"], tran(c, method="trap").voltages["out"])
    assert np.array_equal(tran(parse(net)).voltages["out"], tran(parse(net), method="trap").voltages["out"])


def test_bad_method_and_missing_directive():
    with pytest.raises(ValueError, match="method"):
        tran(parse(rc_net(1e-4)), method="gear")
    with pytest.raises(ValueError, match="no .tran"):
        tran(parse("t\nV1 a 0 1\nR1 a 0 1\n.end"))


def test_step_is_adjusted_to_divide_tstop():
    r = tran(parse("t\nV1 a 0 1\nR1 a 0 1\n.tran 3 10\n.end"))
    assert len(r.time) == 5 and r.time[-1] == pytest.approx(10) and r.time[1] == pytest.approx(2.5)


def test_capacitor_only_node_has_no_initial_dc_state():
    with pytest.raises(SingularCircuitError, match="no DC path"):
        tran(parse("t\nV1 a 0 5\nC1 a b 1u\nC2 b 0 1u\n.tran 1u 10u\n.end"))
