# spice-lite

A small SPICE-style circuit simulator in Python. It parses a subset of the SPICE netlist
format and solves DC operating point, AC small-signal and transient analyses with
Modified Nodal Analysis (MNA). Results are checked against ngspice.

**Status:** Milestones 1-4 done (parser, DC, AC, transient). Controlled sources, diodes and
a CLI are next (see the roadmap in `CLAUDE.md`).

## Install and quick start

```
pip install -e .[dev]
pytest -q
python -m spicelite.plotting      # regenerate the plots in docs/
```

```python
from spicelite import parse
from spicelite.analysis.dc import op
from spicelite.analysis.ac import ac, magnitude_db
from spicelite.analysis.tran import tran

print(op(parse(open("examples/divider.cir").read())).voltages)         # {'in': 10.0, 'out': 6.67}

r = ac(parse(open("examples/rc_lowpass.cir").read()))                   # .ac dec 20 10 100k
print(magnitude_db(r.voltages["out"])[:3])                              # dB at the first points

t = tran(parse(open("examples/rc_step.cir").read()), method="trap")     # or method="be"
print(t.time[-1], t.voltages["out"][-1])
```

The ngspice comparison tests skip (with a message) unless ngspice is found: put
`ngspice_con.exe` / `ngspice.exe` on `PATH`, or set the `NGSPICE` environment variable to
the executable.

## Supported

| | |
|---|---|
| Elements | `R`, `C`, `L`, `V` and `I` (DC, `AC mag [phase_deg]`, `PULSE(...)`, `SIN(...)`) |
| Directives | `.op`, `.ac dec\|oct\|lin`, `.tran tstep tstop`, `.options method=trap\|be`, `.end` |
| Values | SI suffixes `f p n u m k meg g t`, case-insensitive (`m` = milli, `meg` = mega) |
| Transient methods | trapezoidal (default, 2nd order) and backward Euler (1st order, damped), fixed step |

Anything else raises a `NetlistError` with the line number. Known limitations: `PULSE` needs all
seven values; no `.dc` sweep, `.ic`/UIC or controlled sources yet, so a circuit with no DC path to
ground (for example only capacitors) has no initial state and is rejected; the time step is fixed.

## Results vs ngspice

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
