"""Bode plots: spicelite overlaid with ngspice."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # write PNGs without needing a display
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .analysis.ac import ac, magnitude_db, phase_degrees  # noqa: E402
from .ngspice import find_ngspice, run_ac  # noqa: E402
from .parser import parse_file  # noqa: E402


def bode(freqs: np.ndarray, mine: np.ndarray, path: str | Path, title: str = "",
         ref_freqs: np.ndarray | None = None, ref: np.ndarray | None = None) -> None:
    """Magnitude (dB) over phase (degrees, unwrapped) vs. log frequency, saved as a PNG.
    `mine` / `ref` are complex transfer values; `ref` (ngspice) is drawn dashed on top."""
    fig, (ax_m, ax_p) = plt.subplots(2, 1, sharex=True, figsize=(7, 6))
    for ax, fn, label in ((ax_m, magnitude_db, "Magnitude (dB)"), (ax_p, phase_degrees, "Phase (deg)")):
        ax.semilogx(freqs, fn(mine), "-", lw=2.5, label="spicelite")
        if ref is not None:
            ax.semilogx(ref_freqs, fn(ref), "k--", lw=1.2, label="ngspice")
        ax.set_ylabel(label)
        ax.grid(True, which="both", alpha=0.3)
    ax_m.set_title(title)
    ax_m.legend()
    ax_p.set_xlabel("Frequency (Hz)")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main(examples_dir: str = "examples", out_dir: str = "docs") -> None:
    """Write docs/bode_<name>.png for each AC example; overlay ngspice if it is installed."""
    Path(out_dir).mkdir(exist_ok=True)
    for name, node in (("rc_lowpass", "out"), ("rl_highpass", "out"), ("rlc_bandpass", "out")):
        path = Path(examples_dir) / f"{name}.cir"
        mine = ac(parse_file(str(path)))
        # Each example has a 1 V AC source, so the node voltage is the transfer function.
        ref = run_ac(path.read_text()) if find_ngspice() else None
        bode(mine.freqs, mine.voltages[node], Path(out_dir) / f"bode_{name}.png", name,
             ref.freqs if ref else None, ref.voltages[node] if ref else None)
        print(f"wrote {out_dir}/bode_{name}.png" + ("" if ref else " (spicelite only: ngspice not found)"))


if __name__ == "__main__":
    main()
