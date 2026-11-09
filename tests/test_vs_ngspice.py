from pathlib import Path

import numpy as np
import pytest

from spicelite import parse
from spicelite.analysis.ac import ac
from spicelite.analysis.dc import op
from spicelite.analysis.tran import tran
from spicelite.ngspice import find_ngspice, run_ac, run_op, run_tran

EXAMPLES = sorted((Path(__file__).parent.parent / "examples").glob("*.cir"))
AC_EXAMPLES = [p for p in EXAMPLES if parse(p.read_text()).ac is not None]
TRAN_EXAMPLES = [p for p in EXAMPLES if parse(p.read_text()).tran is not None]

# Allowed |spicelite - ngspice| as a FRACTION OF THE SIGNAL'S PEAK, per transient example.
# ngspice runs with reltol=1e-6 and tmax = tstep/10, so it is the accurate side: the gap is
# spicelite's own O(h^2) trapezoidal error (checked: halving spicelite's h on rlc_ring
# shrinks the gap 1.9e-4 -> 4.6e-5 -> 1.0e-5, i.e. 4x per halving). Observed worst case over
# all nodes/currents is 1.1e-5 (rc_step), 2.4e-4 (rlc_ring: ~200 steps per ring period, phase
# error accumulates over ~5 periods) and 1.2e-4 (sin_rl); each tolerance is ~4-5x that.
TRAN_TOL = {"rc_step.cir": 5e-5, "rlc_ring.cir": 1e-3, "sin_rl.cir": 5e-4}

needs_ngspice = pytest.mark.skipif(
    find_ngspice() is None,
    reason="ngspice not found: put ngspice_con.exe/ngspice.exe on PATH or set NGSPICE=<path to exe>")


@needs_ngspice
@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_op_matches_ngspice(path):
    text = path.read_text()
    mine, ref = op(parse(text)), run_op(text)
    assert mine.voltages.keys() == ref.voltages.keys()
    assert mine.currents.keys() == ref.currents.keys()
    # 1e-9 relative: a linear DC solve is a direct LU, so both tools should agree to
    # ~1e-12; abs=1e-15 only covers exact-zero results (e.g. a balanced bridge).
    for name, v in mine.voltages.items():
        assert v == pytest.approx(ref.voltages[name], rel=1e-9, abs=1e-15), name
    for name, i in mine.currents.items():
        assert i == pytest.approx(ref.currents[name], rel=1e-9, abs=1e-15), name


@needs_ngspice
@pytest.mark.parametrize("path", AC_EXAMPLES, ids=lambda p: p.name)
def test_ac_matches_ngspice(path):
    text = path.read_text()
    mine, ref = ac(parse(text)), run_ac(text)
    # Same frequency grid (ngspice multiplies by a step, so it differs by ~1e-15).
    assert np.allclose(mine.freqs, ref.freqs, rtol=1e-9)
    # 1e-6 relative on the COMPLEX values: comparing phase angles would trip on +-180 wrap.
    # atol 1e-12 only matters for values that are essentially zero.
    for kind in ("voltages", "currents"):
        a, b = getattr(mine, kind), getattr(ref, kind)
        assert a.keys() == b.keys()
        for name in a:
            err = np.abs(a[name] - b[name])
            assert (err <= 1e-6 * np.abs(b[name]) + 1e-12).all(), f"{name}: max err {err.max():.3e}"


@needs_ngspice
@pytest.mark.parametrize("path", TRAN_EXAMPLES, ids=lambda p: p.name)
def test_tran_matches_ngspice(path):
    """Trapezoidal (spicelite's default) vs ngspice's default trapezoidal integration.
    Backward Euler is checked against analytic solutions in test_tran.py instead: ngspice
    can't be set to fixed-step BE (its Gear order 1 still picks adaptive steps)."""
    text = path.read_text()
    mine, ref = tran(parse(text), method="trap"), run_tran(text)
    assert mine.voltages.keys() == ref.voltages.keys() and mine.currents.keys() == ref.currents.keys()
    tol = TRAN_TOL[path.name]
    # ngspice chooses its own time points, so put its curve on spicelite's grid.
    for kind in ("voltages", "currents"):
        for name, a in getattr(mine, kind).items():
            b = np.interp(mine.time, ref.time, getattr(ref, kind)[name])
            err, peak = np.abs(a - b).max(), np.abs(b).max()
            assert err <= tol * max(peak, 1e-12), f"{name}: err {err:.3e} vs peak {peak:.3e}"
