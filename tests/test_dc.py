import numpy as np
import pytest

from spicelite import parse
from spicelite.analysis.dc import op
from spicelite.circuit import SingularCircuitError


def solve(body: str):
    return op(parse("title\n" + body + "\n.end"))


def test_divider():
    r = solve("V1 in 0 10\nR1 in out 1k\nR2 out 0 2k")
    assert r.voltages["in"] == pytest.approx(10, rel=1e-12)
    assert r.voltages["out"] == pytest.approx(10 * 2 / 3, rel=1e-12)
    # SPICE sign: a source delivering power has negative branch current.
    assert r.currents["v1"] == pytest.approx(-10 / 3e3, rel=1e-12)


def test_series_parallel():
    # 12 V across 1k in series with (2k || 2k = 1k): v(b) = 6 V, 6 mA total.
    r = solve("V1 a 0 12\nR1 a b 1k\nR2 b 0 2k\nR3 b 0 2k")
    assert r.voltages["b"] == pytest.approx(6, rel=1e-12)
    assert r.currents["v1"] == pytest.approx(-6e-3, rel=1e-12)


@pytest.mark.parametrize("src,expected", [("I1 0 a 2m", 2.0), ("I1 a 0 2m", -2.0)])
def test_current_source_into_resistor(src, expected):
    # I n+ n- flows n+ -> source -> n-, so "I1 0 a" pushes current INTO node a.
    assert solve(f"{src}\nR1 a 0 1k").voltages["a"] == pytest.approx(expected, rel=1e-12)


def test_two_sources():
    r = solve("V1 a 0 12\nR1 a b 1k\nR2 b c 2k\nV2 c 0 6\nR3 b 0 3k")
    assert r.voltages["b"] == pytest.approx(90 / 11, rel=1e-12)
    assert r.currents["v1"] == pytest.approx(-(12 - 90 / 11) / 1e3, rel=1e-12)
    assert r.currents["v2"] == pytest.approx((90 / 11 - 6) / 2e3, rel=1e-12)  # source absorbs


def test_voltage_and_current_source_together():
    # I1 pushes 1 mA into a; V1 holds a at 5 V; so V1 must sink it: i(V1) = +1 mA... plus R current.
    r = solve("V1 a 0 5\nR1 a 0 1k\nI1 0 a 1m")
    assert r.voltages["a"] == pytest.approx(5, rel=1e-12)
    assert r.currents["v1"] == pytest.approx(1e-3 - 5e-3, rel=1e-12)


def test_balanced_bridge_has_no_bridge_current():
    r = solve("V1 t 0 10\nR1 t a 1k\nR2 a 0 2k\nR3 t b 3k\nR4 b 0 6k\nR5 a b 5k")
    assert r.voltages["a"] - r.voltages["b"] == pytest.approx(0, abs=1e-12)


def test_unbalanced_bridge_vs_manual_nodal():
    r = solve("V1 t 0 10\nR1 t a 1k\nR2 a 0 2k\nR3 t b 3k\nR4 b 0 4k\nR5 a b 5k")
    g = lambda ohms: 1 / ohms  # noqa: E731
    # KCL at a and b with v(t) = 10, written out by hand.
    G = np.array([[g(1e3) + g(2e3) + g(5e3), -g(5e3)],
                  [-g(5e3), g(3e3) + g(4e3) + g(5e3)]])
    rhs = np.array([10 * g(1e3), 10 * g(3e3)])
    va, vb = np.linalg.solve(G, rhs)
    assert r.voltages["a"] == pytest.approx(va, rel=1e-12)
    assert r.voltages["b"] == pytest.approx(vb, rel=1e-12)


def test_op_directive_sets_flag():
    c = parse("t\nV1 a 0 1\nR1 a 0 1\n.op\n.end")
    assert c.op and op(c).voltages["a"] == pytest.approx(1)


def test_floating_node_error_names_the_nodes():
    # a-b is an island: the current source gives it current but no voltage reference.
    with pytest.raises(SingularCircuitError, match="a, b"):
        solve("I1 0 a 1m\nR1 a b 1k\nV1 x 0 1\nR2 x 0 1k")


def test_node_only_on_current_source_is_floating():
    with pytest.raises(SingularCircuitError, match="no DC path to ground"):
        solve("I1 0 a 1m")


def test_voltage_source_loop_error():
    with pytest.raises(SingularCircuitError, match="loop of voltage sources"):
        solve("V1 a 0 5\nV2 a 0 3\nR1 a 0 1k")


def test_voltage_source_loop_through_three_sources():
    with pytest.raises(SingularCircuitError, match="v3"):
        solve("V1 a b 1\nV2 b c 1\nV3 c a 1\nR1 a 0 1k")
