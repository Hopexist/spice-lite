from pathlib import Path

import pytest

from spicelite import CurrentSource, NetlistError, Resistor, VoltageSource, parse
from spicelite.parser import parse_file, parse_value

EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.mark.parametrize("text,expected", [
    ("10", 10.0), ("1k", 1e3), ("1K", 1e3), ("1meg", 1e6), ("1MEG", 1e6),
    ("1m", 1e-3), ("1M", 1e-3), ("2.2u", 2.2e-6), ("4n", 4e-9),
    ("10p", 1e-11), ("3f", 3e-15), ("1g", 1e9), ("1t", 1e12),
    ("1e3", 1e3), ("-5", -5.0), (".5k", 500.0), ("1.5E-3", 1.5e-3),
])
def test_parse_value(text, expected):
    assert parse_value(text) == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("text,exact", [("10u", 1e-5), ("1u", 1e-6), ("2.2k", 2200.0), ("3m", 3e-3), ("1e3k", 1e6)])
def test_parse_value_is_correctly_rounded(text, exact):
    # Multiplying 10 * 1e-6 gives 9.999999999999999e-06; scaling in decimal gives exactly 1e-05.
    assert parse_value(text) == exact


@pytest.mark.parametrize("bad", ["abc", "1x", "1kohm", "", "1..2", "k"])
def test_bad_value(bad):
    with pytest.raises(NetlistError):
        parse_value(bad)


def test_basic_netlist():
    c = parse("My title\nV1 in 0 DC 5\nR1 in out 1k\nR2 out 0 1meg\nI1 0 out 1m\n.end\n")
    assert c.title == "My title"
    assert c.elements == [
        VoltageSource("v1", "in", "0", 5.0),
        Resistor("r1", "in", "out", 1e3),
        Resistor("r2", "out", "0", 1e6),
        CurrentSource("i1", "0", "out", 1e-3),
    ]


def test_dc_keyword_optional():
    assert parse("t\nV1 a 0 5\n.end").elements[0].dc == 5.0


def test_case_insensitive():
    c = parse("T\nr1 A B 1K\nR2 b 0 1Meg\n.END")
    assert [e.name for e in c.elements] == ["r1", "r2"]
    assert c.elements[0].n1 == "a" and c.elements[1].value == 1e6


def test_comments_and_blank_lines():
    c = parse("t\n* full comment\n\nR1 a 0 1k ; inline\n   \n.end")
    assert len(c.elements) == 1


def test_title_is_never_parsed():
    # A first line that looks like an element is still the title.
    c = parse("R1 a 0 1k\n.end")
    assert c.elements == [] and c.title == "R1 a 0 1k"


def test_continuation():
    c = parse("t\nR1 a\n+ 0\n+ 2k\n.end")
    assert c.elements == [Resistor("r1", "a", "0", 2e3)]


def test_continuation_after_comment_line():
    assert len(parse("t\nR1 a 0\n* note\n+ 1k\n.end").elements) == 1


def test_continuation_without_predecessor():
    with pytest.raises(NetlistError) as e:
        parse("t\n+ R1 a 0 1k\n.end")
    assert e.value.line == 2


def test_stops_at_end():
    assert len(parse("t\nR1 a 0 1k\n.end\nR2 a 0 bogus").elements) == 1


def test_error_line_numbers():
    with pytest.raises(NetlistError) as e:
        parse("t\n* c\nR1 a 0 1k\nD1 a 0 1u\n.end")
    assert e.value.line == 4 and "line 4" in str(e.value)


def test_error_line_is_start_of_continued_line():
    with pytest.raises(NetlistError) as e:
        parse("t\nR1 a 0\n+ oops\n.end")
    assert e.value.line == 2


@pytest.mark.parametrize("net", [
    "t\nX1 a 0 1\n.end",           # unknown element
    "t\nR1 a 0\n.end",             # missing value
    "t\nR1 a\n.end",               # missing node
    "t\nR1 a 0 1k 5\n.end",        # extra token
    "t\nR1 a 0 xyz\n.end",         # bad value
    "t\nR1 a 0 0\n.end",           # zero resistance
    "t\nR1 a 0 -1k\n.end",         # negative resistance
    "t\nR1 a 0 1k\nr1 b 0 1k\n.end",  # duplicate (case-insensitive)
    "t\n.noise v(a) v1 dec 10 1 1k\n.end",  # directive not supported
    "t\nV1 a 0 EXP(0 1 1m 1m 2m 1m)\n.end",  # source type not supported
    "t\nV1 a 0 DC\n.end",          # DC without value
])
def test_errors(net):
    with pytest.raises(NetlistError):
        parse(net)


def test_node_index_ground_excluded_first_appearance_order():
    c = parse("t\nV1 in 0 1\nR1 in out 1\nR2 out 0 1\n.end")
    assert c.node_index() == {"in": 0, "out": 1}
    assert [v.name for v in c.voltage_sources()] == ["v1"]


def test_examples_parse():
    d = parse_file(EXAMPLES / "divider.cir")
    assert len(d.elements) == 3 and d.node_index() == {"in": 0, "out": 1}
    i = parse_file(EXAMPLES / "current_source.cir")
    assert i.elements[0] == CurrentSource("i1", "0", "a", 2e-3)
