"""Run ngspice in batch mode and read back results, for validating spicelite."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .analysis.dc import OpResult
from .parser import parse


def find_ngspice() -> str | None:
    """$NGSPICE if set, else ngspice_con / ngspice on PATH (Windows ships either name)."""
    env = os.environ.get("NGSPICE")
    if env:
        return env if Path(env).is_file() else None
    return shutil.which("ngspice_con") or shutil.which("ngspice")


def _run(netlist_text: str, control: str, out_name: str = "out.txt") -> str:
    exe = find_ngspice()
    if exe is None:
        raise FileNotFoundError(
            "ngspice not found: put ngspice_con.exe/ngspice.exe on PATH or set NGSPICE=<path to exe>")
    # Drop the user's .end/.op so ours is the only analysis; keep title and elements.
    lines = [ln for ln in netlist_text.splitlines()
             if ln.strip().lower() not in (".end", ".op")]
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / out_name
        # numdgt=16 -> full double precision in wrdata, needed for 1e-9 comparisons.
        control = control.replace("{out}", out.as_posix())
        text = "\n".join(lines) + f"\n.control\nset numdgt=16\nset wr_vecnames\n{control}\nquit\n.endc\n.end\n"
        cir = Path(d) / "in.cir"
        cir.write_text(text)
        proc = subprocess.run([exe, "-b", str(cir)], capture_output=True, text=True, timeout=60)
        if not out.exists():
            raise RuntimeError(f"ngspice produced no output:\n{proc.stdout}\n{proc.stderr}")
        return out.read_text()


def run_op(netlist_text: str) -> OpResult:
    """ngspice `.op`. wrdata writes (scale, value) column pairs under a header of vector names.

    Sign convention: ngspice's `v1#branch` is the current flowing into the + terminal,
    through the source, out of the - terminal -- the same as spicelite's branch current,
    so no sign flip is needed (a source delivering power reads negative in both).
    """
    circuit = parse(netlist_text)
    nodes = list(circuit.node_index())
    sources = [v.name for v in circuit.voltage_sources()]
    vectors = [f"v({n})" for n in nodes] + [f"{s}#branch" for s in sources]
    data = _run(netlist_text, "op\nwrdata {out} " + " ".join(vectors)).splitlines()[1]
    # Columns come in (scale, value) pairs; the scale repeats, so take every second one.
    values = [float(x) for x in data.split()][1::2]
    return OpResult(dict(zip(nodes, values)), dict(zip(sources, values[len(nodes):])))
