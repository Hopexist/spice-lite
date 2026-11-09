from pathlib import Path

import numpy as np
import pytest

from spicelite import parse
from spicelite.analysis.ac import ac
from spicelite.analysis.dc import op
from spicelite.ngspice import find_ngspice, run_ac, run_op

EXAMPLES = sorted((Path(__file__).parent.parent / "examples").glob("*.cir"))
AC_EXAMPLES = [p for p in EXAMPLES if parse(p.read_text()).ac is not None]

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
