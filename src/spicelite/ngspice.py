"""Run ngspice in batch mode and read back results, for validating spicelite."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from .analysis.ac import AcResult
from .analysis.dc import OpResult
from .parser import parse


def find_ngspice() -> str | None:
    """$NGSPICE if set, else ngspice_con / ngspice on PATH (Windows ships either name)."""
    env = os.environ.get("NGSPICE")
    if env:
        return env if Path(env).is_file() else None
    return shutil.which("ngspice_con") or shutil.which("ngspice")


def _run(netlist_text: str, control: str) -> list[list[float]]:
    """Run `control` (ngspice commands, {out} = wrdata target) on the netlist; return the
    numeric rows of the wrdata file (the header line is dropped)."""
    exe = find_ngspice()
    if exe is None:
        raise FileNotFoundError(
            "ngspice not found: put ngspice_con.exe/ngspice.exe on PATH or set NGSPICE=<path to exe>")
    # Drop the user's analysis cards so ours (in the .control block) is the only one.
    lines = [ln for ln in netlist_text.splitlines()
             if (ln.split() or [""])[0].lower() not in (".end", ".op", ".ac")]
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out.txt"
        # numdgt=16 -> full double precision in wrdata, needed for tight comparisons.
        control = control.replace("{out}", out.as_posix())
        text = "\n".join(lines) + f"\n.control\nset numdgt=16\nset wr_vecnames\n{control}\nquit\n.endc\n.end\n"
        cir = Path(d) / "in.cir"
        cir.write_text(text)
        proc = subprocess.run([exe, "-b", str(cir)], capture_output=True, text=True, timeout=60)
        if not out.exists():
            raise RuntimeError(f"ngspice produced no output:\n{proc.stdout}\n{proc.stderr}")
        return [[float(x) for x in row.split()] for row in out.read_text().splitlines()[1:]]


def _vectors(circuit) -> tuple[list[str], list[str], list[str]]:
    nodes = list(circuit.node_index())
    branches = [e.name for e in circuit.branch_elements()]
    return nodes, branches, [f"v({n})" for n in nodes] + [f"{s}#branch" for s in branches]


def run_op(netlist_text: str) -> OpResult:
    """ngspice `.op`. wrdata writes (scale, value) column pairs, one pair per requested vector.

    Sign convention: ngspice's `v1#branch` is the current flowing into the + terminal,
    through the source, out of the - terminal -- the same as spicelite's branch current,
    so no sign flip is needed (a source delivering power reads negative in both).
    """
    nodes, branches, vectors = _vectors(parse(netlist_text))
    row = _run(netlist_text, "op\nwrdata {out} " + " ".join(vectors))[0]
    values = row[1::2]  # the scale repeats before each value
    return OpResult(dict(zip(nodes, values)), dict(zip(branches, values[len(nodes):])))


def run_ac(netlist_text: str) -> AcResult:
    """ngspice `.ac` using the netlist's own sweep. For complex vectors wrdata writes
    (frequency, real, imag) per vector, so we rebuild complex values from the columns."""
    circuit = parse(netlist_text)
    if circuit.ac is None:
        raise ValueError("netlist has no .ac directive")
    s = circuit.ac
    nodes, branches, vectors = _vectors(circuit)
    rows = np.array(_run(netlist_text,
                         f"ac {s.kind} {s.points} {s.fstart!r} {s.fstop!r}\n"
                         "wrdata {out} " + " ".join(vectors)))
    z = rows[:, 1::3] + 1j * rows[:, 2::3]
    return AcResult(rows[:, 0], {n: z[:, i] for i, n in enumerate(nodes)},
                    {b: z[:, len(nodes) + i] for i, b in enumerate(branches)})
