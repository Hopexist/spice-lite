"""Guard for the single stamping path: every element type the parser can produce must be handled by every
analysis (op, dc, ac, fixed and adaptive tran, Newton), or the gap must be an explicit error.

A new element type that is added to the parser but not to elements.STAMPS (or registered as nonlinear
without a Newton linearisation or an AC model) fails here instead of silently stamping nothing.
"""
from dataclasses import dataclass
from typing import get_args

import numpy as np
import pytest

from spicelite import parse
from spicelite.analysis.ac import ac
from spicelite.analysis.dc import dc_sweep, op
from spicelite.analysis.newton import NEWTON_DEVICES
from spicelite.analysis.tran import tran
from spicelite.circuit import Element
from spicelite.elements import STAMPS
from spicelite.mna import stamp_matrix, stamp_sources
from spicelite.parser import ELEMENT_LETTERS

# one netlist line per element letter the parser accepts
SAMPLES = {
    "v": "V1 in 0 DC 1 AC 1 PULSE(0 1 0 1u 1u 5u 10u)",
    "r": "R1 in a 1k",
    "c": "C1 a 0 1n",
    "l": "L1 a b 1m",
    "i": "I1 0 b DC 1m AC 0",
    "d": "D1 b c dm",
    "e": "E1 e 0 a 0 2",
    "g": "G1 0 g a 0 1m",
    "f": "F1 0 f V1 0.5",
    "h": "H1 h 0 V1 100",
    "m": "M1 dd in 0 0 nm",
}
EVERYTHING = "\n".join(["every element type", *SAMPLES.values(),
                        "R2 b 0 1k", "R3 c 0 1k", "R4 e 0 1k", "R5 g 0 1k", "R6 f 0 1k", "R7 h 0 1k",
                        "VDD dd 0 DC 5", ".model dm D", ".model nm NMOS (VTO=0.5 KP=1e-4)",
                        ".dc V1 0 1 0.5", ".ac dec 2 1k 10k", ".tran 1u 10u", ".end"]) + "\n"


def parsed_types() -> set[type]:
    return {type(e) for e in parse(EVERYTHING).elements}


def test_the_sample_netlist_covers_every_element_letter_the_parser_accepts():
    assert set(SAMPLES) == set(ELEMENT_LETTERS), "add a sample line for the new element letter"
    assert parsed_types() == set(get_args(Element)), "the Element union and the parser disagree"


@pytest.mark.parametrize("cls", sorted(get_args(Element), key=lambda c: c.__name__), ids=lambda c: c.__name__)
def test_every_element_type_is_handled_by_every_analysis(cls):
    st = STAMPS.get(cls)
    assert st is not None, f"{cls.__name__} has no entry in elements.STAMPS"
    # op, dc and every transient assemble A through stamp_matrix: a linear matrix part, or Newton
    assert st.matrix is not None or st.newton, f"{cls.__name__}: no matrix stamp and not a Newton device"
    if st.newton:
        assert cls in NEWTON_DEVICES, f"{cls.__name__}: registered as nonlinear but _newton cannot linearise it"
        assert st.small_signal is not None, f"{cls.__name__}: nonlinear but has no small-signal AC model"
    else:
        assert st.small_signal is None  # a linear element's AC behaviour is its matrix stamp at s = j*omega


def test_nonlinear_devices_are_exactly_the_registered_newton_ones():
    c = parse(EVERYTHING)
    assert {type(e) for e in c.nonlinear()} == {cls for cls, st in STAMPS.items() if st.newton}


def test_every_analysis_runs_a_circuit_with_every_element_type():
    c = parse(EVERYTHING)
    results = [op(c).voltages, dc_sweep(c).voltages, ac(c).voltages, tran(c).voltages, tran(c, adaptive=True).voltages]
    for voltages in results:
        assert set(voltages) == set(c.node_index())
        assert all(np.all(np.isfinite(v)) for v in voltages.values())


def test_an_unregistered_element_type_is_an_error_not_a_silent_no_op():
    @dataclass
    class Memristor:
        name: str
        n1: str
        n2: str

    with pytest.raises(TypeError, match="no MNA stamp registered for Memristor"):
        stamp_matrix(np.zeros((1, 1)), {"a": 0}, {}, [Memristor("x1", "a", "0")], 0.0)
    with pytest.raises(TypeError, match="no MNA stamp registered"):
        stamp_sources(np.zeros(1), {"a": 0}, {}, [Memristor("x1", "a", "0")], lambda e: 0.0)
