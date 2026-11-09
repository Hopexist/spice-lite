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
from ..elements import diode_iv, stamp_diode_small_signal
from ..mna import build, check_topology, solve
from .newton import _expand, solve_nonlinear


@dataclass
class AcResult:
    freqs: np.ndarray  # Hz
    voltages: dict[str, np.ndarray]  # node name -> complex phasor at each frequency
    currents: dict[str, np.ndarray]  # V-source / inductor name -> complex branch current


def _diode_solver(circuit: Circuit):
    """(expanded circuit, solve(omega)) for a circuit with diodes, linearised at its DC bias."""
    bias = solve_nonlinear(circuit)
    ex = _expand(circuit)
    idx = bias.idx
    gs = []  # (diode, small-signal conductance at the bias point)
    for d in ex.diodes():
        p, q = idx.get(d.anode), idx.get(d.cathode)
        vd = (bias.x[p] if p is not None else 0.0) - (bias.x[q] if q is not None else 0.0)
        gs.append((d, diode_iv(d.model, vd)[1]))
    check_topology(ex, dc=False)

    def solve_at(omega: float) -> np.ndarray:
        A, b = build(ex, omega, nonlinear_ok=True)
        for d, g in gs:
            stamp_diode_small_signal(A, idx, d, g)
        try:
            return np.linalg.solve(A, b)
        except np.linalg.LinAlgError as err:
            raise SingularCircuitError(f"circuit matrix is singular: {err}") from err

    return ex, solve_at


def ac(circuit: Circuit, sweep: AcSweep | None = None) -> AcResult:
    sweep = sweep or circuit.ac
    if sweep is None:
        raise ValueError("no .ac directive in the circuit and no sweep given")
    freqs = sweep.frequencies()
    if circuit.diodes():
        ex, solve_at = _diode_solver(circuit)
        X = np.array([solve_at(2 * np.pi * f) for f in freqs])
    else:
        ex = circuit
        X = np.array([solve(circuit, 2 * np.pi * f) for f in freqs])  # (n_freq, n_unknowns)
    idx = ex.node_index()
    n = len(idx)
    return AcResult(
        freqs,
        {node: X[:, idx[node]] for node in circuit.node_index()},  # hidden diode-RS nodes left out
        {e.name: X[:, n + k] for k, e in enumerate(circuit.branch_elements())},
    )


def magnitude_db(z: np.ndarray) -> np.ndarray:
    return 20 * np.log10(np.abs(z))


def phase_degrees(z: np.ndarray) -> np.ndarray:
    """Phase in degrees, unwrapped so it doesn't jump by 360 across the +-180 boundary."""
    return np.degrees(np.unwrap(np.angle(z)))
