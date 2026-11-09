from pathlib import Path

import numpy as np

from spicelite.plotting import bode


def test_bode_writes_a_png(tmp_path):
    f = np.logspace(0, 3, 20)
    h = 1 / (1 + 1j * f / 100)
    out = tmp_path / "b.png"
    bode(f, h, out, "rc", f, h)
    assert out.read_bytes()[:4] == b"\x89PNG"


def test_bode_without_reference(tmp_path):
    f = np.logspace(0, 3, 20)
    out = Path(tmp_path) / "b.png"
    bode(f, 1 / (1 + 1j * f / 100), out)
    assert out.stat().st_size > 0
