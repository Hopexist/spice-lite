import math

import numpy as np
import pytest

from spicelite import AcSweep, Capacitor, Inductor, NetlistError, SingularCircuitError, parse
from spicelite.analysis.ac import ac, magnitude_db, phase_degrees

R, C = 1e3, 1e-7
FC = 1 / (2 * math.pi * R * C)
HALF_POWER_DB = -10 * math.log10(2)  # -3.0103 dB


def at(netlist_body: str, f: float):
    """Solve a netlist at the single frequency f."""
    return ac(parse(f"t\n{netlist_body}\n.ac lin 1 {f!r} {f!r}\n.end"))


# ---- parsing ----
def test_parse_c_and_l():
    c = parse("t\nC1 a 0 1u\nL1 a b 2m\n.end")
    assert c.elements == [Capacitor("c1", "a", "0", 1e-6), Inductor("l1", "a", "b", 2e-3)]


@pytest.mark.parametrize("net", ["C1 a 0 0", "C1 a 0 -1u", "L1 a 0 0", "C1 a 0", "L1 a 0 1m 5"])
def test_bad_c_l(net):
    with pytest.raises(NetlistError):
        parse(f"t\n{net}\n.end")


@pytest.mark.parametrize("spec,dc,ac_expected", [
    ("5", 5.0, 0j),
    ("DC 5", 5.0, 0j),
    ("AC 2", 0.0, 2 + 0j),
    ("AC 2 90", 0.0, 2j),                      # phase is degrees in the netlist
    ("DC 5 AC 1", 5.0, 1 + 0j),
    ("AC 1 180 DC 5", 5.0, -1 + 0j),
    ("DC 5 AC 1 -90", 5.0, -1j),
    ("AC 1k", 0.0, 1000 + 0j),
])
def test_source_specs(spec, dc, ac_expected):
    for kind in "VI":
        e = parse(f"t\n{kind}1 a 0 {spec}\n.end").elements[0]
        assert e.dc == dc and e.ac == pytest.approx(ac_expected, abs=1e-12)


@pytest.mark.parametrize("spec", ["AC", "DC 5 AC", "AC 1 2 3", "DC 1 DC 2", "AC 1 AC 2", "AC x", "foo 1"])
def test_bad_source_specs(spec):
    with pytest.raises(NetlistError):
        parse(f"t\nV1 a 0 {spec}\n.end")


@pytest.mark.parametrize("line", [
    ".ac dec 10 1k",               # too few fields
    ".ac dec 10 1 1k 5",           # too many
    ".ac foo 10 1 1k",             # unknown sweep type
    ".ac dec 10.5 1 1k",           # non-integer points
    ".ac dec 0 1 1k",              # zero points
    ".ac dec 10 0 1k",             # zero frequency
    ".ac dec 10 -1 1k",            # negative frequency
    ".ac dec 10 1 -1k",
    ".ac lin 10 0 1k",             # lin from 0 is also rejected
    ".ac dec 10 1k 1",             # fstop < fstart
    ".ac dec 10 x 1k",             # bad value
])
def test_bad_ac_lines(line):
    with pytest.raises(NetlistError) as e:
        parse(f"t\nR1 a 0 1\n{line}\n.end")
    assert e.value.line == 3


def test_duplicate_ac_directive():
    with pytest.raises(NetlistError, match="duplicate .ac"):
        parse("t\n.ac dec 10 1 1k\n.ac dec 10 1 1k\n.end")


def test_ac_directive_parsed_with_suffixes():
    assert parse("t\n.AC DEC 10 1 1meg\n.end").ac == AcSweep("dec", 10, 1.0, 1e6)


def test_sweep_grids():
    assert np.allclose(AcSweep("lin", 5, 1, 5).frequencies(), [1, 2, 3, 4, 5])
    assert np.allclose(AcSweep("oct", 1, 1, 8).frequencies(), [1, 2, 4, 8])
    f = AcSweep("dec", 10, 1, 1e3).frequencies()
    assert len(f) == 31 and f[0] == 1 and f[-1] == pytest.approx(1e3)
    assert AcSweep("lin", 1, 50, 50).frequencies().tolist() == [50.0]


def test_sweep_validates_directly():
    for bad in [("dec", 10, 0, 1e3), ("dec", 10, -5, 1e3), ("dec", 10, 1, 0), ("lin", 0, 1, 2)]:
        with pytest.raises(ValueError):
            AcSweep(*bad)


def test_ac_without_directive():
    with pytest.raises(ValueError, match="no .ac"):
        ac(parse("t\nV1 a 0 AC 1\nR1 a 0 1\n.end"))


# ---- analytic results ----
def test_rc_lowpass_corner():
    h = at(f"V1 in 0 AC 1\nR1 in out {R!r}\nC1 out 0 {C!r}", FC).voltages["out"]
    assert magnitude_db(h)[0] == pytest.approx(HALF_POWER_DB, abs=1e-9)
    assert phase_degrees(h)[0] == pytest.approx(-45, abs=1e-9)


def test_rc_lowpass_response_shape():
    r = ac(parse(f"t\nV1 in 0 AC 1\nR1 in out {R!r}\nC1 out 0 {C!r}\n"
                 f".ac dec 10 {FC / 1e3!r} {FC * 1e3!r}\n.end"))
    h = r.voltages["out"]
    db = magnitude_db(h)
    assert db[0] == pytest.approx(0, abs=1e-5)               # passband
    assert db[-1] - db[-11] == pytest.approx(-20, abs=0.01)  # one decade up: -20 dB/dec
    assert phase_degrees(h)[-1] == pytest.approx(-90, abs=0.1)
    assert np.allclose(h, 1 / (1 + 2j * np.pi * r.freqs * R * C), rtol=1e-12)


def test_rl_highpass_corner():
    L = R / (2 * math.pi * FC)  # corner R/(2 pi L) = FC
    net = f"V1 in 0 AC 1\nR1 in out {R!r}\nL1 out 0 {L!r}"
    h = at(net, FC).voltages["out"]
    assert magnitude_db(h)[0] == pytest.approx(HALF_POWER_DB, abs=1e-9)
    assert phase_degrees(h)[0] == pytest.approx(45, abs=1e-9)
    low = at(net, FC / 1e3).voltages["out"]
    assert magnitude_db(low)[0] == pytest.approx(-60, abs=0.01)  # 20 dB/dec rise


def test_series_rlc_resonance():
    Rr, L, Cc = 10.0, 1e-3, 1e-6
    f0 = 1 / (2 * math.pi * math.sqrt(L * Cc))
    net = f"V1 in 0 AC 1\nL1 in a {L!r}\nC1 a out {Cc!r}\nR1 out 0 {Rr!r}"
    h = at(net, f0).voltages["out"][0]  # across R: at resonance L and C cancel -> H = 1
    assert h == pytest.approx(1 + 0j, abs=1e-9)
    # and the peak of a fine sweep sits at f0 (the middle point of 201)
    r = ac(parse(f"t\n{net}\n.ac lin 201 {0.9 * f0!r} {1.1 * f0!r}\n.end"))
    assert r.freqs[np.argmax(np.abs(r.voltages["out"]))] == pytest.approx(f0, rel=1e-9)
    # at resonance i = V/R, so the inductor voltage |i|*w0*L equals Q*V
    q = math.sqrt(L / Cc) / Rr
    assert abs(r.currents["l1"][100]) * math.sqrt(L / Cc) == pytest.approx(q, rel=1e-9)


def test_current_source_ac_phasor():
    # 1 mA at 90 degrees into 1k: v = 1 V at 90 degrees.
    v = at("I1 0 a AC 1m 90\nR1 a 0 1k", 1.0).voltages["a"][0]
    assert v == pytest.approx(1j, abs=1e-12)


def test_dc_value_does_not_leak_into_ac():
    v = at("V1 a 0 DC 5 AC 1\nR1 a 0 1k", 1.0).voltages["a"][0]
    assert v == pytest.approx(1, abs=1e-12)


def test_source_without_ac_spec_is_a_short_in_ac():
    # V2 has no AC part: it is a 0 V source, so b sits at 0 and only V1 drives a.
    r = at("V1 a 0 AC 1\nR1 a b 1k\nV2 b 0 DC 5", 1.0)
    assert r.voltages["b"][0] == 0 and r.currents["v1"][0] == pytest.approx(-1e-3)


def test_floating_node_in_ac_is_reported():
    with pytest.raises(SingularCircuitError, match="no path to ground"):
        at("V1 a 0 AC 1\nR1 a 0 1k\nR2 x y 1k", 1.0)


def test_capacitor_connects_node_in_ac_not_dc():
    # Node b hangs off a capacitor only: fine for AC, floating at DC.
    assert at("V1 a 0 AC 1\nC1 a b 1u\nR1 b 0 1k", 1.0).voltages["b"].shape == (1,)


def test_inductor_across_source_is_fine_in_ac():
    r = at("V1 a 0 AC 1\nL1 a 0 1m", 1000.0)
    assert r.currents["l1"][0] == pytest.approx(1 / (2j * np.pi * 1000 * 1e-3), rel=1e-12)


def test_phase_is_unwrapped():
    z = np.exp(1j * np.radians([170, 190, 210]))  # angle() alone would wrap 190 -> -170
    assert phase_degrees(z) == pytest.approx([170, 190, 210])
