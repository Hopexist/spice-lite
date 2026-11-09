"""Diode circuits (Newton-Raphson) vs ngspice: `.op` and `.dc` sweeps."""
from pathlib import Path

import numpy as np
import pytest

from spicelite import parse
from spicelite.analysis.dc import dc_sweep, op
from spicelite.ngspice import find_ngspice, run_dc, run_op

EXAMPLES = sorted((Path(__file__).parent.parent / "examples").glob("*.cir"))
DIODE_EXAMPLES = [p for p in EXAMPLES if parse(p.read_text()).diodes()]

needs_ngspice = pytest.mark.skipif(
    find_ngspice() is None,
    reason="ngspice not found: put ngspice_con.exe/ngspice.exe on PATH or set NGSPICE=<path to exe>")

# ngspice with ITS DEFAULT tolerances (reltol 1e-3, vntol 1e-6, abstol 1e-12): it stops iterating
# as soon as the last step is below 1e-3 relative, so ngspice itself is only good to ~1e-4..1e-3
# near a diode's knee. Allowed |spicelite - ngspice| as a FRACTION OF THE SIGNAL'S PEAK, per
# example, over .op and every .dc point, voltages and branch currents. Observed worst cases:
#   rectifier 1.4e-5, clamp 2.1e-4 (the two-diode knee), iv_sweep 1.3e-5; tolerance ~4-5x that.
DEFAULT_TOL = {"diode_rectifier_dc.cir": 5e-5, "diode_clamp.cir": 1e-3, "diode_iv_sweep.cir": 5e-5}
# Pointwise RELATIVE error on currents above 1 uA (the fraction-of-peak test is blind to the
# small currents of a log-scale I-V curve). ngspice's reltol is 1e-3, so up to that is expected;
# observed worst 7.9e-4 (clamp); tolerance 2e-3.
DEFAULT_REL_I = 2e-3
# The same comparison with ngspice's tolerances tightened to ours (reltol 1e-9 ...): now ngspice is
# the accurate side and any disagreement is spicelite's. Observed worst 8e-10 of peak and 1e-9
# pointwise relative; tolerance 5e-9.
TIGHT = "reltol=1e-9 abstol=1e-15 vntol=1e-12"
TIGHT_TOL = 5e-9


def fraction_of_peak_error(mine: dict, ref: dict) -> float:
    return max(np.abs(np.asarray(mine[k]) - np.asarray(ref[k])).max() / max(np.abs(ref[k]).max(), 1e-30)
               for k in mine)


@needs_ngspice
@pytest.mark.parametrize("path", DIODE_EXAMPLES, ids=lambda p: p.name)
def test_diode_op_matches_ngspice_defaults(path):
    text = path.read_text()
    mine, ref = op(parse(text)), run_op(text)
    assert mine.voltages.keys() == ref.voltages.keys() and mine.currents.keys() == ref.currents.keys()
    peak = max(abs(v) for v in [*ref.voltages.values(), *ref.currents.values()])
    err = max(abs(mine.voltages[k] - ref.voltages[k]) for k in mine.voltages)
    err = max(err, *(abs(mine.currents[k] - ref.currents[k]) for k in mine.currents))
    assert err <= DEFAULT_TOL[path.name] * peak, f"err {err:.3e} vs peak {peak:.3e}"


@needs_ngspice
@pytest.mark.parametrize("path", [p for p in DIODE_EXAMPLES if parse(p.read_text()).dc], ids=lambda p: p.name)
def test_diode_dc_sweep_matches_ngspice_defaults(path):
    text = path.read_text()
    mine, ref = dc_sweep(parse(text)), run_dc(text)
    assert np.allclose(mine.sweep, ref.sweep, atol=1e-12)  # same grid
    assert fraction_of_peak_error(mine.voltages, ref.voltages) <= DEFAULT_TOL[path.name]
    assert fraction_of_peak_error(mine.currents, ref.currents) <= DEFAULT_TOL[path.name]
    big = np.abs(ref.currents["v1"]) > 1e-6
    rel = np.abs(mine.currents["v1"] - ref.currents["v1"])[big] / np.abs(ref.currents["v1"])[big]
    assert rel.max() <= DEFAULT_REL_I


@needs_ngspice
@pytest.mark.parametrize("path", [p for p in DIODE_EXAMPLES if parse(p.read_text()).dc], ids=lambda p: p.name)
def test_diode_dc_sweep_matches_tightened_ngspice(path):
    text = path.read_text()
    mine, ref = dc_sweep(parse(text)), run_dc(text, TIGHT)
    assert fraction_of_peak_error(mine.voltages, ref.voltages) <= TIGHT_TOL
    assert fraction_of_peak_error(mine.currents, ref.currents) <= TIGHT_TOL
    big = np.abs(ref.currents["v1"]) > 1e-6
    rel = np.abs(mine.currents["v1"] - ref.currents["v1"])[big] / np.abs(ref.currents["v1"])[big]
    assert rel.max() <= TIGHT_TOL
