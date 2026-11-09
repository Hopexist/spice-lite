"""Time the nonlinear and adaptive example transients plus one MOSFET AC sweep (best of N, wall clock).

    python benchmarks/bench_examples.py

Complements bench_sparse.py, whose ladders are linear: these exercise the Newton and step-control paths.
"""
import time
from pathlib import Path
from spicelite import parse
from spicelite.analysis.tran import tran
from spicelite.analysis.ac import ac
for name in ["diode_rectifier_tran", "cmos_inverter_tran", "stiff_adaptive", "rlc_ring_adaptive"]:
    c = parse(Path(f"examples/{name}.cir").read_text())
    ts = []
    for _ in range(5):
        t0 = time.perf_counter(); tran(c); ts.append(time.perf_counter() - t0)
    print(f"| {name} .tran | {min(ts):.4f} s |")
c = parse(Path("examples/nmos_common_source.cir").read_text())
ts = []
for _ in range(20):
    t0 = time.perf_counter(); ac(c); ts.append(time.perf_counter() - t0)
print(f"| nmos_common_source .ac | {min(ts):.4f} s |")
