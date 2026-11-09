from pathlib import Path

import pytest

from spicelite import parse
from spicelite.analysis.dc import op
from spicelite.ngspice import find_ngspice, run_op

EXAMPLES = sorted((Path(__file__).parent.parent / "examples").glob("*.cir"))

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
