"""Milestone 5: controlled sources E (VCVS), G (VCCS), F (CCCS), H (CCVS) and the op-amp."""
import math
import warnings
from dataclasses import replace
from pathlib import Path
from unittest import mock

import numpy as np
import pytest
from scipy.linalg import lu_factor

from spicelite import (
    CCCS,
    CCVS,
    OPAMP_GAIN,
    VCCS,
    VCVS,
    AcSweep,
    NetlistError,
    OpenLoopWarning,
    Pulse,
    SingularCircuitError,
    opamp,
    parse,
)
from spicelite.analysis.ac import ac, magnitude_db, phase_degrees
from spicelite.analysis.dc import dc_sweep, op
from spicelite.analysis.tran import tran
from spicelite.elements import stamp_cccs, stamp_ccvs, stamp_vccs, stamp_vcvs
from spicelite.ngspice import find_ngspice, run_op
from test_tran import ramp_step

EXAMPLES = Path(__file__).parent.parent / "examples"
needs_ngspice = pytest.mark.skipif(
    find_ngspice() is None,
    reason="ngspice not found: put ngspice_con.exe/ngspice.exe on PATH or set NGSPICE=<path to exe>")


def example_text(name: str) -> str:
    return (EXAMPLES / f"{name}.cir").read_text()


def solve(body: str):
    return op(parse("title\n" + body + "\n.end"))


# ---- parsing ----
def test_all_four_parse_into_their_dataclasses_case_insensitively():
    c = parse("t\nV1 in 0 1\nVs m 0 0\nR1 in m 1k\nE1 e 0 in 0 5\nG1 g 0 IN 0 2m\nF1 f 0 VS 10\nH1 h 0 vs 2K\n.end")
    e, g, f, h = c.elements[3:]
    assert e == VCVS("e1", "e", "0", "in", "0", 5.0)
    assert g == VCCS("g1", "g", "0", "in", "0", 2e-3)
    assert f == CCCS("f1", "f", "0", "vs", 10.0)
    assert h == CCVS("h1", "h", "0", "vs", 2000.0)
    # E and H need a branch-current unknown, G and F do not; control nodes are circuit nodes
    assert [b.name for b in c.branch_elements()] == ["v1", "vs", "e1", "h1"]
    assert "in" in c.node_index()


NET = "t\nV1 a 0 1\nR1 a b 1k\nL1 b 0 1m\nE9 e 0 a 0 2\nVs m 0 0\n{line}\n.end"  # the line under test is line 7


@pytest.mark.parametrize("line", [
    "E1 a 0 b 0", "E1 a 0 b 0 2 3", "G1 a 0 b 2m", "G1 a 0 b 0 2m 1",   # wrong field counts
    "F1 a 0 Vs", "F1 a 0 Vs 2 3", "F1 a 0 10", "H1 a 0 Vs", "H1 a 0 Vs 2 3", "H1 a 0",
])
def test_wrong_field_counts_are_line_numbered(line):
    with pytest.raises(NetlistError, match="needs exactly") as e:
        parse(NET.format(line=line))
    assert e.value.line == 7


@pytest.mark.parametrize("line", ["E1 a 0 b 0 abc", "G1 a 0 b 0 x", "F1 a 0 Vs two", "H1 a 0 Vs 1kohm"])
def test_nonnumeric_gains(line):
    with pytest.raises(NetlistError, match="bad value") as e:
        parse(NET.format(line=line))
    assert e.value.line == 7


@pytest.mark.parametrize("line,msg", [
    ("F1 a 0 Vnone 2", "not in the circuit"),                 # unknown sense source
    ("H1 a 0 R1 2", "not a voltage source"),                  # a resistor
    ("F1 a 0 L1 2", "not a voltage source"),                  # an inductor: only V sources can be sensed
    ("F1 a 0 E9 2", "not a voltage source"),                  # a controlled source
    ("H1 a 0 H1 2", "cannot sense its own current"),          # a source controlling itself
    ("F1 a 0 F1 2", "cannot sense its own current"),
])
def test_sense_source_errors_are_reported_at_the_element_line(line, msg):
    with pytest.raises(NetlistError, match=msg) as e:
        parse(NET.format(line=line))
    assert e.value.line == 7


def test_sense_source_may_be_defined_after_its_user():
    c = parse("t\nF1 out 0 Vs 10\nRo out 0 1k\nV1 in 0 1\nR1 in m 1k\nVs m 0 0\n.end")
    assert op(c).voltages["out"] == pytest.approx(-10.0, rel=1e-12)


# ---- the stamps, hand-computed ----
def test_stamp_vcvs():
    A = np.zeros((4, 4))
    stamp_vcvs(A, {"o": 0, "cp": 1, "cm": 2}, 3, VCVS("e1", "o", "0", "cp", "cm", 5.0))
    want = np.zeros((4, 4))
    want[0, 3] = want[3, 0] = 1  # output node column / constraint row
    want[3, 1], want[3, 2] = -5, +5  # -gain on nc+, +gain on nc-
    assert np.array_equal(A, want)


def test_stamp_vcvs_with_a_floating_output_pair():
    A = np.zeros((4, 4))
    stamp_vcvs(A, {"a": 0, "b": 1, "c": 2}, 3, VCVS("e1", "a", "b", "c", "0", 2.0))
    want = np.zeros((4, 4))
    want[0, 3] = want[3, 0] = 1
    want[1, 3] = want[3, 1] = -1
    want[3, 2] = -2
    assert np.array_equal(A, want)


def test_stamp_vccs():
    A = np.zeros((4, 4))
    stamp_vccs(A, {"a": 0, "b": 1, "c": 2, "d": 3}, VCCS("g1", "a", "b", "c", "d", 2e-3))
    want = np.zeros((4, 4))
    want[0, 2], want[0, 3], want[1, 2], want[1, 3] = 2e-3, -2e-3, -2e-3, 2e-3
    assert np.array_equal(A, want)


def test_stamp_vccs_to_ground_skips_ground_rows_and_columns():
    A = np.zeros((2, 2))
    stamp_vccs(A, {"o": 0, "c": 1}, VCCS("g1", "o", "0", "c", "0", 3.0))
    assert np.array_equal(A, [[0, 3.0], [0, 0]])


def test_stamp_cccs():
    A = np.zeros((3, 3))
    stamp_cccs(A, {"a": 0, "b": 1}, 2, CCCS("f1", "a", "b", "vs", 10.0))
    assert np.array_equal(A, [[0, 0, 10.0], [0, 0, -10.0], [0, 0, 0]])


def test_stamp_ccvs():
    A = np.zeros((4, 4))
    stamp_ccvs(A, {"a": 0, "b": 1}, 3, 2, CCVS("h1", "a", "b", "vs", 2000.0))
    want = np.zeros((4, 4))
    want[0, 3] = want[3, 0] = 1
    want[1, 3] = want[3, 1] = -1
    want[3, 2] = -2000.0
    assert np.array_equal(A, want)


# ---- analytic DC checks, one per source type ----
def test_vcvs_gain_and_differential_control():
    r = solve("V1 a 0 3\nV2 b 0 1\nE1 out 0 a b 5\nR1 out 0 1k")
    assert r.voltages["out"] == pytest.approx(5 * (3 - 1), rel=1e-12)
    assert r.currents["e1"] == pytest.approx(-10e-3, rel=1e-12)  # delivering 10 mA: negative (SPICE sign)
    assert r.currents["v1"] == 0 and r.currents["v2"] == 0        # the control input draws no current


def test_vccs_transconductance_and_current_direction():
    # G pushes gm*vin from n+ through the source to n-: with n+ = out it PULLS current out of the node
    assert solve("V1 in 0 1\nG1 out 0 in 0 2m\nR1 out 0 1k").voltages["out"] == pytest.approx(-2.0, rel=1e-12)
    assert solve("V1 in 0 1\nG1 0 out in 0 2m\nR1 out 0 1k").voltages["out"] == pytest.approx(+2.0, rel=1e-12)
    assert solve("V1 in 0 1\nG1 out 0 0 in 2m\nR1 out 0 1k").voltages["out"] == pytest.approx(+2.0, rel=1e-12)


def test_gm_between_the_same_nodes_is_a_resistor():
    # G across its own control nodes is a conductance gm: 1 V across it draws gm amps
    r = solve("V1 a 0 1\nG1 a 0 a 0 2m")
    assert r.currents["v1"] == pytest.approx(-2e-3, rel=1e-12)


def test_cccs_current_gain():
    r = solve("V1 in 0 2\nR1 in m 1k\nVs m 0 0\nF1 out 0 Vs 10\nR2 out 0 1k")
    assert r.currents["vs"] == pytest.approx(2e-3, rel=1e-12)       # 2 mA into Vs's + terminal
    assert r.voltages["out"] == pytest.approx(-10 * 2e-3 * 1e3, rel=1e-12)


def test_ccvs_transresistance():
    r = solve("V1 in 0 2\nR1 in m 1k\nVs m 0 0\nH1 out 0 Vs 2k\nR2 out 0 1k")
    assert r.voltages["out"] == pytest.approx(2e3 * 2e-3, rel=1e-12)
    assert r.currents["h1"] == pytest.approx(-4e-3, rel=1e-12)       # H delivers 4 V / 1k


def test_sense_current_sign_follows_the_source_orientation():
    """i(Vs) is positive when current enters Vs's + terminal (ngspice's convention). Reversing
    the source's terminals flips the sign of the sensed current, and so F's and H's outputs."""
    fwd = solve("V1 in 0 2\nR1 in m 1k\nVs m 0 0\nF1 out 0 Vs 10\nR2 out 0 1k\nH1 h 0 Vs 2k\nR3 h 0 1k")
    rev = solve("V1 in 0 2\nR1 in m 1k\nVs 0 m 0\nF1 out 0 Vs 10\nR2 out 0 1k\nH1 h 0 Vs 2k\nR3 h 0 1k")
    assert fwd.currents["vs"] == pytest.approx(+2e-3) and rev.currents["vs"] == pytest.approx(-2e-3)
    assert rev.voltages["out"] == pytest.approx(-fwd.voltages["out"], rel=1e-12)
    assert rev.voltages["h"] == pytest.approx(-fwd.voltages["h"], rel=1e-12)


def test_sensing_a_source_that_delivers_power_uses_its_negative_current():
    # V1 delivers 1 mA, so i(V1) = -1 mA and F's 100 * i = -0.1 A flows out -> 0: +0.1 V across 1 ohm
    r = solve("V1 in 0 1\nR1 in 0 1k\nF1 out 0 V1 100\nR2 out 0 1")
    assert r.currents["v1"] == pytest.approx(-1e-3, rel=1e-12)
    assert r.voltages["out"] == pytest.approx(+0.1, rel=1e-12)


SIGN_NET = """signs
V1 in 0 2
R1 in m 1k
Vs m 0 0
R2 in mr 2k
Vr 0 mr 0
F1 f1 0 Vs 10
Rf1 f1 0 1k
F2 f2 0 Vr 10
Rf2 f2 0 1k
F3 f3 0 V1 100
Rf3 f3 0 1
F4 0 f4 Vs 10
Rf4 f4 0 1k
H1 h1 0 Vs 2k
Rh1 h1 0 1k
H2 h2 0 Vr 2k
Rh2 h2 0 1k
H3 0 h3 Vs 2k
Rh3 h3 0 1k
E1 e1 0 in 0 5
Re1 e1 0 1k
E2 e2 0 0 in 5
Re2 e2 0 1k
E3 0 e3 in 0 5
Re3 e3 0 1k
G1 g1 0 in 0 2m
Rg1 g1 0 1k
G2 0 g2 in 0 2m
Rg2 g2 0 1k
G3 g3 0 0 in 2m
Rg3 g3 0 1k
.op
.end
"""


@needs_ngspice
def test_signs_of_every_source_orientation_match_ngspice():
    """F/H sensing both orientations and a power-delivering source; E/G with swapped output and
    control terminals. Linear DC, so the match is to round-off (observed 0)."""
    mine, ref = op(parse(SIGN_NET)), run_op(SIGN_NET)
    assert mine.voltages.keys() == ref.voltages.keys() and mine.currents.keys() == ref.currents.keys()
    for k, v in mine.voltages.items():
        assert v == pytest.approx(ref.voltages[k], rel=1e-9, abs=1e-15), k
    for k, i in mine.currents.items():
        assert i == pytest.approx(ref.currents[k], rel=1e-9, abs=1e-15), k


# ---- AC and transient of the four example circuits ----
GAINS = {"vcvs_e": 5.0, "vccs_g": -2.0, "cccs_f": -10.0, "ccvs_h": 2.0}  # DC gain; all have tau = 1 ms


@pytest.mark.parametrize("name,gain", GAINS.items())
def test_ac_response_is_gain_over_one_plus_jwrc(name, gain):
    r = ac(parse(example_text(name)))
    expect = gain / (1 + 2j * np.pi * r.freqs * 1e-3)
    assert np.allclose(r.voltages["out"], expect, rtol=1e-12)


@pytest.mark.parametrize("name,gain", GAINS.items())
def test_step_response_follows_gain_times_an_rc_step(name, gain):
    r = tran(parse(example_text(name)))
    k = r.time <= 3e-3  # before the pulse's falling edge
    expect = gain * ramp_step(r.time[k], 10e-6)
    # trapezoidal error at h = 10 us, tau = 1 ms: measured ~1e-5 of the final value, tolerance 5x that
    assert np.abs(r.voltages["out"][k] - expect).max() < 5e-5 * abs(gain)


@pytest.mark.parametrize("name,gain", GAINS.items())
def test_dc_sweep_is_linear_in_the_source(name, gain):
    r = dc_sweep(parse(example_text(name)))
    assert np.allclose(r.voltages["out"], gain * r.sweep, rtol=1e-12, atol=1e-12)


def test_linear_transient_with_controlled_sources_factors_the_matrix_once():
    c = parse(example_text("cccs_f"))
    with mock.patch("spicelite.analysis.tran.lu_factor", wraps=lu_factor) as factor, \
            mock.patch("spicelite.analysis.tran._newton") as newton:
        r = tran(c)
    assert factor.call_count == 1 and newton.call_count == 0
    assert (r.iterations == 0).all()


def test_controlled_source_inside_the_newton_path():
    # a diode drop buffered by an E: Newton still converges and E follows the diode node
    net = ("t\nV1 in 0 5\nR1 in a 1k\nD1 a 0 dm\nE1 out 0 a 0 2\nR2 out 0 1k\n.model dm D(IS=1e-14 N=1)\n"
           ".dc V1 0 5 1\n.end")
    c = parse(net)
    r = op(c)
    assert r.strategy == "newton"
    assert r.voltages["out"] == pytest.approx(2 * r.voltages["a"], rel=1e-12)
    sweep = dc_sweep(c)
    assert np.allclose(sweep.voltages["out"], 2 * sweep.voltages["a"], rtol=1e-12, atol=1e-12)
    # and in transient and AC: the diode circuit is solved by Newton / linearised, E stamped as always
    assert np.allclose(tran(parse(net.replace(".dc V1 0 5 1", ".tran 1u 5u"))).voltages["out"],
                       2 * tran(parse(net.replace(".dc V1 0 5 1", ".tran 1u 5u"))).voltages["a"], rtol=1e-9)
    a = ac(parse(net.replace("V1 in 0 5", "V1 in 0 5 AC 1").replace(".dc V1 0 5 1", ".ac lin 1 1k 1k")))
    assert a.voltages["out"][0] == pytest.approx(2 * a.voltages["a"][0], rel=1e-12)


# ---- the op-amp ----
def inverting(rf=10e3, r1=1e3, gain=OPAMP_GAIN):
    return solve(f"V1 in 0 1\nR1 in inn {r1!r}\nR2 inn out {rf!r}\nE1 out 0 0 inn {gain!r}")


@pytest.mark.parametrize("gain", [1e2, 1e3, 1e4, 1e5, 1e6, 1e8])
def test_inverting_amplifier_has_the_exact_finite_gain_formula(gain):
    ideal = -10.0
    expect = ideal / (1 + 11.0 / gain)  # -(Rf/R1) / (1 + (1 + Rf/R1)/A)
    assert inverting(gain=gain).voltages["out"] == pytest.approx(expect, rel=1e-9)


def test_closed_loop_gain_approaches_the_ideal_as_open_loop_gain_grows():
    errors = [abs(inverting(gain=a).voltages["out"] - (-10.0)) for a in (1e3, 1e4, 1e5, 1e6)]
    assert errors == sorted(errors, reverse=True)           # strictly better each decade
    for a, err in zip((1e3, 1e4, 1e5, 1e6), errors):
        assert 108.5 < err * a < 110.0                      # error ~ (1 + Rf/R1) * |ideal| / A = 110 / A
    assert errors[-1] < 1.2e-4


def test_non_inverting_amplifier_and_voltage_follower():
    r = solve("V1 in 0 1\nR1 inn 0 1k\nR2 inn out 9k\nE1 out 0 in inn 1e6")   # gain 1 + Rf/R1 = 10
    assert r.voltages["out"] == pytest.approx(10 / (1 + 10 / 1e6), rel=1e-9)
    f = solve("V1 in 0 1\nE1 out 0 in out 1e6\nR1 out 0 1k")                  # follower: A / (1 + A)
    assert f.voltages["out"] == pytest.approx(1e6 / (1 + 1e6), rel=1e-9)


def test_opamp_helper_matches_the_netlist_form_and_defaults_to_1e6():
    base = parse("t\nV1 in 0 1\nR1 in inn 1k\nR2 inn out 10k\n.end")
    helper = replace(base, elements=base.elements + [opamp("E1", "out", "0", "inn")])
    netlist = parse("t\nV1 in 0 1\nR1 in inn 1k\nR2 inn out 10k\nE1 out 0 0 inn 1e6\n.end")
    assert op(helper).voltages == op(netlist).voltages
    assert helper.elements[-1].gain == OPAMP_GAIN == 1e6


def test_open_loop_opamp_warns_clearly_and_still_solves():
    net = "t\nV1 in 0 1m\nR1 in inp 1k\nR2 inp 0 1k\nE1 out 0 inp 0 1e6\nRl out 0 1k\n.end"
    with pytest.warns(OpenLoopWarning, match=r"e1: no feedback path from its output node 'out'.*open loop"):
        r = op(parse(net))
    assert r.voltages["out"] == pytest.approx(1e6 * 0.5e-3, rel=1e-12)  # gain x the differential input


@pytest.mark.parametrize("name", ["inv_amp", "integrator", "sallen_key_lp"])
def test_closed_loop_examples_do_not_warn(name):
    with warnings.catch_warnings():
        warnings.simplefilter("error", OpenLoopWarning)
        op(parse(example_text(name)))


def test_feedback_through_a_capacitor_counts_and_low_gain_e_never_warns():
    with warnings.catch_warnings():
        warnings.simplefilter("error", OpenLoopWarning)
        op(parse("t\nV1 in 0 1\nR1 in inn 1k\nC1 inn out 1u\nE1 out 0 0 inn 1e6\n.end"))
        op(parse("t\nV1 in 0 1\nE1 out 0 in 0 5\nR1 out 0 1k\n.end"))   # gain 5: not an op-amp


def test_floating_opamp_input_is_a_clear_error_naming_the_node():
    with pytest.raises(SingularCircuitError, match=r"node\(s\) inp have no DC path to ground"):
        solve("V1 in 0 1\nR1 in inn 1k\nR2 inn out 10k\nE1 out 0 inp inn 1e6")


def test_a_voltage_source_in_parallel_with_an_e_is_reported_not_a_crash():
    with pytest.raises(SingularCircuitError, match="singular"):
        solve("V1 a 0 1\nE1 a 0 b 0 2\nR1 b 0 1k\nI1 0 b 1m")


# ---- inverting amplifier example, DC and AC ----
def test_inv_amp_example_dc_and_ac_gain():
    c = parse(example_text("inv_amp"))
    assert op(c).voltages["out"] == pytest.approx(-10 / (1 + 11 / 1e6), rel=1e-9)
    h = ac(c).voltages["out"]
    assert np.allclose(h, -10 / (1 + 11 / 1e6), rtol=1e-9)              # flat: the model has no bandwidth limit
    assert abs(phase_degrees(h)[0]) == pytest.approx(180.0, abs=1e-9)  # inverting
    sweep = dc_sweep(c)
    assert np.allclose(sweep.voltages["out"], -10 / (1 + 11 / 1e6) * sweep.sweep, rtol=1e-9, atol=1e-12)


# ---- integrator example ----
def test_integrator_ramps_at_minus_one_volt_per_millisecond_then_holds():
    c = parse(example_text("integrator"))
    r = tran(c)
    pulse = c.elements[0].tran
    assert isinstance(pulse, Pulse)
    # exact integral of the PULSE input on a 1 us grid (its corners are on the grid, so trapezoids are exact)
    fine_t = np.arange(0, 2e-3 + 1e-9, 1e-6)
    vin = np.array([pulse.value(t) for t in fine_t])
    integral = np.concatenate([[0.0], np.cumsum((vin[1:] + vin[:-1]) / 2 * 1e-6)])
    expect = -np.interp(r.time, fine_t, integral) / 1e-3                     # -(1/RC) * integral, RC = 1 ms
    # measured: 5e-7 V off ngspice; the closed-loop integrator's finite-gain droop is ~1e-6 over 2 ms
    assert np.abs(r.voltages["out"] - expect).max() < 5e-6
    assert r.voltages["out"].min() == pytest.approx(-1.0, abs=2e-2)          # ramp: 1 V * 1 ms / RC
    assert r.voltages["out"][-1] == pytest.approx(r.voltages["out"].min(), abs=2e-3)   # ...then it holds


def test_finite_gain_makes_the_integrator_leak():
    net = example_text("integrator").replace("1e6", "100")                  # A = 100: time constant A*RC = 0.1 s
    held = tran(parse(net)).voltages["out"][-1]
    ideal = tran(parse(example_text("integrator"))).voltages["out"][-1]
    assert abs(held) < abs(ideal) and abs(held - ideal) > 5e-3             # visibly droops


# ---- Sallen-Key low-pass: analytic cutoff and Q ----
R, C1, C2 = 10e3, 80e-9, 10e-9
F0 = 1 / (2 * math.pi * R * math.sqrt(C1 * C2))
Q = math.sqrt(C1 / C2) / 2


def sk_h(f, r=R, c1=C1, c2=C2):
    s = 2j * np.pi * f
    return 1 / (s**2 * r * r * c1 * c2 + s * c2 * 2 * r + 1)


def test_sallen_key_matches_the_second_order_transfer_function():
    r = ac(parse(example_text("sallen_key_lp")))
    # finite op-amp gain (1e6) perturbs the follower by ~1e-6: measured worst 3e-7, tolerance 1e-5
    assert np.allclose(r.voltages["out"], sk_h(r.freqs), rtol=1e-5)


def test_sallen_key_natural_frequency_and_q():
    assert F0 == pytest.approx(562.7, abs=0.1) and Q == pytest.approx(1.4142, abs=1e-4)
    c = parse(example_text("sallen_key_lp"))
    h = ac(c, AcSweep("lin", 1, F0, F0)).voltages["out"][0]
    assert abs(h) == pytest.approx(Q, rel=1e-5)                              # |H(f0)| = Q
    assert phase_degrees(np.array([h]))[0] == pytest.approx(-90.0, abs=1e-3)  # and phase -90 degrees there
    dc = ac(c, AcSweep("lin", 1, 1e-3 * F0, 1e-3 * F0)).voltages["out"][0]
    assert abs(dc) == pytest.approx(1.0, rel=2e-6)                           # unity DC gain


def test_sallen_key_peak_frequency_and_height():
    f_peak = F0 * math.sqrt(1 - 1 / (2 * Q**2))
    h_peak = Q / math.sqrt(1 - 1 / (4 * Q**2))
    r = ac(parse(example_text("sallen_key_lp")), AcSweep("lin", 4001, 300, 800))
    mag = np.abs(r.voltages["out"])
    assert r.freqs[mag.argmax()] == pytest.approx(f_peak, abs=0.2)
    assert mag.max() == pytest.approx(h_peak, rel=1e-5)


def test_sallen_key_butterworth_variant_is_3db_down_at_cutoff():
    text = example_text("sallen_key_lp").replace("C1 n1 out 80n", "C1 n1 out 20n")   # C1/C2 = 2: Q = 0.7071
    f0 = 1 / (2 * math.pi * R * math.sqrt(20e-9 * C2))
    h = ac(parse(text), AcSweep("lin", 1, f0, f0)).voltages["out"][0]
    assert magnitude_db(np.array([h]))[0] == pytest.approx(-10 * math.log10(2), abs=1e-4)
    assert abs(h) == pytest.approx(1 / math.sqrt(2), rel=1e-5)
