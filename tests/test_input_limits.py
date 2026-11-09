"""Hostile or absurd netlist input is refused with a clear message, before any big allocation or raw exception."""
import pytest

from spicelite import NetlistError, parse
from spicelite.circuit import AcSweep, DcSweep
from spicelite.web_api import run_netlist

DIVIDER = "t\nV1 1 0 1\nR1 1 0 1\n"


def test_dc_point_count_is_checked_before_the_sweep_is_built():
    r = run_netlist(DIVIDER + ".dc V1 0 1 1e-7\n")  # 1e7 points: refused up front, not allocated first
    assert not r["ok"] and "needs 10,000,001 points" in r["error"]["message"]


def test_ac_point_count_is_checked_before_the_frequencies_are_built():
    r = run_netlist(DIVIDER + ".ac lin 30000000 1 10\n")
    assert not r["ok"] and "needs 30,000,000 points" in r["error"]["message"]


def test_count_matches_the_generated_values():
    for s in (AcSweep("dec", 10, 1, 1e6), AcSweep("oct", 5, 1, 64), AcSweep("lin", 7, 1, 10)):
        assert s.count() == len(s.frequencies())
    for d in (DcSweep("V1", 0, 1, 0.1), DcSweep("V1", 1, 0, -0.3), DcSweep("V1", 0, 1, 1)):
        assert d.count() == len(d.values())


@pytest.mark.parametrize("value", ["1e9999999", "1e99999999999", "1e400", "-1e400"])
def test_out_of_range_values_are_netlist_errors_with_a_line_number(value):
    with pytest.raises(NetlistError) as err:
        parse(f"t\nV1 1 0 {value}\n.op\n")
    assert err.value.line == 2


def test_extreme_adaptive_tran_range_is_a_clean_error():
    text = "t\nV1 1 0 1\nR1 1 2 1\nC1 2 0 1\n.options step=adaptive\n.tran 1e-300 1e300\n"
    r = run_netlist(text)
    assert not r["ok"] and "internal error" not in r["error"]["message"]
