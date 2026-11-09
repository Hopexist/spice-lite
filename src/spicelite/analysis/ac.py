"""`.ac` small-signal frequency sweep.

Linear elements need no linearising: each frequency is one complex MNA solve with s = j*omega,
driven by the sources' AC phasors. With diodes, the DC operating point is found first (Newton,
as for `.op`) and each diode is replaced by its small-signal conductance g = di/dv there;
everything else about the sweep is unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..circuit import AcSweep, Circuit, SingularCircuitError
from ..elements import stamp_of
from ..mna import build, check_topology, solve
from ..sparse import check_solver
from .newton import _expand, solve_nonlinear


@dataclass
class AcResult:
    """Complex phasors per node/branch over the frequency grid."""
    freqs: np.ndarray  # Hz
    voltages: dict[str, np.ndarray]  # node name -> complex phasor at each frequency
    currents: dict[str, np.ndarray]  # V-source / inductor name -> complex branch current


def _diode_solver(circuit: Circuit):
    """(expanded circuit, solve(omega)) for a circuit with diodes, linearised at its DC bias."""
    bias = solve_nonlinear(circuit)
    ex = _expand(circuit)
    idx = bias.idx
    # each diode / MOSFET linearised once at the bias, then re-applied at every frequency
    small = [stamp_of(d).small_signal(idx, d, bias.x) for d in ex.nonlinear()]
    check_topology(ex, dc=False)

    def solve_at(omega: float) -> np.ndarray:
        A, b = build(ex, omega, nonlinear_ok=True)
        for stamp in small:
            stamp(A)
        try:
            return np.linalg.solve(A, b)
        except np.linalg.LinAlgError as err:
            raise SingularCircuitError(f"circuit matrix is singular: {err}") from err

    return ex, solve_at


def ac(circuit: Circuit, sweep: AcSweep | None = None, solver: str = "auto") -> AcResult:
    """AC small-signal sweep: one complex MNA solve per frequency (diodes linearised at their DC bias)."""
    check_solver(circuit, solver)
    sweep = sweep or circuit.ac
    if sweep is None:
        raise ValueError("no .ac directive in the circuit and no sweep given")
    freqs = sweep.frequencies()
    if circuit.nonlinear():
        ex, solve_at = _diode_solver(circuit)
        X = np.array([solve_at(2 * np.pi * f) for f in freqs])
    else:
        ex = circuit
        X = np.array([solve(circuit, 2 * np.pi * f, solver=solver) for f in freqs])  # (n_freq, n_unknowns)
    idx = ex.node_index()
    n = len(idx)
    return AcResult(
        freqs,
        {node: X[:, idx[node]] for node in circuit.node_index()},  # hidden diode-RS nodes left out
        {e.name: X[:, n + k] for k, e in enumerate(circuit.branch_elements())},
    )


def magnitude_db(z: np.ndarray) -> np.ndarray:
    """20 log10 |z|; an exactly zero value (a node with no AC signal, e.g. a supply rail) is -inf dB."""
    with np.errstate(divide="ignore"):
        return 20 * np.log10(np.abs(z))


def phase_degrees(z: np.ndarray) -> np.ndarray:
    """Phase in degrees, unwrapped so it doesn't jump by 360 across the +-180 boundary."""
    return np.degrees(np.unwrap(np.angle(z)))
