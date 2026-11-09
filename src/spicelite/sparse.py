"""Sparse MNA assembly and solving.

An MNA matrix is mostly zeros: each element touches only the rows and columns of its own nodes,
so a node connects to a handful of others no matter how big the circuit is. A dense n x n matrix
costs O(n^2) memory and O(n^3) time to factor; a sparse one costs O(nnz) memory and, for a chain
like an RC ladder, close to O(n) time.

Every stamp in elements.py only ever does `A[i, j] += value` (or `-=`), never reads a stamp back.
`Triplets` exploits that: it accepts the same writes as a dense array, records them as
(row, col, value) triples, and lets scipy sum the duplicates when converting to CSC.
"""
from __future__ import annotations

import numpy as np
from scipy.sparse import coo_matrix, csc_matrix
from scipy.sparse.linalg import splu

from .circuit import SingularCircuitError

# Circuits with at least this many unknowns use the sparse path under solver="auto". Chosen from
# benchmarks/bench_sparse.py: below it, dense LAPACK on a tiny matrix beats sparse bookkeeping.
SPARSE_MIN_SIZE = 60

SOLVERS = ("auto", "dense", "sparse")


def use_sparse(size: int, solver: str) -> bool:
    """Resolve a solver choice ("auto", "dense" or "sparse") for a system of `size` unknowns."""
    if solver not in SOLVERS:
        raise ValueError(f"solver must be one of {', '.join(SOLVERS)}, got {solver!r}")
    return solver == "sparse" or (solver == "auto" and size >= SPARSE_MIN_SIZE)


def check_solver(circuit, solver: str) -> None:
    """Validate `solver`; an explicit "sparse" is refused for diode circuits.
    shortcut: the Newton loop (analysis/newton.py) copies and edits a dense matrix every
    iteration, so diode circuits stay dense; "auto" quietly picks dense for them, "sparse" says no.
    Upgrade by stamping the diode companions into a sparse pattern if big diode circuits matter."""
    use_sparse(0, solver)
    if solver == "sparse" and circuit.diodes():
        raise ValueError("solver='sparse' is not supported for circuits with diodes "
                         "(Newton-Raphson uses dense matrices); use 'dense' or 'auto'")


class Triplets:
    """Write-only stand-in for a dense matrix: `A[i, j] += v` appends (i, j, v)."""

    def __init__(self, size: int, dtype):
        self.size, self.dtype = size, dtype
        self.rows: list[int] = []
        self.cols: list[int] = []
        self.vals: list = []

    def __getitem__(self, ij):
        return 0.0  # the += in a stamp reads this, adds its value and writes the sum back

    def __setitem__(self, ij, value):
        self.rows.append(ij[0])
        self.cols.append(ij[1])
        self.vals.append(value)

    def tocsc(self) -> csc_matrix:
        m = coo_matrix((np.array(self.vals, dtype=self.dtype), (self.rows, self.cols)),
                       shape=(self.size, self.size))
        return m.tocsc()  # duplicate (i, j) entries are summed here


def factor(A: csc_matrix):
    """Sparse LU. `.solve(b)` on the result back-substitutes. A (numerically) singular matrix
    raises SingularCircuitError, like the dense path."""
    try:
        return splu(A)
    except RuntimeError as err:  # scipy: "Factor is exactly singular"
        raise SingularCircuitError(f"circuit matrix is singular: {err}") from err
