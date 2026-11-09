# spice-lite

A small SPICE-style circuit simulator in Python. It parses a subset of the SPICE netlist
format and solves DC operating point, DC sweep, AC small-signal and transient analyses with
Modified Nodal Analysis (MNA), using Newton-Raphson for diodes. Results are checked against ngspice.

**Status:** Milestones 1-5 done (parser, DC, AC, transient, diodes with Newton-Raphson). Nonlinear
transient, controlled sources and a CLI are next (see the roadmap in `CLAUDE.md`).

## Install and quick start

```
pip install -e .[dev]
pytest -q
python -m spicelite.plotting      # regenerate the plots in docs/
```

```python
from spicelite import parse
from spicelite.analysis.dc import op, dc_sweep
from spicelite.analysis.ac import ac, magnitude_db
from spicelite.analysis.tran import tran

print(op(parse(open("examples/divider.cir").read())).voltages)         # {'in': 10.0, 'out': 6.67}

r = ac(parse(open("examples/rc_lowpass.cir").read()))                   # .ac dec 20 10 100k
print(magnitude_db(r.voltages["out"])[:3])                              # dB at the first points

t = tran(parse(open("examples/rc_step.cir").read()), method="trap")     # or method="be"
print(t.time[-1], t.voltages["out"][-1])

s = dc_sweep(parse(open("examples/diode_clamp.cir").read()))            # .dc V1 -5 5 0.1, Newton per point
print(s.voltages["out"][[0, 50, -1]], s.iterations.max())
```

The ngspice comparison tests skip (with a message) unless ngspice is found: put
`ngspice_con.exe` / `ngspice.exe` on `PATH`, or set the `NGSPICE` environment variable to
the executable.

## Supported

| | |
|---|---|
| Elements | `R`, `C`, `L`, `D` (diode), `V` and `I` (DC, `AC mag [phase_deg]`, `PULSE(...)`, `SIN(...)`) |
| Models | `.model name D(IS=.. N=.. RS=..)` (only the diode so far) |
| Directives | `.op`, `.dc source start stop step`, `.ac dec\|oct\|lin`, `.tran tstep tstop`, `.options method=trap\|be`, `.end` |
| Values | SI suffixes `f p n u m k meg g t`, case-insensitive (`m` = milli, `meg` = mega) |
| Linear DC | direct solve, unchanged by the nonlinear work |
| Nonlinear DC (`.op`, `.dc`) | Newton-Raphson with junction voltage limiting and a gmin-stepping fallback |
| Transient methods | trapezoidal (default, 2nd order) and backward Euler (1st order, damped), fixed step |

Anything else raises a `NetlistError` with the line number. Known limitations:

* Diodes work in `.op` and `.dc` only; `.ac` and `.tran` with a diode raise a clear
  `NotImplementedError` (nonlinear transient is the next milestone).
* `PULSE` needs all seven values; no `.ic`/UIC or controlled sources yet, so a transient needs a DC
  path to ground for its initial state (a circuit of only capacitors is rejected); the time step is fixed.
* Diode model: no breakdown, junction capacitance, transit time or temperature scaling.

## Diodes and Newton-Raphson

A diode's current `i = IS (e^(v/(N Vt)) - 1)` is nonlinear, so MNA cannot solve it in one shot.
Newton-Raphson linearises it around the current guess `v0`: a conductance `g = di/dv` in parallel with
a current source `Ieq = i(v0) - g v0`. Those two terms are stamped into the ordinary MNA matrix
(`elements.stamp_diode`), the now-linear system is solved, and the guess moves to the solution.
This repeats until nothing changes. Linear circuits never enter this loop: they keep the single direct solve.

**Model and defaults.** `IS = 1e-14 A`, `N = 1`, `RS = 0 ohm` unless the `.model` card says otherwise.
Like SPICE, every junction also gets `GMIN = 1e-12 S` in parallel (it dominates the reverse current,
which is `IS + GMIN |v|`), and `Vt = kT/q = 25.8649 mV` at 27 C using ngspice's own constants, so the
numbers can be compared digit for digit. `RS > 0` adds a hidden internal node (`<diode>#int`) with a
resistor, which is not shown in the results.

**What keeps Newton from failing**

1. *Junction voltage limiting* (`pnjlim`, as in SPICE): `e^(v/Vt)` overflows if Newton jumps a junction
   by volts, so a junction can only move up logarithmically per iteration.
2. *Convergence on voltages and currents*: every node voltage must change by less than
   `reltol*|v| + vntol`, every branch current by less than `reltol*|i| + abstol`, and each diode's
   linearised current must match its true current at the new voltage (a nonlinear KCL residual). Defaults
   `reltol = 1e-6`, `vntol = 1e-9 V`, `abstol = 1e-14 A`. Limiting must not have fired, and at least
   two iterations are required.
3. *gmin stepping as the fallback.* If plain Newton fails, a large conductance (1e-2 S) is added from
   every node to ground, which makes the circuit nearly linear and easy to solve; it is shrunk one decade
   at a time to 1e-12 S and then removed, each stage starting from the previous answer. I chose this over
   *source stepping* (ramping all sources 0 -> 100 %) because the usual diode trouble is nodes that are
   barely defined when junctions are cut off, which gmin fixes directly, and it is ngspice's own first
   fallback. Source stepping is a documented, unimplemented alternative.
4. *Warm starts*: a `.dc` sweep starts each point from the previous point's solution.

A `ConvergenceError` reports the iteration count and the unknown that was still moving the most.
No ordinary diode circuit I tried (series chains of up to 80 diodes at 1000 V, back-to-back diodes
forced with a current source, `IS = 1e-40`, `N = 0.02`) defeated plain Newton with limiting: they took
2 to 16 iterations. The fallback is exercised by capping the iteration count, and the result reports
which strategy (`newton` or `gmin`) produced it.

| Example | `.op` iterations (from zero) | `.dc` iterations per point (max / mean) |
|---|---|---|
| `diode_rectifier_dc.cir` | 7 | 5 / 2.7 |
| `diode_clamp.cir` | 10 | 7 / 3.3 |
| `diode_iv_sweep.cir` | 4 | 4 / 3.1 |

### DC sweeps vs ngspice

Spicelite matches the exact (Lambert-W) single-diode solution to better than 1e-11 relative
(worst of 8 test cases: 2.4e-12). Against ngspice with its
default tolerances the difference is up to 2e-4 of the signal's peak: that is ngspice's `reltol = 1e-3`
stopping early near the diode's knee. With ngspice's tolerances tightened to ours the difference is
below 1e-9.

![](docs/iv_diode.png)

| Rectifier transfer curve | Two-diode clamp |
|---|---|
| ![](docs/transfer_rectifier.png) | ![](docs/transfer_clamp.png) |

## Results vs ngspice (linear analyses)

### AC (Bode, complex values agree with ngspice to better than 1e-12 relative)

| RC lowpass | RL highpass | RLC bandpass |
|---|---|---|
| ![](docs/bode_rc_lowpass.png) | ![](docs/bode_rl_highpass.png) | ![](docs/bode_rlc_bandpass.png) |

### Transient (trapezoidal vs ngspice with tightened tolerances, error curve underneath)

| RC pulse | Underdamped RLC | Sine into RL |
|---|---|---|
| ![](docs/wave_rc_step.png) | ![](docs/wave_rlc_ring.png) | ![](docs/wave_sin_rl.png) |

The gap to ngspice is spicelite's own O(h^2) trapezoidal error: halving the step cuts it 4x.

### Trapezoidal ringing vs backward Euler damping

When the step is much larger than the circuit's time constant, trapezoidal is not damped and
rings around the true answer after a sudden input change; backward Euler stays monotonic (at the
cost of being only first-order accurate).

![](docs/trap_ringing.png)

Convergence on an RC step response (halving h): backward Euler's error falls ~2x per halving,
trapezoidal's ~4x. With an ideal zero-rise step, trapezoidal drops to first order, because the
capacitor current jumps at t = 0 and the trapezoid rule averages it with its pre-step value.
