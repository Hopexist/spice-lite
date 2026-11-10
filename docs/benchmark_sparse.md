# Sparse vs dense benchmark (raw output)

Command: `python benchmarks/bench_sparse.py` (defaults: sizes 10 100 1000 10000, best of 3, 1 for the largest).
Run on Mon Nov 9 2026, the author's Windows 11 laptop, Python 3.12.10, numpy 2.5.4, scipy 1.18.1. Timings include matrix assembly.
Wall-clock times on a laptop vary from run to run (the 1000-section `.op` speed-up was 76.7x in an earlier run and 43.5x here).

| sections | unknowns | .op dense | .op sparse | speed-up | .tran dense | .tran sparse | speed-up | adaptive dense | adaptive sparse | speed-up |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 12 | 0.0004 s | 0.0007 s | 0.6x | 0.0044 s | 0.0041 s | 1.1x | 0.0090 s | 0.0096 s | 0.9x |
| 100 | 102 | 0.0469 s | 0.0014 s | 34.7x | 0.0930 s | 0.0234 s | 4.0x | 0.1092 s | 0.0337 s | 3.2x |
| 1000 | 1002 | 0.5952 s | 0.0137 s | 43.5x | 2.3608 s | 0.2818 s | 8.4x | 2.6496 s | 0.2899 s | 9.1x |
| 10000 | 10002 | 4.5598 s | 0.1211 s | 37.7x | 39.3796 s | 2.5776 s | 15.3x | 68.5861 s | 3.6383 s | 18.9x |
