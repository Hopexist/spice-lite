"""Time the nonlinear and adaptive example transients plus one MOSFET AC sweep (best of N, wall clock).

    python benchmarks/bench_examples.py

Complements bench_sparse.py, whose ladders are linear: these exercise the Newton and step-control paths.
"""
import time
from pathlib import Path

from spicelite import parse
from spicelite.analysis.ac import ac
from spicelite.analysis.tran import tran

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def best(fn, repeat: int) -> float:
    times = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return min(times)


def main() -> None:
    print("| workload | time |\n|---|---:|")
    for name in ["diode_rectifier_tran", "cmos_inverter_tran", "stiff_adaptive", "rlc_ring_adaptive"]:
        c = parse((EXAMPLES / f"{name}.cir").read_text())
        print(f"| {name} .tran | {best(lambda: tran(c), 5):.4f} s |")
    c = parse((EXAMPLES / "nmos_common_source.cir").read_text())
    print(f"| nmos_common_source .ac | {best(lambda: ac(c), 20):.4f} s |")


if __name__ == "__main__":
    main()
