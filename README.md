# spice-lite

A small SPICE-style circuit simulator in Python. It parses a subset of the SPICE netlist
format and solves DC operating point, DC sweep, AC small-signal and transient analyses with
Modified Nodal Analysis (MNA), using Newton-Raphson for diodes. Results are checked against ngspice.

**Status:** parser, DC, AC, transient, diodes with Newton-Raphson (DC, AC, transient), `.ic`/UIC, and
controlled sources with op-amps are done. A CLI, sparse solves and CI are next (see the roadmap in `CLAUDE.md`).

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

d = tran(parse(open("examples/diode_rectifier_tran.cir").read()))       # Newton at every time step
print(d.voltages["out"].max(), d.iterations.max(), d.cuts)              # peak, worst Newton iterations, step halvings
```

The ngspice comparison tests skip (with a message) unless ngspice is found: put
`ngspice_con.exe` / `ngspice.exe` on `PATH`, or set the `NGSPICE` environment variable to
the executable.

## Supported

| | |
|---|---|
| Elements | `R`, `C`, `L`, `D` (diode), `V` and `I` (DC, `AC mag [phase_deg]`, `PULSE(...)`, `SIN(...)`), controlled sources `E` (VCVS), `G` (VCCS), `F` (CCCS), `H` (CCVS); an op-amp is an `E` with gain 1e6 |
| Models | `.model name D(IS=.. N=.. RS=..)` (only the diode so far) |
| Directives | `.op`, `.dc source start stop step`, `.ac dec\|oct\|lin`, `.tran tstep tstop [uic]`, `.ic v(node)=value`, `.options method=trap\|be`, `.end` |
| Values | SI suffixes `f p n u m k meg g t`, case-insensitive (`m` = milli, `meg` = mega) |
| Linear circuits | one direct solve (DC), one solve per frequency (AC), LU factored once (transient) |
| Diodes | Newton-Raphson with junction voltage limiting and a gmin-stepping fallback in `.op`/`.dc`; Newton at every step in `.tran` (with step halving); linearised at the bias point in `.ac` |
| Transient methods | trapezoidal (default, 2nd order) and backward Euler (1st order, damped), fixed step |
| Initial state | DC solution, or with `uic` the `.ic` capacitor voltages and zero inductor currents |

Anything else raises a `NetlistError` with the line number. Known limitations:

* `PULSE` needs all seven values; the time step is fixed (a failing diode step is halved internally,
  but output stays on the fixed grid).
* The op-amp model has a flat gain at every frequency (no gain-bandwidth limit, slew rate, saturation or
  input/output impedance); an `F`/`H` can only sense a `V` source's current.
* `.ic` only sets capacitor voltages (a node with no capacitor on it is rejected) and is only used
  with `uic`; without `uic` an `.ic` line is an error rather than being silently ignored.
* A loop made only of voltage sources and capacitors (or inductors and current sources only) has no
  t = 0+ capacitor current / inductor voltage; those histories then start at zero (a `shortcut:` note in `tran.py`).
* Diode model: no breakdown, junction capacitance (`CJO`), transit time (`TT`) or temperature scaling.

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
4. *Warm starts*: a `.dc` sweep starts each point from the previous point's solution, and a transient
   step starts from the previous time point.

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

## Diodes in transient and AC analysis

**Transient.** The linear part of the circuit (resistors, the capacitor and inductor companion models,
source rows) is stamped once per step size; each time step then runs the same Newton loop as `.op`,
starting from the previous time point. Typical cost is 2-4 iterations per step (the worst step in each
example is 6-7). If a step fails to converge it is split into two half steps, recursively, up to 8
times (down to 1/256 of the nominal step) while the output stays on the fixed grid; a failure
after that raises `ConvergenceError` with the time and the unknown still moving. The result reports
`iterations` per step and the total `cuts`.

**AC.** The DC operating point is found with Newton, then each diode is replaced by its small-signal
conductance `g = di/dv` at that bias (`rd = N Vt / Id`), and the usual complex sweep runs. It matches the
analytic divider-with-`rd` response to 1e-9 and ngspice to 6e-11 relative (ngspice linearises at its own
bias point, which is only good to ~1e-4 with its default tolerances, so the comparison tightens it).

| Half-wave rectifier, 10 uF filter | Two-diode clamp, sine in |
|---|---|
| ![](docs/wave_diode_rectifier_tran.png) | ![](docs/wave_diode_clamp_tran.png) |

![](docs/bode_diode_ac.png)

**Trapezoidal ringing at a diode turn-off.** Trapezoidal is not damped. When a diode switches off into a
circuit whose time constant is much shorter than the step, the output undershoots and rings around the
true answer (here below 0 V, which a diode would never allow); backward Euler decays monotonically.

![](docs/diode_ringing.png)

## Controlled sources and op-amps

| | Netlist | Equation | Extra branch unknown? |
|---|---|---|---|
| VCVS | `E name n+ n- nc+ nc- gain` | `v(n+) - v(n-) = gain (v(nc+) - v(nc-))` | yes (a voltage output) |
| VCCS | `G name n+ n- nc+ nc- gm` | current `gm (v(nc+) - v(nc-))` flows `n+ -> source -> n-` | no |
| CCCS | `F name n+ n- Vsense gain` | current `gain i(Vsense)` flows `n+ -> source -> n-` | no (reuses Vsense's) |
| CCVS | `H name n+ n- Vsense rm` | `v(n+) - v(n-) = rm i(Vsense)` | yes (a voltage output) |

All four are linear and memoryless, so they stamp the same real entries in DC, in the complex AC matrix
and in every transient step (a linear transient still factors its matrix once). The stamps are in
`elements.py` with their patterns in the docstrings.

**Sign convention (same as ngspice).** The sense current `i(Vsense)` is the branch current of a `V`
source: positive when current flows *into its + terminal and through it*. A source that delivers power
therefore reads negative. `G` and `F` currents, like an `I` source's, flow from `n+` through the source to
`n-`, so `G1 out 0 in 0 2m` *pulls* current out of node `out` (a positive input gives a negative output).
Reversing the sense source's terminals flips the sign of what `F` and `H` produce. `tests/test_controlled.py`
checks every orientation (both sense orientations, a power-delivering sense source, swapped output and
control terminals) against ngspice.

**Op-amp.** An op-amp is an `E` with a large gain (`E1 out 0 in+ in- 1e6`; `spicelite.opamp()` builds one
with the default `OPAMP_GAIN = 1e6`). I reused the VCVS rather than adding a new element because it needs
no new stamp or solver code and the finite gain makes the *finite-gain error* of a closed loop visible and
testable: the inverting amplifier's gain is `-(R2/R1) / (1 + (1 + R2/R1)/A)`, within 1e-9 of that formula
for A from 1e2 to 1e8, and the error falls as `110/A`. The alternative, a *nullor* (an ideal op-amp that
forces `v(in+) = v(in-)` with an unconstrained output current), is not implemented: it needs its own stamp,
cannot be used open loop, and has no finite-gain error to study.

An op-amp with no feedback path from its output to its inputs (a gain >= 1e3 `E` whose output cannot reach
its control nodes except through ground) raises an `OpenLoopWarning`, because its output is then just
`gain x` the differential input. A floating input is a `SingularCircuitError` naming the node.

### Examples against ngspice

| Inverting amplifier | Integrator | Sallen-Key low-pass |
|---|---|---|
| gain -10, DC + AC + `.dc` | `v(out) = -(1/RC) integral v(in)` | `f0 = 562.7 Hz`, `Q = 1.414` |

![](docs/bode_sallen_key_lp.png)

The Sallen-Key response matches the second-order transfer function to 1e-5 (the follower's finite gain
accounts for the rest); `|H(f0)| = Q` to 1e-5 with phase -90 degrees, and the peak frequency and height
match `f0 sqrt(1 - 1/(2Q^2))` and `Q / sqrt(1 - 1/(4Q^2))`.

![](docs/wave_integrator.png)

Against ngspice: linear DC and `.dc` agree exactly, AC to 3e-15 relative, and transient to 1e-5 of peak
(the O(h^2) trapezoidal error, as for the other RC circuits; the integrator is 5e-7).

## Initial conditions: `.ic` and `uic`

`.tran tstep tstop uic` skips the DC solve and starts from `.ic v(node)=value` capacitor voltages
(unlisted nodes are 0) and zero inductor currents, as in SPICE.

Trapezoidal integration also needs each capacitor's current and each inductor's voltage at t = 0+, not
just the state variables. They are found by solving the circuit at t = 0+ with every capacitor held at
its voltage (as a voltage source) and every inductor at its current (as a current source). This also
fixes a flaw in the first transient version: with a zero-rise step at t = 0, trapezoidal averaged the
capacitor current *before* the step (0) with the one after, which cut it to first order. It now
converges at second order for ideal steps too (error ratio 4.00 per halving of the step).

| RC discharge from `.ic v(out)=5` | RLC ring-down from `.ic v(a)=1` |
|---|---|
| ![](docs/wave_rc_discharge_uic.png) | ![](docs/wave_rlc_uic.png) |

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
cost of being only first-order accurate). The overshoot is large because the input steps at t = 0
and the step is 20 time constants.

![](docs/trap_ringing.png)

Convergence on an RC step response (halving h): backward Euler's error falls ~2x per halving,
trapezoidal's ~4x, for ramped steps and, since the t = 0+ initialisation, for ideal steps as well.
