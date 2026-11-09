"""Odd-but-plausible netlists: each must either solve correctly or fail with a clear error."""
import numpy as np
import pytest

from spicelite import NetlistError, SingularCircuitError, parse
from spicelite.analysis.ac import ac
from spicelite.analysis.dc import op
from spicelite.analysis.tran import tran

BASE = "t\nV1 a 0 DC 1\n"


def test_empty_and_title_only_netlists_are_refused_at_analysis_time():
    # parse() accepts them (a title line is a valid netlist), but there is nothing to solve
    for text in ("", "just a title\n", "title\n.op\n.end\n"):
        with pytest.raises(SingularCircuitError, match="no elements"):
            op(parse(text))


def test_missing_end_is_fine():
    assert op(parse(BASE + "R1 a 0 1k\n.op\n")).voltages["a"] == 1.0


@pytest.mark.parametrize("dup", ["R1 a 0 2k", "r1 a 0 2k"])
def test_duplicate_names_are_errors_with_the_line_number_case_insensitively(dup):
    with pytest.raises(NetlistError, match=r"line 4: duplicate element name 'r1'"):
        parse(BASE + "R1 a 0 1k\n" + dup + "\n")


def test_no_ground_node_reports_the_floating_nodes():
    with pytest.raises(SingularCircuitError, match="no DC path to ground"):
        op(parse("t\nV1 a b DC 1\nR1 a b 1k\n.op\n.end\n"))


def test_floating_subcircuit_is_named():
    with pytest.raises(SingularCircuitError, match="b, c"):
        op(parse(BASE + "R1 a 0 1k\nR2 b c 1k\n.op\n.end\n"))


@pytest.mark.parametrize("line,what", [("R1 a 0 0", "resistance"), ("R1 a 0 -1k", "resistance"),
                                       ("C1 a 0 0", "capacitance"), ("L1 a 0 0", "inductance")])
def test_zero_or_negative_passives_are_rejected(line, what):
    with pytest.raises(NetlistError, match=f"line 3: .* positive {what}"):
        parse(BASE + line + "\n")


def test_zero_valued_sources_are_fine():
    r = op(parse("t\nV1 a 0 DC 0\nR1 a b 1k\nR2 b 0 1k\nI1 0 b DC 0\n.op\n.end\n"))
    assert r.voltages["b"] == 0.0 and r.currents["v1"] == 0.0


@pytest.mark.parametrize("r1,r2", [("1e12", "1e12"), ("1e-9", "1e-9"), ("1t", "1t"), ("1f", "1f")])
def test_extreme_but_balanced_resistor_values_still_divide_exactly_in_half(r1, r2):
    r = op(parse(f"{BASE}R1 a b {r1}\nR2 b 0 {r2}\n.op\n.end\n"))
    assert r.voltages["b"] == pytest.approx(0.5, rel=1e-9)


def test_very_wide_value_ratio_keeps_the_answer():
    # 1e-3 ohm over 1e9 ohm: the divider output is 1e-12 V; conditioning is ~1e12 but still exact enough
    r = op(parse(BASE + "R1 a b 1m\nR2 b 0 1g\n.op\n.end\n"))
    assert r.voltages["b"] == pytest.approx(1.0, rel=1e-9)


def test_tiny_and_huge_capacitors_in_ac_and_tran():
    net = BASE.replace("DC 1", "DC 1 AC 1") + "R1 a b 1k\nC1 b 0 {c}\n.ac dec 2 1 1g\n.tran 1u 10u\n.end\n"
    for c, farads in (("1f", 1e-15), ("1", 1.0)):
        c_ = parse(net.format(c=c))
        out = ac(c_).voltages["b"]
        h = 1 / (1 + 2j * np.pi * 1.0 * 1e3 * farads)  # RC lowpass at the first frequency, 1 Hz
        assert out[0] == pytest.approx(h, rel=1e-9)
        assert tran(c_).voltages["b"][0] == pytest.approx(1.0)  # DC start


def test_resistor_with_both_ends_on_one_node_has_no_effect():
    r = op(parse(BASE + "R1 a a 1k\nR2 a 0 1k\n.op\n.end\n"))
    assert r.voltages["a"] == 1.0 and r.currents["v1"] == pytest.approx(-1e-3)


@pytest.mark.parametrize("text,msg", [
    (BASE + "Q1 a 0 0 npn\n", "unsupported element 'q1'"),
    (BASE + ".noise\n", "unsupported directive '.noise'"),
    (BASE + ".param x=1\n", "unsupported directive '.param'"),
    (BASE + ".subckt foo a b\n", "unsupported directive '.subckt'"),
    (BASE + "R1 a 0 abc\n", "bad value 'abc'"),
])
def test_unsupported_features_fail_loudly_with_line_numbers(text, msg):
    with pytest.raises(NetlistError, match=f"line 3: {msg}"):
        parse(text)
