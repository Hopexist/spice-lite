"""Level-1 MOSFET: parsing, the Shichman-Hodges equations against hand calculation, PMOS symmetry,
the inverter switching threshold, Newton convergence, and ngspice agreement."""
import math
import warnings
from pathlib import Path

import numpy as np
import pytest
from scipy.optimize import brentq

from spicelite import Mosfet, MosModel, NetlistError, SingularCircuitError, parse
from spicelite.analysis.ac import ac
from spicelite.analysis.dc import dc_sweep, op
from spicelite.analysis.newton import fetlim, limit_mos, limvds
from spicelite.analysis.tran import tran
from spicelite.elements import mos_eval, mos_threshold
from spicelite.ngspice import find_ngspice, run_ac, run_dc, run_op

EXAMPLES = Path(__file__).parent.parent / "examples"
needs_ngspice = pytest.mark.skipif(
    find_ngspice() is None,
    reason="ngspice not found: put ngspice_con.exe/ngspice.exe on PATH or set NGSPICE=<path to exe>")

NM = "nm NMOS (LEVEL=1 VTO=1 KP=100u LAMBDA=0.02)"
PM = "pm PMOS (LEVEL=1 VTO=-1 KP=50u LAMBDA=0.02)"
TIGHT = "reltol=1e-9 abstol=1e-15 vntol=1e-12"  # ngspice options: make ngspice the accurate side


def nmos(**kw) -> Mosfet:
    """beta = KP W / L = 1 mA/V^2 unless overridden; VTO 1 V."""
    m = MosModel("nm", "nmos", **{"VTO": 1.0, "KP": 100e-6, **kw})
    return Mosfet("m1", "d", "g", "s", "b", "nm", 10e-6, 1e-6, m)


# ---- parsing ------------------------------------------------------------------------------------

def test_parse_mosfet_and_models():
    c = parse(f"t\nM1 d g s b nm W=10u L=2u\nM2 d g s b pm\n.model {NM}\n.model pm PMOS (VTO=-0.7 GAMMA=0.4 PHI=0.7)\n")
    m1, m2 = c.mosfets()
    assert (m1.drain, m1.gate, m1.source, m1.bulk, m1.W, m1.L) == ("d", "g", "s", "b", 1e-5, 2e-6)
    assert m1.model.kind == "nmos" and m1.model.VTO == 1.0 and m1.model.KP == 1e-4 and m1.model.LAMBDA == 0.02
    assert (m2.W, m2.L) == (1e-4, 1e-4)  # ngspice's defaults when W / L are omitted
    assert m2.model.kind == "pmos" and (m2.model.GAMMA, m2.model.PHI, m2.model.KP) == (0.4, 0.7, 2e-5)
    assert m1.model.sign == 1 and m2.model.sign == -1


def test_parameters_may_have_spaces_around_equals_and_any_order():
    m, = parse("t\nM1 d g s b nm L = 2u W = 10u\n.model nm NMOS (kp = 1e-4 vto = 1)\n").mosfets()
    assert (m.W, m.L, m.model.KP, m.model.VTO) == (1e-5, 2e-6, 1e-4, 1.0)


@pytest.mark.parametrize("text,msg", [
    ("M1 d g s nm\n.model nm NMOS (VTO=1)\n", r"line 2: 'm1' needs exactly: drain gate source bulk model"),
    ("M1 d g s b nm extra\n.model nm NMOS (VTO=1)\n", r"line 2: 'm1' needs exactly"),
    ("M1 d g s b nope\n.model nm NMOS (VTO=1)\n", r"line 2: MOSFET 'm1' uses unknown model 'nope'"),
    ("M1 d g s b nm AD=1p\n.model nm NMOS (VTO=1)\n", r"line 2: unsupported MOSFET parameter 'ad=1p'; supported: W, L"),
    ("M1 d g s b nm W=1u W=2u\n.model nm NMOS (VTO=1)\n", r"line 2: duplicate MOSFET parameter 'W'"),
    ("M1 d g s b nm W=0\n.model nm NMOS (VTO=1)\n", r"line 2: 'm1': W must be positive"),
    ("M1 d g s b nm L=-1u\n.model nm NMOS (VTO=1)\n", r"line 2: 'm1': L must be positive"),
    ("M1 d g s b nm\n.model nm NMOS (LEVEL=3 VTO=1)\n", r"line 3: only LEVEL=1"),
    ("M1 d g s b nm\n.model nm NMOS (CGSO=1p)\n", r"line 3: unsupported MOS parameter 'cgso=1p'; supported: LEVEL, VTO, KP"),
    ("M1 d g s b nm\n.model nm NMOS (VTO=1 VTO=2)\n", r"line 3: duplicate model parameter 'VTO'"),
    ("M1 d g s b nm\n.model nm NMOS (KP=-1)\n", r"line 3: MOS model needs KP > 0"),
    ("M1 d g s b nm\n.model nm NMOS (GAMMA=-1)\n", r"line 3: MOS model needs"),
    ("D1 a b nm\nR1 a 0 1k\n.model nm NMOS (VTO=1)\n", r"line 2: diode 'd1' uses model 'nm', which is not a D model"),
    ("M1 d g s b dm\n.model dm D (IS=1e-14)\n", r"line 2: MOSFET 'm1' uses model 'dm', which is not a NMOS/PMOS model"),
    ("M1 d g s b nm\n.model nm BJT (VTO=1)\n", r"line 3: unsupported model type 'bjt'; supported: D, NMOS, PMOS"),
])
def test_parser_errors_have_line_numbers(text, msg):
    with pytest.raises(NetlistError, match=msg):
        parse("title\n" + text)


def test_duplicate_mosfet_names_are_errors():
    with pytest.raises(NetlistError, match="duplicate element name 'm1'"):
        parse("t\nM1 d g s b nm\nm1 d g s b nm\n.model nm NMOS ()\n")


# ---- the device equations, by hand --------------------------------------------------------------
# beta = KP W / L = 100u * 10 = 1 mA/V^2, Vth = 1 V.

def test_cutoff_below_threshold():
    i, gm, gds, gmbs, rev, _ = mos_eval(nmos(), 0.9, 3.0, 0.0)
    assert (i, gm, gds, gmbs, rev) == (0.0, 0.0, 0.0, 0.0, False)


def test_triode_hand_calculation():
    # Vov = 2, Vds = 1 < Vov: i = beta (Vov Vds - Vds^2/2) = 1m (2 - 0.5) = 1.5 mA
    i, gm, gds, _, _, _ = mos_eval(nmos(LAMBDA=0.0), 3.0, 1.0, 0.0)
    assert i == pytest.approx(1.5e-3, rel=1e-12)
    assert gm == pytest.approx(1e-3 * 1.0, rel=1e-12)  # beta Vds
    assert gds == pytest.approx(1e-3 * (2.0 - 1.0), rel=1e-12)  # beta (Vov - Vds)


def test_saturation_hand_calculation():
    # Vov = 2, Vds = 3 >= Vov: i = beta/2 Vov^2 = 2 mA, gm = beta Vov = 2 mS, gds = 0 without lambda
    i, gm, gds, _, _, _ = mos_eval(nmos(LAMBDA=0.0), 3.0, 3.0, 0.0)
    assert (i, gm, gds) == (pytest.approx(2e-3), pytest.approx(2e-3), 0.0)


def test_channel_length_modulation_multiplies_by_one_plus_lambda_vds():
    i, gm, gds, _, _, _ = mos_eval(nmos(LAMBDA=0.05), 3.0, 4.0, 0.0)
    assert i == pytest.approx(2e-3 * (1 + 0.05 * 4.0), rel=1e-12)
    assert gds == pytest.approx(2e-3 * 0.05, rel=1e-12)  # beta/2 Vov^2 lambda
    assert gm == pytest.approx(2e-3 * 1.2, rel=1e-12)


@pytest.mark.parametrize("lam", [0.0, 0.03])
def test_triode_and_saturation_meet_at_vds_equal_vov(lam):
    m = nmos(LAMBDA=lam)
    below, above = mos_eval(m, 3.0, 2.0 - 1e-9, 0.0), mos_eval(m, 3.0, 2.0 + 1e-9, 0.0)
    for k in range(4):  # i, gm, gds, gmbs are continuous across the boundary
        assert below[k] == pytest.approx(above[k], rel=1e-6, abs=1e-11)  # abs: gds = beta * 1e-9 on the triode side


def test_derivatives_match_finite_differences():
    m = nmos(LAMBDA=0.03, GAMMA=0.5, PHI=0.7)
    for vgs, vds, vbs in [(3.0, 1.0, -0.5), (2.0, 4.0, -1.0), (1.4, 0.2, 0.0), (2.5, 3.0, 0.2)]:
        _, gm, gds, gmbs, *_ = mos_eval(m, vgs, vds, vbs)
        h = 1e-6

        def current(k, dv):
            return mos_eval(m, vgs + dv * (k == 0), vds + dv * (k == 1), vbs + dv * (k == 2))[0]

        for k, g in enumerate((gm, gds, gmbs)):
            assert (current(k, h) - current(k, -h)) / (2 * h) == pytest.approx(g, rel=1e-5, abs=1e-12)


def test_body_effect_raises_threshold_when_the_bulk_is_reverse_biased():
    m = MosModel("nm", "nmos", VTO=1.0, GAMMA=0.5, PHI=0.6)
    assert mos_threshold(m, 0.0) == pytest.approx(1.0)
    assert mos_threshold(m, -1.0) == pytest.approx(1.0 + 0.5 * (math.sqrt(1.6) - math.sqrt(0.6)))  # hand value
    assert mos_threshold(m, 0.3) < 1.0  # forward bias lowers it; the continuation stays smooth past PHI
    assert mos_threshold(m, 0.6 + 1e-9) == pytest.approx(mos_threshold(m, 0.6 - 1e-9), abs=1e-7)


def test_negative_vds_reverses_the_channel():
    m = nmos(LAMBDA=0.0)
    # gate 3 V, drain 1 V below the source: the drain pin acts as the source. Relative to it
    # Vgs' = 3 - (-1) = 4, Vds' = 1: triode with Vov' = 3: i = 1m (3 - 0.5) = 2.5 mA, flowing source -> drain
    i, _, _, _, reverse, (vgs_e, vds_e, _) = mos_eval(m, 3.0, -1.0, 0.0)
    assert reverse and (vgs_e, vds_e) == (4.0, 1.0)
    assert i == pytest.approx(2.5e-3, rel=1e-12)


def test_pmos_is_the_mirror_image_of_nmos():
    n = MosModel("nm", "nmos", VTO=1.0, KP=1e-4, LAMBDA=0.02, GAMMA=0.4, PHI=0.7)
    p = MosModel("pm", "pmos", VTO=-1.0, KP=1e-4, LAMBDA=0.02, GAMMA=0.4, PHI=0.7)
    mn, mp = Mosfet("m", "d", "g", "s", "b", "n", 1e-5, 1e-6, n), Mosfet("m", "d", "g", "s", "b", "p", 1e-5, 1e-6, p)
    for v in [(3.0, 1.0, -0.5), (3.0, 4.0, 0.0), (0.5, 2.0, 0.0), (2.0, -1.5, -1.0)]:
        a, b = mos_eval(mn, *v), mos_eval(mp, *(-x for x in v))
        assert b[0] == pytest.approx(-a[0], rel=1e-12, abs=1e-18)  # current negated
        for k in (1, 2, 3):
            assert b[k] == pytest.approx(a[k], rel=1e-12, abs=1e-18)  # conductances keep their sign
        assert a[4] == b[4]


def test_pmos_and_nmos_circuits_are_mirror_images():
    def net(kind, sign):
        vto = 1 if kind == "NMOS" else -1
        return (f"t\nVd d 0 DC {3 * sign}\nVg g 0 DC {2 * sign}\nM1 d g 0 0 m W=10u L=1u\n"
                f".model m {kind} (VTO={vto} KP=100u LAMBDA=0.02)\n")
    n, p = op(parse(net("NMOS", 1))), op(parse(net("PMOS", -1)))
    assert p.currents["vd"] == pytest.approx(-n.currents["vd"], rel=1e-12)
    assert n.currents["vd"] < 0  # a V source feeding the drain current reads negative (SPICE sign)


# ---- limiting helpers --------------------------------------------------------------------------

def test_fetlim_and_limvds_cap_big_jumps():
    assert fetlim(10.0, 0.0, 1.0) == pytest.approx(1.5)  # cutoff -> on: only up to just above threshold
    assert fetlim(2.5, 2.0, 1.0) == 2.5  # a small step in the operating region is untouched
    assert fetlim(20.0, 8.0, 1.0) == 20.0  # a 12 V step is within the allowed vtsthi = |2 (8 - 1)| + 2 = 16
    assert fetlim(30.0, 8.0, 1.0) == 24.0  # but 22 V is capped at the old value + 16
    assert limvds(50.0, 1.0) == 4.0 and limvds(-3.0, 1.0) == -0.5
    assert limvds(100.0, 5.0) == 17.0 and limvds(1.0, 5.0) == 2.0
    new, limited = limit_mos((2.5, 1.0, 0.0), (2.5, 1.0, 0.0), 1.0)
    assert not limited and new == (2.5, 1.0, 0.0)


# ---- circuits: analytic answers -----------------------------------------------------------------

def test_common_source_bias_matches_the_square_law():
    # Vgs = 1.5, Vt = 1, beta = 1 mA/V^2, lambda = 0.02, Rd = 5k. Saturation: Vout = 5 - Rd beta/2 Vov^2 (1 + lambda Vout)
    vov, beta, lam, rd = 0.5, 1e-3, 0.02, 5e3
    k = rd * beta / 2 * vov**2
    vout = (5 - k) / (1 + k * lam)
    c = parse((EXAMPLES / "nmos_common_source.cir").read_text())
    # rel 1e-7: the GMIN conductances (1e-12 S x 4.3 V x 5 kOhm = 2e-8 V) are in the model, as in ngspice
    assert op(c).voltages["out"] == pytest.approx(vout, rel=1e-7)
    assert vout > vov  # really in saturation (Vds > Vov)


def test_common_source_ac_gain_is_minus_gm_times_rd_parallel_ro():
    c = parse((EXAMPLES / "nmos_common_source.cir").read_text())
    vout = op(c).voltages["out"]
    beta, lam, vov = 1e-3, 0.02, 0.5
    gm, gds = beta * vov * (1 + lam * vout), 0.5 * beta * vov**2 * lam
    gain = -gm / (1 / 5e3 + gds)
    low = ac(c).voltages["out"][0]  # 1 kHz: far below the 3 MHz pole
    assert low.real == pytest.approx(gain, rel=1e-3)  # the 10 pF load is still ~0.2 % at 1 kHz
    assert abs(low.imag) < 5e-3 * abs(gain)


def vm_netlist(vtn, vtp, kn, kp, lam, vdd=5.0):
    return (f"t\nVdd vdd 0 DC {vdd}\nVin in 0 DC 0\nMN out in 0 0 nm W=10u L=1u\nMP out in vdd vdd pm W=10u L=1u\n"
            f".model nm NMOS (VTO={vtn} KP={kn} LAMBDA={lam})\n.model pm PMOS (VTO={vtp} KP={kp} LAMBDA={lam})\n"
            f".dc Vin 0 {vdd} 0.001\n")


def crossing(c) -> float:
    r = dc_sweep(c)
    d = r.voltages["out"] - r.sweep
    k = int(np.argmax(d < 0))  # first point where Vout has fallen below Vin
    return float(r.sweep[k - 1] + d[k - 1] / (d[k - 1] - d[k]) * (r.sweep[k] - r.sweep[k - 1]))


def test_inverter_threshold_matches_the_analytic_value():
    # lambda = 0: Vm = (VTn + r (VDD - |VTp|)) / (1 + r), r = sqrt(betap / betan). Both devices are
    # saturated at Vin = Vout = Vm. lambda is kept tiny (1e-4) so the stage keeps a finite gain.
    vtn, vtp, kn, kp = 0.8, -1.2, 100e-6, 220e-6
    r = math.sqrt(kp / kn)
    vm = (vtn + r * (5 - abs(vtp))) / (1 + r)
    assert crossing(parse(vm_netlist(vtn, vtp, kn, kp, 1e-4))) == pytest.approx(vm, abs=2e-3)


def test_inverter_threshold_with_channel_length_modulation_matches_the_exact_equation():
    # With lambda the saturation currents carry (1 + lambda Vds); at Vin = Vout = Vm:
    #   kn (Vm - VTn)^2 (1 + lam Vm) = kp (VDD - Vm - |VTp|)^2 (1 + lam (VDD - Vm))
    vtn, vtp, kn, kp, lam = 0.8, -1.2, 100e-6, 220e-6, 0.05

    def f(v):
        return kn * (v - vtn) ** 2 * (1 + lam * v) - kp * (5 - v - abs(vtp)) ** 2 * (1 + lam * (5 - v))

    vm = brentq(f, vtn + 0.1, 5 - abs(vtp) - 0.1)
    assert crossing(parse(vm_netlist(vtn, vtp, kn, kp, lam))) == pytest.approx(vm, abs=2e-3)


def test_symmetric_inverter_switches_at_half_vdd_and_its_rails_are_clean():
    c = parse((EXAMPLES / "cmos_inverter_vtc.cir").read_text())
    r = dc_sweep(c)
    assert crossing(c) == pytest.approx(2.5, abs=1e-3)
    assert r.voltages["out"][0] == pytest.approx(5.0, abs=1e-8)  # input low: the PMOS pulls out to VDD (GMIN leakage ~1e-9)
    assert r.voltages["out"][-1] == pytest.approx(0.0, abs=1e-8)
    assert np.all(np.diff(r.voltages["out"]) <= 1e-9)  # monotone falling


def test_inverter_transient_swings_rail_to_rail_and_back():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r = tran(parse((EXAMPLES / "cmos_inverter_tran.cir").read_text()))
    out = r.voltages["out"]
    assert out[0] == pytest.approx(5.0, abs=1e-6)  # input low at t = 0
    assert out.min() < 0.01  # pulled to ground while the input is high
    assert out[np.searchsorted(r.time, 25e-9)] > 4.99  # and back up before the next pulse starts at 26 ns
    assert r.cuts == 0


# ---- the fallbacks and the topology errors ------------------------------------------------------

def test_floating_gate_is_reported():
    with pytest.raises(SingularCircuitError, match="no DC path to ground"):
        op(parse(f"t\nVdd d 0 DC 5\nM1 d g 0 0 nm W=10u L=1u\n.model {NM}\n"))


def test_a_node_touching_only_cutoff_devices_is_still_solvable():
    # Both devices are off (the NMOS gate at 0 V, the PMOS gate tied to VDD), so only their GMIN
    # conductances hold `out`: the matrix must not be singular.
    c = parse(f"t\nVdd vdd 0 DC 5\nVin in 0 DC 0\nMN out in 0 0 nm W=10u L=1u\nMP out vdd vdd vdd pm W=10u L=1u\n"
              f".model {NM}\n.model {PM}\n")
    assert 0.0 <= op(c).voltages["out"] <= 5.0


def test_solver_sparse_is_refused_for_mosfet_circuits():
    c = parse((EXAMPLES / "nmos_common_source.cir").read_text())
    with pytest.raises(ValueError, match="diodes or MOSFETs"):
        op(c, solver="sparse")
    assert op(c, solver="auto").voltages == op(c, solver="dense").voltages


# ---- ngspice -----------------------------------------------------------------------------------
# ngspice's LEVEL=1 also has two bulk junction diodes per device. Their GMIN conductance is the only part
# that matters at these biases and spicelite stamps exactly that (elements.py), so ngspice's default gmin
# can be used. Tolerances are fractions of the signal's peak; each records its observed worst case.

def max_gap(mine, ref, tol):
    for kind in ("voltages", "currents"):
        for k, a in getattr(mine, kind).items():
            b = getattr(ref, kind)[k]
            gap = np.abs(a - b).max()
            assert gap <= tol * max(np.abs(b).max(), 1e-12), f"{k}: gap {gap:.3e}, peak {np.abs(b).max():.3e}"


@needs_ngspice
def test_nmos_iv_family_matches_ngspice():
    # Id vs Vds for four gate voltages (one .dc per Vgs). Tolerance 1e-9 of peak; observed 8e-12
    # (the ~1e-14 A junction leakage ngspice has and we do not, over a 1.2 mA peak).
    base = (EXAMPLES / "nmos_iv.cir").read_text()
    for vgs in (1.5, 2.0, 2.5, 3.0):
        text = base.replace("Vgs g 0 DC 2.5", f"Vgs g 0 DC {vgs}")
        max_gap(dc_sweep(parse(text)), run_dc(text, TIGHT), 1e-9)


@needs_ngspice
def test_inverter_vtc_matches_ngspice():
    # Observed worst 3.3e-9 V on v(out) (6.5e-10 of the 5 V swing): the small-signal gain at the switching
    # point is ~1/lambda ~ 50, which amplifies ngspice's own convergence tolerance (tightened here). Tolerance 5e-8.
    text = (EXAMPLES / "cmos_inverter_vtc.cir").read_text()
    max_gap(dc_sweep(parse(text)), run_dc(text, TIGHT), 5e-8)


@needs_ngspice
def test_common_source_op_and_ac_match_ngspice():
    # .op to 1e-9 relative (observed 1e-11); .ac to 1e-6 relative on the complex value (ngspice linearises at its
    # own bias point, so it runs with tightened options as in the diode AC test).
    text = (EXAMPLES / "nmos_common_source.cir").read_text()
    a, b = op(parse(text)), run_op(text)
    for k in a.voltages:
        assert a.voltages[k] == pytest.approx(b.voltages[k], rel=1e-9, abs=1e-12)
    mine, ref = ac(parse(text)), run_ac(text, TIGHT)
    for k in mine.voltages:
        err = np.abs(mine.voltages[k] - ref.voltages[k])
        assert (err <= 1e-6 * np.abs(ref.voltages[k]) + 1e-12).all(), k


BODY = """t
Vdd vdd 0 DC 5
Vg g 0 DC 3
M1 vdd g s 0 nm W=10u L=1u
Rs s 0 10k
.model nm NMOS (LEVEL=1 VTO=1 KP=100u LAMBDA=0.02 GAMMA=0.5 PHI=0.7)
.dc Vg 0 5 0.05
"""


@needs_ngspice
def test_source_follower_with_body_effect_matches_ngspice():
    # The source rises above the grounded bulk, so Vbs < 0 and the threshold climbs (GAMMA 0.5, PHI 0.7).
    mine = dc_sweep(parse(BODY))
    assert mine.voltages["s"].max() > 1.0  # the follower really conducted
    max_gap(mine, run_dc(BODY, TIGHT), 1e-8)


PMOS_NET = """t
Vdd vdd 0 DC 5
Vin in 0 DC 0
MP out in vdd vdd pm W=20u L=1u
Rl out 0 10k
.model pm PMOS (LEVEL=1 VTO=-1 KP=50u LAMBDA=0.02 GAMMA=0.4 PHI=0.7)
.dc Vin 0 5 0.05
"""


@needs_ngspice
def test_pmos_load_matches_ngspice():
    # The sweep takes the PMOS from triode (gate low) through saturation to cutoff.
    mine = dc_sweep(parse(PMOS_NET))
    assert mine.voltages["out"][0] > 1.0
    assert mine.voltages["out"][-1] == pytest.approx(0.0, abs=1e-6)  # off: GMIN leakage x 10k
    max_gap(mine, run_dc(PMOS_NET, TIGHT), 1e-8)


REVERSE = f"""t
Vs s 0 DC 3
Vg g 0 DC 4
M1 d g s 0 nm W=10u L=1u
Rd d 0 1k
.model {NM}
.dc Vs 0 5 0.05
"""


@needs_ngspice
def test_reverse_conduction_swap_matches_ngspice():
    # The labelled source pin rises above the resistor-grounded drain, so Vds < 0 and the channel conducts backwards.
    # shortcut check: the sweep stays at Vs >= 0 because below that the grounded bulk would forward-bias ngspice's
    # bulk-source junction diode, which spicelite reduces to its GMIN (documented limitation).
    max_gap(dc_sweep(parse(REVERSE)), run_dc(REVERSE, TIGHT), 1e-8)
