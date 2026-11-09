"""Precompute the ngspice reference curves the web UI overlays on the bundled examples.

    NGSPICE=<path to ngspice> python scripts/gen_reference.py [--out web/public/reference] [examples/foo.cir ...]

For every example, run the same analyses spicelite.web_api runs, through the existing ngspice runner
(spicelite.ngspice), and save ngspice's results INTERPOLATED ONTO spicelite's own x grid, so the browser can
subtract the two directly. The reference is committed data, regenerated here; the page never runs ngspice.

File format (one per example, <name>.json):
    {"example": "rc_lowpass", "ngspice": "ngspice-41", "analyses": [
        {"type": "ac", "x": [...], "signals": [{"name": "v(out)", "part": "magnitude" | "phase" | null, "values": [...]}]}]}
Analyses appear in web_api order (op, dc, ac, tran); non-finite values are null.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

from spicelite.analysis.ac import magnitude_db, phase_degrees
from spicelite.ngspice import find_ngspice, run_ac, run_dc, run_op, run_tran
from spicelite.web_api import run_netlist

ROOT = Path(__file__).resolve().parent.parent
TIGHT = "reltol=1e-9 abstol=1e-15 vntol=1e-12"  # same ngspice options the comparison tests use
# examples whose default ngspice settings would be too slow: ngspice's tmax = tstep * fraction
TRAN_FRACTION = {"stiff_adaptive": 1e4}


def clean(values) -> list:
    """Plain list, 9 significant digits, non-finite -> None (keeps the files small and strict JSON)."""
    return [float(f"{v:.9g}") if math.isfinite(v) else None for v in np.asarray(values, dtype=float).ravel()]


def onto(x_ref, y_ref, x_new):
    """Interpolate ngspice's curve onto spicelite's grid (np.interp clamps outside the range: the grids coincide there)."""
    return np.interp(np.asarray(x_new, dtype=float), np.asarray(x_ref, dtype=float), np.asarray(y_ref, dtype=float))


def reference_for(name: str, text: str, mine: dict) -> list[dict]:
    out = []
    for a in mine["analyses"]:
        kind, sig, x = a["type"], [], []
        if kind == "op":
            r = run_op(text)
            sig = [{"name": f"v({n})", "part": None, "values": clean([v])} for n, v in r.voltages.items()]
            sig += [{"name": f"i({n})", "part": None, "values": clean([v])} for n, v in r.currents.items()]
        elif kind == "ac":
            r = run_ac(text, TIGHT)
            x = a["x"]["values"]
            for group, prefix in ((r.voltages, "v"), (r.currents, "i")):
                for n, z in group.items():
                    with np.errstate(divide="ignore"):
                        mag = magnitude_db(z)
                    mag = np.where(np.isfinite(mag), mag, np.nan)  # an exactly zero signal has no dB value
                    sig.append({"name": f"{prefix}({n})", "part": "magnitude", "values": clean(onto(r.freqs, mag, x))})
                    ph = phase_degrees(z)
                    sig.append({"name": f"{prefix}({n})", "part": "phase", "values": clean(onto(r.freqs, ph, x))})
        else:  # dc and tran: real curves against a sweep value or time
            x = a["x"]["values"]
            if kind == "dc":
                r = run_dc(text, TIGHT)
                grid = r.sweep
            else:
                r = run_tran(text, tmax_fraction=TRAN_FRACTION.get(name, 0.1))
                grid = r.time
            for group, prefix in ((r.voltages, "v"), (r.currents, "i")):
                for n, v in group.items():
                    sig.append({"name": f"{prefix}({n})", "part": None, "values": clean(onto(grid, v, x))})
        out.append({"type": kind, "x": clean(x), "signals": sig})
    return out


def ngspice_version(exe: str) -> str:
    try:
        text = subprocess.run([exe, "-v"], capture_output=True, text=True, timeout=20).stdout
        for line in text.splitlines():
            if "ngspice" in line.lower() and any(ch.isdigit() for ch in line):
                return line.strip().lstrip("*").strip()[:60]
    except Exception:
        pass
    return "ngspice"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("examples", nargs="*", type=Path, help="netlists (default: every examples/*.cir)")
    ap.add_argument("--out", type=Path, default=ROOT / "web" / "public" / "reference")
    args = ap.parse_args()
    exe = find_ngspice()
    if exe is None:
        print("ngspice not found: put it on PATH or set NGSPICE=<path to ngspice>", file=sys.stderr)
        return 2
    version = ngspice_version(exe)
    args.out.mkdir(parents=True, exist_ok=True)
    paths = args.examples or sorted((ROOT / "examples").glob("*.cir"))
    failed = 0
    for path in paths:
        text = path.read_text(encoding="utf-8")
        mine = run_netlist(text)
        if not mine["ok"]:
            print(f"{path.stem}: spicelite failed ({mine['error']['message']}); skipped", file=sys.stderr)
            failed += 1
            continue
        try:
            analyses = reference_for(path.stem, text, mine)
        except Exception as err:  # one bad example must not hide the rest
            print(f"{path.stem}: ngspice failed ({type(err).__name__}: {err}); skipped", file=sys.stderr)
            failed += 1
            continue
        payload = {"example": path.stem, "ngspice": version, "analyses": analyses}
        body = json.dumps(payload, separators=(",", ":"), allow_nan=False)
        (args.out / f"{path.stem}.json").write_text(body, encoding="utf-8")
        print(f"{path.stem}: {len(analyses)} analyses")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
