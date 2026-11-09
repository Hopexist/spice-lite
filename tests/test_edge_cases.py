"""Odd-but-plausible netlists: each must either solve correctly or fail with a clear error."""
import numpy as np
import pytest

from spicelite import NetlistError, SingularCircuitError, parse
from spicelite.analysis.ac import ac
from spicelite.analysis.dc import op
from spicelite.analysis.tran import tran
from spicelite.circuit import TranSpec

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


# ---- Milestones 8 and 9: MOSFETs, initial conditions, step control ------------------------------

NMOS_MODEL = ".model nm NMOS (VTO=1 KP=100u)\n"


def mos_net(device: str) -> str:
    return f"t\nVd d 0 DC 3\nVg g 0 DC 2\n{device}\n{NMOS_MODEL}.op\n.end\n"


def test_mosfet_with_w_and_l_omitted_uses_ngspices_100um_defaults():
    # omitted == explicit, and W/L = 1 means beta = KP: Id = KP/2 (2 - 1)^2 = 50 uA in saturation (Vds = 3 > Vov = 1)
    omitted = op(parse(mos_net("M1 d g 0 0 nm")))
    explicit = op(parse(mos_net("M1 d g 0 0 nm W=100u L=100u")))
    assert omitted.currents["vd"] == explicit.currents["vd"] == pytest.approx(-50e-6, rel=1e-6)
    only_w = op(parse(mos_net("M1 d g 0 0 nm W=200u")))  # L still defaults: W/L = 2
    assert only_w.currents["vd"] == pytest.approx(-100e-6, rel=1e-6)


@pytest.mark.parametrize("device,msg", [("M1 d g 0 0 nm W=0 L=1u", "W must be positive"),
                                        ("M1 d g 0 0 nm W=1u L=0", "L must be positive"),
                                        ("M1 d g 0 0 nm W=-1u L=1u", "W must be positive")])
def test_zero_or_negative_mosfet_dimensions_are_rejected_with_the_line_number(device, msg):
    with pytest.raises(NetlistError, match=rf"line 4: 'm1': {msg}"):
        parse(mos_net(device))


def test_floating_gate_and_floating_bulk_are_reported_by_name():
    with pytest.raises(SingularCircuitError, match=r"node\(s\) g have no DC path"):
        op(parse(f"t\nVd d 0 DC 3\nM1 d g 0 0 nm W=1u L=1u\n{NMOS_MODEL}"))
    with pytest.raises(SingularCircuitError, match=r"node\(s\) b have no DC path"):
        op(parse(f"t\nVd d 0 DC 3\nVg g 0 DC 2\nM1 d g 0 b nm W=1u L=1u\n{NMOS_MODEL}"))


def test_mosfet_gate_connected_through_a_resistor_is_not_floating():
    r = op(parse(f"t\nVd d 0 DC 3\nVg g0 0 DC 2\nRg g0 g 1meg\nM1 d g 0 0 nm W=100u L=100u\n{NMOS_MODEL}"))
    assert r.voltages["g"] == pytest.approx(2.0, rel=1e-9)  # no gate current: no drop across Rg


def test_ic_on_a_nonexistent_node_is_a_netlist_error():
    with pytest.raises(NetlistError, match=r"line 4: .ic refers to node 'zzz', which is not in the circuit"):
        parse("t\nR1 a 0 1k\nC1 a 0 1u\n.ic v(zzz)=1\n.tran 1u 1m uic\n")


def test_ic_without_uic_is_an_error_and_ic_on_a_capacitorless_node_has_no_effect_error():
    with pytest.raises(NetlistError, match=r"\.ic is only used with `uic`"):
        parse("t\nR1 a 0 1k\nC1 a 0 1u\n.ic v(a)=1\n.tran 1u 1m\n")
    with pytest.raises(ValueError, match=r"\.ic on node\(s\) b has no effect"):
        tran(parse("t\nV1 a 0 DC 1\nR1 a b 1k\nR2 b 0 1k\nC1 a 0 1u\n.ic v(b)=1\n.tran 1u 1m uic\n"))


def test_uic_on_a_circuit_without_capacitors_starts_from_the_dc_values_at_zero_state():
    # nothing to initialise: the resistive circuit simply follows its sources (no error, no spurious dynamics)
    r = tran(parse("t\nV1 a 0 DC 1\nR1 a b 1k\nR2 b 0 1k\n.tran 100u 1m uic\n"))
    assert np.allclose(r.voltages["b"], 0.5) and np.allclose(r.voltages["a"], 1.0)


@pytest.mark.parametrize("adaptive", ["", ".options step=adaptive\n"])
def test_tstep_larger_than_tstop_is_a_netlist_error(adaptive):
    with pytest.raises(NetlistError, match=r"tstop \(0.001\) is below tstep \(1.0\)"):
        parse(f"t\nV1 a 0 DC 1\nR1 a b 1k\nC1 b 0 1u\n{adaptive}.tran 1 1m\n")
    with pytest.raises(ValueError, match="tstop"):
        TranSpec(1.0, 1e-3)


def test_adaptive_tstep_equal_to_tstop_takes_a_single_step():
    r = tran(parse("t\nV1 a 0 DC 1\nR1 a b 1k\nC1 b 0 1u\n.tran 1m 1m\n"), adaptive=True)
    assert len(r.time) >= 2 and r.time[-1] == 1e-3 and r.time[0] == 0.0


def test_mna_build_refuses_a_mosfet_instead_of_silently_dropping_it():
    """Found in the stamping audit: mna.build guarded only diodes, so a MOSFET circuit built directly
    (without the Newton solver) came back with the transistor missing and a plausible-looking answer."""
    from spicelite.mna import build, solve
    c = parse("t\nVDD d 0 DC 5\nVG g 0 DC 2\nR1 d x 1k\nM1 x g 0 0 nm\n.model nm NMOS (VTO=1 KP=1e-4)\n.op\n")
    with pytest.raises(NotImplementedError, match="m1"):
        build(c)
    with pytest.raises(NotImplementedError, match="m1"):
        solve(c)
