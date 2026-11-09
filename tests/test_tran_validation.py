"""Bad .tran inputs must raise a clear ValueError, never a raw MemoryError/OverflowError or a silent wrong answer."""
import pytest

from spicelite import parse
from spicelite.analysis.adaptive import StepControl
from spicelite.analysis.tran import tran
from spicelite.circuit import TranSpec

RC = "rc\nV1 1 0 1\nR1 1 2 1k\nC1 2 0 1n\n.tran 1u 5u\n.end\n"
DIODE = "d\nV1 1 0 SIN(0 2 1meg)\nD1 1 2 DM\nR1 2 0 1k\nC1 2 0 1n\n.model DM D\n.tran 10n 2u\n.end\n"


@pytest.mark.parametrize("tstep,tstop", [(float("nan"), 1e-3), (1e-5, float("nan")), (1e-5, float("inf"))])
def test_transpec_rejects_nan_and_inf(tstep, tstop):
    with pytest.raises(ValueError, match="finite"):
        TranSpec(tstep, tstop)


def test_absurd_step_count_is_refused_before_allocating():
    with pytest.raises(ValueError, match="steps"):
        tran(parse(RC), TranSpec(1e-12, 5e-3))


def test_adaptive_hmin_above_tstop_is_refused():
    with pytest.raises(ValueError, match="hmin"):
        tran(parse(RC), adaptive=StepControl(hmin=1.0))


def test_max_iter_below_one_is_refused():
    with pytest.raises(ValueError, match="max_iter"):
        tran(parse(DIODE), max_iter=0)
