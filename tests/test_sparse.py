"""Sparse assembly and solves must give the dense answers (to round-off) on every example."""
from pathlib import Path

import numpy as np
import pytest

from spicelite import SingularCircuitError, parse
from spicelite.analysis.ac import ac
from spicelite.analysis.dc import dc_sweep, op
from spicelite.analysis.tran import tran
from spicelite.mna import build
from spicelite.sparse import SPARSE_MIN_SIZE, Triplets, use_sparse

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
EXAMPLES = sorted(EXAMPLES_DIR.glob("*.cir"))
LINEAR = [p for p in EXAMPLES if not parse(p.read_text()).nonlinear()]
DIODE = [p for p in EXAMPLES if parse(p.read_text()).nonlinear()]  # diodes and MOSFETs: Newton, so dense

# Dense (LAPACK partial-pivot LU) and sparse (SuperLU, column ordering) are both direct solvers
# on the same matrix, so they differ only by round-off: ~1e-15 relative on these well-scaled
# circuits. 1e-9 relative leaves room for the transient's 100s of accumulated steps; atol covers
# signals that are exactly zero in one solver and ~1e-17 in the other.
RTOL, ATOL = 1e-9, 1e-12


def same(a: dict, b: dict) -> None:
    assert a.keys() == b.keys()
    for k in a:
        assert np.allclose(a[k], b[k], rtol=RTOL, atol=ATOL), k


@pytest.mark.parametrize("path", LINEAR, ids=lambda p: p.name)
def test_dense_and_sparse_agree_on_every_linear_example(path):
    c = parse(path.read_text())
    d, s = op(c, solver="dense"), op(c, solver="sparse")
    same(d.voltages, s.voltages)
    same(d.currents, s.currents)
    if c.dc:
        d, s = dc_sweep(c, solver="dense"), dc_sweep(c, solver="sparse")
        same(d.voltages, s.voltages)
        same(d.currents, s.currents)
    if c.ac:
        d, s = ac(c, solver="dense"), ac(c, solver="sparse")
        same(d.voltages, s.voltages)
        same(d.currents, s.currents)
    if c.tran:
        d, s = tran(c, solver="dense"), tran(c, solver="sparse")
        same(d.voltages, s.voltages)
        same(d.currents, s.currents)


@pytest.mark.parametrize("path", DIODE, ids=lambda p: p.name)
def test_diode_circuits_stay_dense_under_auto_and_refuse_sparse(path):
    c = parse(path.read_text())
    same(op(c, solver="auto").voltages, op(c, solver="dense").voltages)
    with pytest.raises(ValueError, match="diodes"):
        op(c, solver="sparse")


def test_built_matrices_are_identical():
    c = parse((EXAMPLES_DIR / "rlc_bandpass.cir").read_text())
    for omega in (None, 2 * np.pi * 1e3):
        Ad, bd = build(c, omega, solver="dense")
        As, bs = build(c, omega, solver="sparse")
        assert np.array_equal(Ad, As.toarray()) and np.array_equal(bd, bs)


def test_triplets_sum_duplicates_like_dense_accumulation():
    t = Triplets(2, float)
    t[0, 0] += 1.5
    t[0, 0] += 2.0
    t[1, 0] -= 1.0
    assert t.tocsc().toarray().tolist() == [[3.5, 0.0], [-1.0, 0.0]]


def test_solver_choice_validation_and_auto_threshold():
    assert not use_sparse(SPARSE_MIN_SIZE - 1, "auto") and use_sparse(SPARSE_MIN_SIZE, "auto")
    assert use_sparse(2, "sparse") and not use_sparse(10**6, "dense")
    with pytest.raises(ValueError, match="solver"):
        use_sparse(5, "fast")


@pytest.mark.parametrize("solver", ["dense", "sparse"])
def test_floating_node_is_reported_the_same_way(solver):
    c = parse("t\nV1 a 0 DC 1\nR1 a 0 1k\nR2 b c 1k\n.op\n.end\n")
    with pytest.raises(SingularCircuitError):
        op(c, solver=solver)


def test_sparse_matrix_that_is_singular_after_assembly_raises_clearly():
    # two ideal sources in parallel pass no union-find check only if they differ in kind; a VCVS
    # whose output is shorted to its own control makes the row 0 = 0 and reaches the LU stage
    c = parse("t\nV1 a 0 DC 1\nR1 a b 1k\nE1 b 0 b 0 1\n.op\n.end\n")
    for solver in ("dense", "sparse"):
        with pytest.raises(SingularCircuitError):
            op(c, solver=solver)


def ladder(n: int) -> str:
    lines = ["ladder", "V1 n0 0 DC 1 PULSE(0 1 0 1u 1u 1 2)"]
    for k in range(1, n + 1):
        lines += [f"R{k} n{k - 1} n{k} 1k", f"C{k} n{k} 0 1n"]
    return "\n".join(lines + [".tran 1u 50u", ".end"]) + "\n"


def test_large_ladder_dense_equals_sparse_and_auto_picks_sparse():
    c = parse(ladder(300))  # 302 unknowns: above the auto threshold
    d, s, a = (tran(c, solver=x) for x in ("dense", "sparse", "auto"))
    same(d.voltages, s.voltages)
    same(a.voltages, s.voltages)
    # sanity on the physics, not just agreement: a charging RC ladder stays between 0 and the 1 V
    # step and falls off along the line (the far end lags the near end)
    v1, vfar = s.voltages["n1"], s.voltages["n300"]
    assert v1.min() >= -1e-9 and v1.max() <= 1 + 1e-9
    assert v1[-1] > vfar[-1] >= 0


def test_sparse_transient_factors_once(monkeypatch):
    import spicelite.analysis.tran as tr
    calls = []
    real = tr.factor
    monkeypatch.setattr(tr, "factor", lambda A: calls.append(1) or real(A))
    tran(parse(ladder(100)), solver="sparse")
    assert len(calls) == 1
