"""DC behaviour with C and L: C is open, L is a 0 V source (so Milestone 2 results hold)."""
import pytest

from spicelite import SingularCircuitError, parse
from spicelite.analysis.dc import op


def solve(body: str):
    return op(parse("title\n" + body + "\n.end"))


def test_capacitor_is_open_at_dc():
    r = solve("V1 a 0 5\nR1 a b 1k\nC1 b 0 1u\nR2 b 0 1k")
    assert r.voltages["b"] == pytest.approx(2.5, rel=1e-12)
    assert r.currents["v1"] == pytest.approx(-2.5e-3, rel=1e-12)


def test_inductor_is_short_at_dc():
    r = solve("V1 a 0 6\nR1 a b 1k\nL1 b c 1m\nR2 c 0 2k")
    assert r.voltages["b"] == pytest.approx(4, rel=1e-12)
    assert r.voltages["c"] == pytest.approx(4, rel=1e-12)
    assert r.currents["l1"] == pytest.approx(2e-3, rel=1e-12)  # flows b -> c, positive
    assert r.currents["v1"] == pytest.approx(-2e-3, rel=1e-12)


def test_node_held_only_by_capacitor_is_floating_at_dc():
    with pytest.raises(SingularCircuitError, match="no DC path to ground"):
        solve("V1 a 0 5\nC1 a b 1u")


def test_inductor_across_voltage_source_is_a_loop_at_dc():
    with pytest.raises(SingularCircuitError, match="l1 closes a loop of voltage sources"):
        solve("V1 a 0 5\nL1 a 0 1m")
