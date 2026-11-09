"""`.ac` small-signal frequency sweep.

All elements here are linear, so there is nothing to linearise: each frequency is one
complex MNA solve with s = j*omega, driven by the sources' AC phasors.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..circuit import AcSweep, Circuit
from ..mna import solve


@dataclass
class AcResult:
    freqs: np.ndarray  # Hz
    voltages: dict[str, np.ndarray]  # node name -> complex phasor at each frequency
    currents: dict[str, np.ndarray]  # V-source / inductor name -> complex branch current


def ac(circuit: Circuit, sweep: AcSweep | None = None) -> AcResult:
    sweep = sweep or circuit.ac
    if sweep is None:
        raise ValueError("no .ac directive in the circuit and no sweep given")
    freqs = sweep.frequencies()
    X = np.array([solve(circuit, 2 * np.pi * f) for f in freqs])  # (n_freq, n_unknowns)
    idx = circuit.node_index()
    n = len(idx)
    return AcResult(
        freqs,
        {node: X[:, i] for node, i in idx.items()},
        {e.name: X[:, n + k] for k, e in enumerate(circuit.branch_elements())},
    )


def magnitude_db(z: np.ndarray) -> np.ndarray:
    return 20 * np.log10(np.abs(z))


def phase_degrees(z: np.ndarray) -> np.ndarray:
    """Phase in degrees, unwrapped so it doesn't jump by 360 across the +-180 boundary."""
    return np.degrees(np.unwrap(np.angle(z)))
