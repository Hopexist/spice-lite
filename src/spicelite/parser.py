"""Netlist text -> Circuit. Anything unsupported raises NetlistError with a line number."""
from __future__ import annotations

import cmath
import math
import re
from decimal import Decimal

from .circuit import (AcSweep, Capacitor, Circuit, CurrentSource, Inductor, NetlistError, Pulse,
                      Resistor, Sin, TranSpec, VoltageSource)

# "meg" must be tried before "m" (milli), or 1meg would parse as 1 milli.
_SUFFIX = {"meg": 6, "f": -15, "p": -12, "n": -9, "u": -6, "m": -3, "k": 3, "g": 9, "t": 12}  # powers of 10
_VALUE = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)(meg|[fpnumkgt])?$")
_WAVE = re.compile(r"\b(pulse|sin)\s*\(([^)]*)\)")
_METHOD = re.compile(r"method=(trap|be)")
_TWO_TERMINAL = {"r": (Resistor, "resistance"), "c": (Capacitor, "capacitance"),
                 "l": (Inductor, "inductance")}


def parse_value(text: str, line: int | None = None) -> float:
    """'4.7k' -> 4700.0. Case-insensitive. Unit letters like 'ohm' are rejected, not ignored."""
    m = _VALUE.match(text.lower())
    if not m:
        raise NetlistError(f"bad value {text!r}", line)
    # Scale in decimal so "10u" is exactly the float 1e-05 (10 * 1e-6 would be 9.999999999999999e-06).
    return float(Decimal(m.group(1)).scaleb(_SUFFIX.get(m.group(2), 0)))


def _logical_lines(text: str) -> list[tuple[int, str]]:
    """Strip comments, join '+' continuations. Returns (starting line number, content)."""
    out: list[tuple[int, str]] = []
    for num, raw in enumerate(text.splitlines(), start=1):
        line = raw.split(";", 1)[0].strip()
        if not line or line.startswith("*"):
            continue
        if line.startswith("+"):
            if not out:
                raise NetlistError("continuation line with nothing to continue", num)
            out[-1] = (out[-1][0], out[-1][1] + " " + line[1:])
        else:
            out.append((num, line))
    return out


def _source_values(tokens: list[str], num: int) -> tuple[float, complex]:
    """Source spec -> (dc, ac phasor). Accepts `5`, `DC 5`, `AC 1 [phase_deg]`, `DC 5 AC 1 [phase]`.
    The netlist phase is in degrees; the phasor stores it as radians. PULSE/SIN come later."""
    args = tokens[3:]
    dc, ac, seen, i = 0.0, 0j, set(), 0
    if not args:  # only a PULSE/SIN waveform was given
        return dc, ac
    if args[0] not in ("dc", "ac"):  # bare value means DC
        dc, i = parse_value(args[0], num), 1
        seen.add("dc")
    while i < len(args):
        key = args[i]
        if key not in ("dc", "ac") or key in seen or i + 1 >= len(args):
            raise NetlistError(f"unsupported source spec {' '.join(args)!r}", num)
        seen.add(key)
        value = parse_value(args[i + 1], num)
        i += 2
        if key == "dc":
            dc = value
        else:
            phase = 0.0
            if i < len(args) and args[i] not in ("dc", "ac"):
                phase, i = parse_value(args[i], num), i + 1
            ac = cmath.rect(value, math.radians(phase))
    return dc, ac


def _parse_ac(tokens: list[str], num: int) -> AcSweep:
    if len(tokens) != 5:
        raise NetlistError(".ac needs: .ac dec|lin|oct <points> <fstart> <fstop>", num)
    try:
        points = int(tokens[2])
    except ValueError:
        raise NetlistError(f"number of points must be an integer, got {tokens[2]!r}", num) from None
    try:
        return AcSweep(tokens[1], points, parse_value(tokens[3], num), parse_value(tokens[4], num))
    except ValueError as err:
        raise NetlistError(str(err), num) from None


def _parse_wave(kind: str, arg_text: str, num: int) -> Pulse | Sin:
    """PULSE needs all 7 values (no silent SPICE defaults); SIN takes vo va freq [td theta]."""
    args = [parse_value(a, num) for a in arg_text.replace(",", " ").split()]
    want = (7, 7) if kind == "pulse" else (3, 5)
    if not want[0] <= len(args) <= want[1]:
        usage = "PULSE(v1 v2 td tr tf pw per)" if kind == "pulse" else "SIN(vo va freq [td theta])"
        raise NetlistError(f"expected {usage}, got {len(args)} value(s)", num)
    try:
        return Pulse(*args) if kind == "pulse" else Sin(*args)
    except ValueError as err:
        raise NetlistError(str(err), num) from None


def _parse_tran(tokens: list[str], num: int) -> TranSpec:
    if len(tokens) != 3:
        raise NetlistError(".tran needs: .tran <tstep> <tstop>", num)
    try:
        return TranSpec(parse_value(tokens[1], num), parse_value(tokens[2], num))
    except ValueError as err:
        raise NetlistError(str(err), num) from None


def parse(text: str) -> Circuit:
    # The title is always line 1, even if it looks like a comment or element.
    lines = text.splitlines()
    circuit = Circuit(title=lines[0].strip() if lines else "")
    body = "\n".join(["", *lines[1:]])  # blank first line keeps numbering aligned
    seen: set[str] = set()

    for num, line in _logical_lines(body):
        low, wave = line.lower(), None
        if low[0] in "vi" and (m := _WAVE.search(low)):
            wave = _parse_wave(m.group(1), m.group(2), num)
            low = low[:m.start()] + " " + low[m.end():]
        tokens = low.split()
        name = tokens[0]
        if name.startswith("."):
            if name == ".end":
                return circuit
            if name == ".op":
                if len(tokens) != 1:
                    raise NetlistError(".op takes no arguments", num)
                circuit.op = True
                continue
            if name == ".ac":
                if circuit.ac is not None:
                    raise NetlistError("duplicate .ac directive", num)
                circuit.ac = _parse_ac(tokens, num)
                continue
            if name == ".tran":
                if circuit.tran is not None:
                    raise NetlistError("duplicate .tran directive", num)
                circuit.tran = _parse_tran(tokens, num)
                continue
            if name in (".options", ".option"):
                m = _METHOD.fullmatch("".join(tokens[1:]))
                if not m:
                    raise NetlistError("unsupported option; only 'method=trap' or 'method=be'", num)
                circuit.method = m.group(1)
                continue
            raise NetlistError(f"unsupported directive {name!r}", num)
        kind = name[0]
        if kind not in "rclvi":
            raise NetlistError(f"unsupported element {name!r}", num)
        if name in seen:
            raise NetlistError(f"duplicate element name {name!r}", num)
        seen.add(name)
        if len(tokens) < (3 if wave else 4):
            raise NetlistError(f"{name!r} needs two nodes and a value", num)
        a, b = tokens[1], tokens[2]
        if kind in _TWO_TERMINAL:
            cls, what = _TWO_TERMINAL[kind]
            if len(tokens) != 4:
                raise NetlistError(f"{name!r} takes exactly two nodes and a value", num)
            value = parse_value(tokens[3], num)
            if value <= 0:
                raise NetlistError(f"{name!r} must have a positive {what}", num)
            circuit.elements.append(cls(name, a, b, value))
        else:
            cls = VoltageSource if kind == "v" else CurrentSource
            circuit.elements.append(cls(name, a, b, *_source_values(tokens, num), wave))
    return circuit  # shortcut: .end is optional here, require it if strictness matters


def parse_file(path: str) -> Circuit:
    with open(path, encoding="utf-8") as f:
        return parse(f.read())
