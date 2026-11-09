"""Plots: Bode overlays (AC), waveform overlays and the trapezoidal-ringing demo (transient)."""
from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # write PNGs without needing a display
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .analysis.ac import ac, magnitude_db, phase_degrees  # noqa: E402
from .analysis.dc import dc_sweep  # noqa: E402
from .analysis.tran import ResolutionWarning, tran  # noqa: E402
from .ngspice import find_ngspice, run_ac, run_dc, run_tran  # noqa: E402
from .parser import parse, parse_file  # noqa: E402


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


def waveform(t: np.ndarray, mine: np.ndarray, path: str | Path, title: str = "",
             ref_t: np.ndarray | None = None, ref: np.ndarray | None = None,
             context: np.ndarray | None = None, context_label: str = "input") -> None:
    """Waveform over its error curve. `ref` (ngspice, its own time points) is drawn dashed
    and the error is spicelite minus ngspice interpolated onto spicelite's time grid.
    `context` is an optional faint curve (usually the source) drawn behind for orientation."""
    unit, scale = ("ms", 1e3) if t[-1] >= 1e-3 else ("us", 1e6)
    fig, (ax, ax_e) = plt.subplots(2, 1, sharex=True, figsize=(7, 6),
                                   gridspec_kw={"height_ratios": [3, 1]})
    if context is not None:
        ax.plot(t * scale, context, color="0.7", lw=1.2, label=context_label)
    ax.plot(t * scale, mine, lw=2.5, label="spicelite (trapezoidal)")
    if ref is not None:
        ax.plot(ref_t * scale, ref, "k--", lw=1.2, label="ngspice")
        ax_e.plot(t * scale, mine - np.interp(t, ref_t, ref), color="tab:red", lw=1.2)
    ax.set_ylabel("Voltage (V)")
    ax.set_title(title)
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax_e.set_ylabel("Error (V)")
    ax_e.set_xlabel(f"Time ({unit})")
    ax_e.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def sweep_plot(x: np.ndarray, mine: np.ndarray, path: str | Path, title: str = "", xlabel: str = "",
               ylabel: str = "", ref: np.ndarray | None = None, logy: bool = False,
               err_floor: float = 0.0) -> None:
    """A .dc sweep result over its error curve. `ref` (ngspice, same sweep points) is drawn
    dashed. With logy the curves are |y| on a log axis and the error is RELATIVE, so the
    14-decade diode I-V curve is checked point by point rather than only near its peak. The
    relative error is only drawn where |ref| > err_floor: below ngspice's default abstol
    (1e-12 A) its own currents have no relative accuracy, so those points would just show
    ngspice's tolerance floor."""
    pos = lambda a: np.where(np.abs(a) > 0, np.abs(a), np.nan)  # noqa: E731  (log axes can't show 0)
    fig, (ax, ax_e) = plt.subplots(2, 1, sharex=True, figsize=(7, 6),
                                   gridspec_kw={"height_ratios": [3, 1]})
    draw = ax.semilogy if logy else ax.plot
    draw(x, pos(mine) if logy else mine, lw=2.5, label="spicelite")
    if ref is not None:
        draw(x, pos(ref) if logy else ref, "k--", lw=1.2, label="ngspice")
        err = np.where(np.abs(ref) > err_floor, (mine - ref) / pos(ref), np.nan) if logy else mine - ref
        ax_e.plot(x, err, color="tab:red", lw=1.2)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend()
    ax.grid(True, which="both", alpha=0.3)
    ax_e.set_ylabel("Relative error" if logy else "Error")
    ax_e.set_xlabel(xlabel)
    ax_e.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def diode_ringing_demo(path: str | Path) -> None:
    """Half-wave rectifier into a FAST RC (tau = 10 us) with a 50 us step: when the diode turns
    off the output decays much faster than the step. Trapezoidal undershoots below 0 V and rings
    (the diode would never let it), backward Euler decays monotonically. The reference is the
    same circuit at 0.5 us."""
    net = ("diode ringing\nV1 in 0 DC 0 SIN(0 5 1k)\nD1 in out dm\nC1 out 0 1n\nR1 out 0 10k\n"
           ".model dm D(IS=1e-14 N=1 RS=1)\n.tran {h} 2m\n.end")
    fine = tran(parse(net.format(h="0.5u")))
    trap, be = tran(parse(net.format(h="50u")), method="trap"), tran(parse(net.format(h="50u")), method="be")
    fig, (ax_all, ax_zoom) = plt.subplots(2, 1, figsize=(7, 7))
    for ax, (lo, hi) in ((ax_all, (0, 2e-3)), (ax_zoom, (0.45e-3, 0.8e-3))):
        ax.plot(fine.time * 1e3, fine.voltages["out"], color="0.55", lw=2, label="reference (h = 0.5 us)")
        for r, c, m, lab in ((trap, "tab:red", "o", "trapezoidal (rings below 0 V)"),
                             (be, "tab:blue", "s", "backward Euler (damped)")):
            keep = (r.time >= lo) & (r.time <= hi)
            ax.plot(r.time[keep] * 1e3, r.voltages["out"][keep], m + "-", color=c, ms=4, label=lab)
        ax.axhline(0, color="k", lw=0.6)
        ax.set_xlim(lo * 1e3, hi * 1e3)
        ax.set_ylabel("v(out) (V)")
        ax.grid(True, alpha=0.3)
    ax_zoom.set_ylim(-0.08, 1.0)  # otherwise the axis spans the whole waveform and the 50 mV undershoot vanishes
    ax_all.set_title("Diode turning off into a fast RC (tau = 10 us), step h = 50 us")
    ax_all.legend(fontsize=8)
    ax_zoom.set_xlabel("Time (ms)")
    ax_zoom.set_title("zoom on the turn-off", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def ringing_demo(path: str | Path) -> None:
    """A 0 -> 1 V -> 0 pulse into an RC with the time step 20x the time constant.
    Trapezoidal rings around the true (monotonic) answer; backward Euler just damps."""
    tau, h = 1e-6, 20e-6  # R C = 1 kohm * 1 nF
    # pw just under 5h so round-off in k*h can't move the falling edge by a whole step
    net = (f"ringing demo\nV1 in 0 PULSE(0 1 0 0 0 {5 * h * (1 - 1e-9)!r} 1)\n"
           f"R1 in out 1k\nC1 out 0 1n\n.tran {h!r} {15 * h!r}\n.end")
    circuit = parse(net)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResolutionWarning)  # the ideal edge IS under-resolved: that's the point
        trap, be = tran(circuit, method="trap"), tran(circuit, method="be")
    td = np.linspace(0, 15 * h, 800)
    exact = np.where(td < 5 * h, 1 - np.exp(-td / tau), (1 - np.exp(-5 * h / tau)) * np.exp(-(td - 5 * h) / tau))
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(td * 1e6, exact, color="0.55", lw=2, label="exact response")
    ax.plot(trap.time * 1e6, trap.voltages["out"], "o-", color="tab:red", label="trapezoidal (rings)")
    ax.plot(be.time * 1e6, be.voltages["out"], "s-", color="tab:blue", label="backward Euler (damped)")
    ax.set_xlabel("Time (us)")
    ax.set_ylabel("v(out) (V)")
    ax.set_title(f"Pulse into RC, step h = 20 tau (tau = {tau * 1e6:g} us)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main(examples_dir: str = "examples", out_dir: str = "docs") -> None:
    """Write the docs/ plots; overlay ngspice wherever it is installed."""
    Path(out_dir).mkdir(exist_ok=True)
    have_ngspice = find_ngspice() is not None
    note = "" if have_ngspice else " (spicelite only: ngspice not found)"
    # ngspice linearises diodes at its own bias point, so tighten it (harmless for linear circuits)
    tight = "reltol=1e-9 abstol=1e-15 vntol=1e-12"
    for name, node in (("rc_lowpass", "out"), ("rl_highpass", "out"), ("rlc_bandpass", "out"), ("diode_ac", "a"),
                       ("sallen_key_lp", "out")):
        path = Path(examples_dir) / f"{name}.cir"
        mine = ac(parse_file(str(path)))
        # Each example has a 1 V AC source, so the node voltage is the transfer function.
        ref = run_ac(path.read_text(), tight) if have_ngspice else None
        bode(mine.freqs, mine.voltages[node], Path(out_dir) / f"bode_{name}.png", name,
             ref.freqs if ref else None, ref.voltages[node] if ref else None)
        print(f"wrote {out_dir}/bode_{name}.png{note}")
    # (example, plotted node, faint context node or None)
    for name, node, ctx in (("rc_step", "out", None), ("rlc_ring", "out", None), ("sin_rl", "out", None),
                            ("diode_rectifier_tran", "out", "in"), ("diode_clamp_tran", "out", "in"),
                            ("rc_discharge_uic", "out", None), ("rlc_uic", "a", None),
                            ("integrator", "out", "in")):
        path = Path(examples_dir) / f"{name}.cir"
        mine = tran(parse_file(str(path)))
        ref = run_tran(path.read_text()) if have_ngspice else None
        waveform(mine.time, mine.voltages[node], Path(out_dir) / f"wave_{name}.png", name,
                 ref.time if ref else None, ref.voltages[node] if ref else None,
                 mine.voltages[ctx] if ctx else None, f"v({ctx})")
        print(f"wrote {out_dir}/wave_{name}.png{note}")
    ringing_demo(Path(out_dir) / "trap_ringing.png")
    print(f"wrote {out_dir}/trap_ringing.png")
    diode_ringing_demo(Path(out_dir) / "diode_ringing.png")
    print(f"wrote {out_dir}/diode_ringing.png")
    # (example, plotted signal, sign, output file, title, y label, log scale)
    for name, sig, sign, png, title, ylabel, logy in (
            ("diode_rectifier_dc", "out", 1, "transfer_rectifier", "Diode rectifier transfer curve", "v(out) (V)", False),
            ("diode_clamp", "out", 1, "transfer_clamp", "Two-diode clamp transfer curve", "v(out) (V)", False),
            ("diode_iv_sweep", "v1", -1, "iv_diode", "Diode I-V curve (IS = 1e-14 A, N = 1, RS = 1 ohm)",
             "Diode current (A), log scale", True)):
        path = Path(examples_dir) / f"{name}.cir"
        mine = dc_sweep(parse_file(str(path)))
        ref = run_dc(path.read_text()) if have_ngspice else None
        pick = lambda r: sign * (r.currents if sig == "v1" else r.voltages)[sig]  # noqa: E731
        sweep_plot(mine.sweep, pick(mine), Path(out_dir) / f"{png}.png", title, "V1 (V)", ylabel,
                   pick(ref) if ref else None, logy, err_floor=1e-9)
        print(f"wrote {out_dir}/{png}.png{note}")


if __name__ == "__main__":
    main()
