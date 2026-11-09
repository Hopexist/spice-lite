"""Time dense vs sparse MNA solves on long RC ladders.

    python benchmarks/bench_sparse.py [--sizes 10 100 1000 10000] [--dense-max 10000] [--repeat 3]

An N-section ladder is  V1 - R - R - ... - R  with a capacitor from every internal node to ground,
so it has N + 1 nodes + 1 branch unknown and a tridiagonal-ish matrix (the best case for sparse).
Two workloads: `.op` (one linear solve) and `.tran` (100 trapezoidal steps: one factorisation,
then 100 back-substitutions). Times are best-of-`repeat` wall-clock seconds and include matrix
assembly, because assembly is part of what the sparse path changes.
"""
from __future__ import annotations

import argparse
import time

from spicelite import parse
from spicelite.analysis.dc import op
from spicelite.analysis.tran import tran


def ladder(n: int) -> str:
    lines = [f"RC ladder, {n} sections", "V1 n0 0 DC 1 PULSE(0 1 0 1u 1u 1 2)"]
    for k in range(1, n + 1):
        lines += [f"R{k} n{k - 1} n{k} 1k", f"C{k} n{k} 0 1n"]
    lines += [".op", ".tran 1u 100u", ".end"]
    return "\n".join(lines) + "\n"


def best(fn, repeat: int) -> float:
    times = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return min(times)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sizes", type=int, nargs="+", default=[10, 100, 1000, 10000])
    ap.add_argument("--dense-max", type=int, default=10000, help="skip dense above this many sections")
    ap.add_argument("--repeat", type=int, default=3)
    a = ap.parse_args()
    print("| sections | unknowns | .op dense | .op sparse | speed-up | .tran dense | .tran sparse | speed-up |")
    print("|---:|---:|---:|---:|---:|---:|---:|---:|")
    for n in a.sizes:
        c = parse(ladder(n))
        size = len(c.node_index()) + len(c.branch_elements())
        reps = 1 if n >= 10000 else a.repeat  # a 10k dense solve is slow: once is enough
        row = []
        for run in (lambda s: op(c, solver=s), lambda s: tran(c, solver=s)):
            d = best(lambda: run("dense"), reps) if n <= a.dense_max else None
            s = best(lambda: run("sparse"), reps)
            row += [f"{d:.4f} s" if d is not None else "skipped", f"{s:.4f} s",
                    f"{d / s:.1f}x" if d is not None else "-"]
        print(f"| {n} | {size} | " + " | ".join(row) + " |", flush=True)


if __name__ == "__main__":
    main()
