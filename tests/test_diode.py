import math
from unittest import mock

import numpy as np
import pytest
from scipy.special import lambertw

from spicelite import DcSweep, Diode, DiodeModel, NetlistError, parse
from spicelite.analysis.dc import dc_sweep, op
from spicelite.analysis.newton import pnjlim, solve_nonlinear
from spicelite.circuit import ConvergenceError, Resistor
from spicelite.elements import GMIN, VT, diode_iv, stamp_diode

MODEL = ".model dm D(IS=1e-14 N=1)"


def net(body, model=MODEL, tail=""):
    return f"title\n{body}\n{model}\n{tail}\n.end"


def series(vs, r, model=MODEL):
    """Source -> R -> diode to ground; node `a` is the diode's anode (RS, if any, is inside the model)."""
    return parse(net(f"V1 in 0 {vs}\nR1 in a {r}\nD1 a 0 dm", model))


def lambert(vs, r, IS=1e-14, N=1.0, RS=0.0):
    """Exact solution of  Vs - (R + RS) - diode || GMIN  via the Lambert W function.
    GMIN (SPICE's junction shunt) is folded into the source's Thevenin equivalent, which leaves
    a plain series diode:  y e^y = (IS Rth/a) e^{(Vth + IS Rth)/a},  I = a y / Rth - IS.
    Returns (source current into the circuit, voltage at node a)."""
    a, rt = N * VT, r + RS
    vth, rth = vs / (1 + GMIN * rt), rt / (1 + GMIN * rt)
    i_d = a / rth * lambertw(IS * rth / a * np.exp((vth + IS * rth) / a)).real - IS
    vd = vth - i_d * rth
    i_src = (vs - vd) / rt
    return i_src, vs - i_src * r


# ---- parsing: .model ----
def test_model_parsed_with_defaults_and_case_insensitive():
    c = parse("t\n.MODEL Dm1 d (Is=2e-15 N=1.5 rs=10)\n.MODEL dflt D\n.end")
    assert c.models["dm1"] == DiodeModel("dm1", 2e-15, 1.5, 10.0)
    assert c.models["dflt"] == DiodeModel("dflt", 1e-14, 1.0, 0.0)  # SPICE defaults


@pytest.mark.parametrize("line", [
    ".model dm D(IS=1e-14, N=1, RS=5)",      # commas
    ".model dm D IS=1e-14 N=1 RS=5",         # no parentheses
    ".model dm D( IS = 1e-14  N = 1 RS = 5 )",  # spaces around =
])
def test_model_syntax_variants(line):
    assert parse(f"t\n{line}\n.end").models["dm"] == DiodeModel("dm", 1e-14, 1.0, 5.0)


@pytest.mark.parametrize("line", [
    ".model dm NPN(IS=1e-14)",       # unknown type
    ".model dm D(BV=100)",           # unknown parameter
    ".model dm D(CJO=1p)",           # unknown parameter
    ".model dm D(IS)",               # no value
    ".model dm D(IS=abc)",           # bad value
    ".model dm D(IS=0)",             # IS must be positive
    ".model dm D(IS=-1e-14)",
    ".model dm D(N=0)",              # N must be positive
    ".model dm D(RS=-1)",            # RS must be >= 0
    ".model dm D(IS=1e-14 IS=2e-14)",  # duplicate parameter
    ".model dm",                     # no type
    ".model",                        # nothing
    ".model dm D(IS=1e-14) extra",   # trailing junk
])
def test_bad_model_lines(line):
    with pytest.raises(NetlistError) as e:
        parse(f"t\nR1 a 0 1\n{line}\n.end")
    assert e.value.line == 3


def test_duplicate_model_name():
    with pytest.raises(NetlistError, match="duplicate model"):
        parse("t\n.model dm D\n.model DM D\n.end")


# ---- parsing: diode element ----
def test_diode_element_and_model_defined_later():
    c = parse("t\nD1 a 0 dm\n.model dm D(IS=2e-14)\n.end")
    d = c.elements[0]
    assert isinstance(d, Diode) and (d.anode, d.cathode, d.model_name) == ("a", "0", "dm")
    assert d.model.IS == 2e-14 and c.node_index() == {"a": 0}


def test_unknown_model_reported_at_the_diode_line():
    with pytest.raises(NetlistError, match="unknown model 'nope'") as e:
        parse("t\nR1 a 0 1\nD1 a 0 nope\n.model dm D\n.end")
    assert e.value.line == 3


@pytest.mark.parametrize("line", ["D1 a 0", "D1 a 0 dm 2", "D1 a dm"])
def test_bad_diode_lines(line):
    with pytest.raises(NetlistError):
        parse(f"t\n{line}\n.model dm D\n.end")


# ---- parsing: .dc ----
def test_dc_directive_and_grid():
    c = parse("t\nV1 a 0 0\nR1 a 0 1\n.dc V1 0 1 0.25\n.end")
    assert c.dc == DcSweep("v1", 0.0, 1.0, 0.25)
    assert np.allclose(c.dc.values(), [0, 0.25, 0.5, 0.75, 1])
    assert len(DcSweep("v1", 0, 1, 0.1).values()) == 11       # float step, no point lost
    assert np.allclose(DcSweep("v1", 5, -5, -5).values(), [5, 0, -5])  # descending
    assert DcSweep("v1", 2, 2, 1).values().tolist() == [2.0]  # single point


@pytest.mark.parametrize("line", [
    ".dc V1 0 1", ".dc V1 0 1 0.1 5", ".dc V1 0 1 0", ".dc V1 0 1 -0.1", ".dc V1 1 0 0.1",
    ".dc V1 x 1 0.1", ".dc V9 0 1 0.1", ".dc R1 0 1 0.1",  # unknown source / not a source
])
def test_bad_dc_lines(line):
    with pytest.raises(NetlistError) as e:
        parse(f"t\nV1 a 0 0\nR1 a 0 1\n{line}\n.end")
    assert e.value.line == 4


def test_duplicate_dc():
    with pytest.raises(NetlistError, match="duplicate .dc"):
        parse("t\nV1 a 0 0\nR1 a 0 1\n.dc V1 0 1 1\n.dc V1 0 1 1\n.end")


# ---- the Newton companion model ----
def test_diode_iv_matches_shockley_plus_gmin():
    m = DiodeModel("m", IS=1e-14, N=1.5)
    i, g = diode_iv(m, 0.6)
    e = math.exp(0.6 / (1.5 * VT))
    assert i == pytest.approx(1e-14 * (e - 1) + GMIN * 0.6, rel=1e-14)
    assert g == pytest.approx(1e-14 / (1.5 * VT) * e + GMIN, rel=1e-14)
    assert diode_iv(m, 0.0) == (0.0, 1e-14 / (1.5 * VT) + GMIN)  # zero bias: i = 0, g = IS/(N Vt) + GMIN


def test_stamp_diode_hand_computed():
    d = Diode("d1", "a", "b", "m", DiodeModel("m", IS=1e-14, N=1.0))
    vd = 0.5
    e = math.exp(vd / VT)
    g = 1e-14 / VT * e + GMIN
    ieq = 1e-14 * (e - 1) + GMIN * vd - g * vd  # i(vd) - g vd
    A, b = np.zeros((2, 2)), np.zeros(2)
    got = stamp_diode(A, b, {"a": 0, "b": 1}, d, vd)
    assert got == pytest.approx((g, ieq), rel=1e-12)
    assert A == pytest.approx(np.array([[g, -g], [-g, g]]), rel=1e-12)
    assert b == pytest.approx([-ieq, ieq], rel=1e-12)
    # the linearisation is the tangent: exact at vd
    assert g * vd + ieq == pytest.approx(diode_iv(d.model, vd)[0], rel=1e-12)


def test_stamp_diode_to_ground_uses_only_the_anode_row():
    d = Diode("d1", "a", "0", "m", DiodeModel("m"))
    A, b = np.zeros((1, 1)), np.zeros(1)
    g, ieq = stamp_diode(A, b, {"a": 0}, d, 0.0)
    assert A[0, 0] == g and b[0] == -ieq and ieq == 0.0  # at zero bias i = 0 and Ieq = 0


# ---- voltage limiting ----
VCRIT = VT * math.log(VT / (math.sqrt(2) * 1e-14))


def test_pnjlim_leaves_small_and_reverse_steps_alone():
    assert pnjlim(0.3, 0.29, VT, VCRIT) == (0.3, False)        # below vcrit
    assert pnjlim(0.8, 0.79, VT, VCRIT) == (0.8, False)        # above vcrit but a step < 2 vt
    assert pnjlim(-5.0, 0.0, VT, VCRIT) == (-5.0, False)       # reverse jumps are not limited


def test_pnjlim_turns_big_forward_jumps_into_logarithmic_steps():
    v, limited = pnjlim(5.0, 0.6, VT, VCRIT)  # Newton wants +5 V: would be e^193 in the exponential
    assert limited and v == pytest.approx(0.6 + VT * (2 + math.log((5.0 - 0.6) / VT - 2)))
    assert 0.6 < v < 1.0
    v, limited = pnjlim(5.0, 0.0, VT, VCRIT)  # from an off diode: vt ln(v / vt)
    assert limited and v == pytest.approx(VT * math.log(5.0 / VT))


# ---- analytic: Lambert W ----
@pytest.mark.parametrize("vs,r,IS,N,RS", [
    (1, 1e3, 1e-14, 1.0, 0.0), (5, 1e3, 1e-14, 1.0, 0.0), (12, 100.0, 1e-14, 1.0, 0.0),
    (5, 1e5, 1e-14, 1.0, 0.0), (5, 1e3, 1e-14, 1.5, 0.0), (5, 1e3, 1e-12, 1.0, 0.0),
    (5, 100.0, 1e-14, 1.0, 10.0), (3, 10.0, 1e-14, 2.0, 5.0),
])
def test_forward_bias_matches_lambert_w(vs, r, IS, N, RS):
    c = series(vs, r, f".model dm D(IS={IS!r} N={N!r} RS={RS!r})")
    i_src, va = lambert(vs, r, IS, N, RS)
    res = op(c)
    # Newton stops at reltol 1e-6 but converges quadratically, so it lands ~1e-12 from exact.
    assert res.currents["v1"] == pytest.approx(-i_src, rel=1e-9)   # SPICE sign: the source delivers current
    assert res.voltages["a"] == pytest.approx(va, rel=1e-9)
    assert res.strategy == "newton" and "d1#int" not in res.voltages  # hidden RS node stays hidden


def test_reverse_bias_leakage_is_is_plus_gmin():
    res = op(series(-5, "1k"))
    assert res.voltages["a"] == pytest.approx(-5.0, abs=1e-8)
    # reverse current = IS (e^{-193} - 1) + GMIN * (-5): dominated by SPICE's gmin shunt
    assert res.currents["v1"] == pytest.approx(1e-14 + GMIN * 5.0, rel=1e-6)
    assert res.iterations <= 4 and res.strategy == "newton"


def test_zero_bias():
    res = op(series(0, "1k"))
    assert res.voltages["a"] == pytest.approx(0, abs=1e-15) and res.currents["v1"] == pytest.approx(0, abs=1e-15)


def test_hard_switch_coarse_sweep_from_reverse_to_forward():
    """-10 V -> +10 V in 5 V jumps: each point starts from a very different diode state."""
    c = parse(net("V1 in 0 0\nR1 in a 10\nD1 a 0 dm", tail=".dc V1 -10 10 5"))
    r = dc_sweep(c)
    assert r.sweep.tolist() == [-10, -5, 0, 5, 10]
    assert r.voltages["a"][:2] == pytest.approx([-10, -5], abs=1e-8)       # off: ~ the source
    assert r.voltages["a"][2] == pytest.approx(0, abs=1e-12)
    for k in (3, 4):                                                       # on: the junction clamps
        assert r.voltages["a"][k] == pytest.approx(lambert(r.sweep[k], 10.0)[1], rel=1e-9)
        assert 0.8 < r.voltages["a"][k] < 1.1
    assert r.iterations.max() <= 15  # regression guard: the jump to +10 V is the hardest step


# ---- iteration counts stay bounded (regression guard) ----
# Observed worst cases: op from a zero start 7 / 10 / 4 iterations, sweep points 5 / 7 / 4.
# The limits leave ~3 iterations of margin: a change that doubles them is a real regression.
BOUNDS = {"diode_rectifier_dc.cir": (10, 8), "diode_clamp.cir": (13, 10), "diode_iv_sweep.cir": (7, 7)}


@pytest.mark.parametrize("name", BOUNDS)
def test_newton_iterations_stay_bounded_on_examples(name):
    from pathlib import Path

    c = parse((Path(__file__).parent.parent / "examples" / name).read_text())
    op_limit, sweep_limit = BOUNDS[name]
    o = op(c)
    assert o.strategy == "newton" and o.iterations <= op_limit
    assert dc_sweep(c).iterations.max() <= sweep_limit


def test_sweep_warm_start_beats_cold_start():
    from dataclasses import replace

    c = parse(net("V1 in 0 0\nR1 in a 1k\nD1 a 0 dm", tail=".dc V1 0 5 0.25"))
    warm = dc_sweep(c).iterations
    cold = [op(replace(c, elements=[replace(e, dc=v) if e.name == "v1" else e for e in c.elements])).iterations
            for v in c.dc.values()]
    assert warm[1:].mean() < np.mean(cold[1:])


# ---- the fallback ----
FALLBACK_NET = net("V1 in 0 1\nR1 in a 1k\nD1 a 0 dm")  # plain Newton needs 8 iterations here


def test_gmin_stepping_rescues_a_circuit_plain_newton_cannot_solve_in_time():
    c = parse(FALLBACK_NET)
    assert solve_nonlinear(c).iterations == 8  # reference: plain Newton, no cap pressure
    # Cap each Newton run at 5 iterations. Without the fallback it fails ...
    with pytest.raises(ConvergenceError) as e:
        solve_nonlinear(c, max_iter=5, fallback=False)
    assert e.value.iterations == 5 and e.value.worst_node in ("a", "in", "i(v1)")
    # ... with the fallback the SAME cap succeeds, and the result says gmin stepping did it.
    rescued = solve_nonlinear(c, max_iter=5)
    assert rescued.strategy == "gmin" and rescued.iterations > 5
    plain = solve_nonlinear(c)
    assert rescued.x == pytest.approx(plain.x, rel=1e-9, abs=1e-12)  # same answer


def test_fallback_not_used_when_plain_newton_converges():
    assert solve_nonlinear(parse(FALLBACK_NET)).strategy == "newton"


def test_convergence_error_reports_iterations_and_worst_node():
    c = parse(FALLBACK_NET)
    with pytest.raises(ConvergenceError, match=r"3 iterations.*worst unknown is \S+") as e:
        solve_nonlinear(c, max_iter=3, fallback=False)
    assert e.value.iterations == 3 and e.value.worst_node


def test_convergence_error_when_even_the_fallback_fails():
    with pytest.raises(ConvergenceError, match="gmin stepping failed") as e:
        solve_nonlinear(parse(FALLBACK_NET), max_iter=1)
    assert e.value.iterations > 1 and e.value.worst_node


# ---- linear circuits keep the old fast path ----
def test_linear_circuit_never_enters_newton():
    c = parse("t\nV1 in 0 10\nR1 in out 1k\nR2 out 0 2k\n.dc V1 0 10 5\n.end")
    with mock.patch("spicelite.analysis.dc.solve_nonlinear") as newton:
        o, s = op(c), dc_sweep(c)
    newton.assert_not_called()
    assert o.voltages["out"] == pytest.approx(10 * 2 / 3, rel=1e-12) and (o.iterations, o.strategy) == (0, "linear")
    assert s.voltages["out"] == pytest.approx([0, 5 * 2 / 3, 10 * 2 / 3], rel=1e-12, abs=1e-15)
    assert s.iterations.tolist() == [0, 0, 0]


def test_dc_sweep_of_a_current_source():
    c = parse("t\nI1 0 a 0\nR1 a 0 2k\n.dc I1 0 3m 1m\n.end")
    assert dc_sweep(c).voltages["a"] == pytest.approx([0, 2, 4, 6])


def test_dc_sweep_does_not_modify_the_circuit():
    c = parse(net("V1 in 0 5\nR1 in a 1k\nD1 a 0 dm", tail=".dc V1 0 1 0.5"))
    dc_sweep(c)
    assert c.elements[0].dc == 5.0


def test_dc_sweep_without_directive():
    with pytest.raises(ValueError, match="no .dc"):
        dc_sweep(parse("t\nV1 a 0 1\nR1 a 0 1\n.end"))


# ---- the raw MNA builder never silently ignores a diode ----
def test_mna_build_refuses_diodes_without_the_newton_or_small_signal_path():
    from spicelite.mna import build

    with pytest.raises(NotImplementedError, match="d1.*Newton solver or the small-signal path"):
        build(parse(net("V1 in 0 1\nR1 in a 1k\nD1 a 0 dm")))


def test_diode_is_a_dc_path_but_a_source_loop_is_still_singular():
    from spicelite import SingularCircuitError

    # a diode counts as a DC path to ground (its leakage + GMIN), so this circuit is solvable
    assert op(parse(net("I1 0 a 1m\nD1 a 0 dm"))).voltages["a"] == pytest.approx(0.6, abs=0.3)
    with pytest.raises(SingularCircuitError, match="loop of voltage sources"):
        op(parse(net("V1 a 0 1\nV2 a 0 2\nD1 a 0 dm")))


def test_series_resistance_expansion_does_not_change_the_users_circuit():
    c = parse(net("V1 in 0 5\nD1 in 0 dm", model=".model dm D(IS=1e-14 RS=10)"))
    n_before = len(c.elements)
    solve_nonlinear(c)
    assert len(c.elements) == n_before and not any(isinstance(e, Resistor) for e in c.elements)
