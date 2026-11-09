"""Netlist text -> Circuit. Anything unsupported raises NetlistError with a line number."""
from __future__ import annotations

import cmath
import math
import re

from .circuit import (AcSweep, Capacitor, Circuit, CurrentSource, Inductor, NetlistError,
                      Resistor, VoltageSource)

# "meg" must be tried before "m" (milli), or 1meg would parse as 1 milli.
_SUFFIX = {"meg": 1e6, "f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6,
           "m": 1e-3, "k": 1e3, "g": 1e9, "t": 1e12}
_VALUE = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)(meg|[fpnumkgt])?$")
_TWO_TERMINAL = {"r": (Resistor, "resistance"), "c": (Capacitor, "capacitance"),
                 "l": (Inductor, "inductance")}


def parse_value(text: str, line: int | None = None) -> float:
    """'4.7k' -> 4700.0. Case-insensitive. Unit letters like 'ohm' are rejected, not ignored."""
    m = _VALUE.match(text.lower())
    if not m:
        raise NetlistError(f"bad value {text!r}", line)
    return float(m.group(1)) * _SUFFIX.get(m.group(2), 1.0)


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


def parse(text: str) -> Circuit:
    # The title is always line 1, even if it looks like a comment or element.
    lines = text.splitlines()
    circuit = Circuit(title=lines[0].strip() if lines else "")
    body = "\n".join(["", *lines[1:]])  # blank first line keeps numbering aligned
    seen: set[str] = set()

    for num, line in _logical_lines(body):
        tokens = line.lower().split()
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
            raise NetlistError(f"unsupported directive {name!r}", num)
        kind = name[0]
        if kind not in "rclvi":
            raise NetlistError(f"unsupported element {name!r}", num)
        if name in seen:
            raise NetlistError(f"duplicate element name {name!r}", num)
        seen.add(name)
        if len(tokens) < 4:
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
            circuit.elements.append(cls(name, a, b, *_source_values(tokens, num)))
    return circuit  # shortcut: .end is optional here, require it if strictness matters


def parse_file(path: str) -> Circuit:
    with open(path, encoding="utf-8") as f:
        return parse(f.read())
