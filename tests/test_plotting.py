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


def test_waveform_with_and_without_reference(tmp_path):
    from spicelite.plotting import waveform

    t = np.linspace(0, 5e-3, 50)
    v = 1 - np.exp(-t / 1e-3)
    waveform(t, v, tmp_path / "a.png", "rc", t, v)
    waveform(t, v, tmp_path / "b.png")
    assert (tmp_path / "a.png").read_bytes()[:4] == b"\x89PNG" and (tmp_path / "b.png").stat().st_size > 0


def test_ringing_demo_writes_a_png(tmp_path):
    from spicelite.plotting import ringing_demo

    ringing_demo(tmp_path / "r.png")
    assert (tmp_path / "r.png").read_bytes()[:4] == b"\x89PNG"


def test_sweep_plot_linear_and_log_with_zeros(tmp_path):
    from spicelite.plotting import sweep_plot

    x = np.linspace(0, 1, 30)
    i = np.exp(x * 20) * 1e-9 * (x > 0)  # first point is exactly 0: must not break the log axis
    sweep_plot(x, i, tmp_path / "log.png", "iv", "V", "I", i, logy=True)
    sweep_plot(x, x, tmp_path / "lin.png", "t", "V", "I", x)
    sweep_plot(x, x, tmp_path / "noref.png")
    for n in ("log", "lin", "noref"):
        assert (tmp_path / f"{n}.png").read_bytes()[:4] == b"\x89PNG"
