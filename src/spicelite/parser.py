"""Netlist text -> Circuit. Anything unsupported raises NetlistError with a line number."""
from __future__ import annotations

import re

from .circuit import Circuit, CurrentSource, NetlistError, Resistor, VoltageSource

# "meg" must be tried before "m" (milli), or 1meg would parse as 1 milli.
_SUFFIX = {"meg": 1e6, "f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6,
           "m": 1e-3, "k": 1e3, "g": 1e9, "t": 1e12}
_VALUE = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)(meg|[fpnumkgt])?$")


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


def _source_value(tokens: list[str], num: int) -> float:
    """Accept `5` or `DC 5`. AC/PULSE/SIN come in later milestones."""
    args = tokens[3:]
    if args and args[0] == "dc":
        args = args[1:]
    if len(args) != 1:
        raise NetlistError(f"unsupported source spec {' '.join(tokens[3:])!r}", num)
    return parse_value(args[0], num)


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
            raise NetlistError(f"unsupported directive {name!r}", num)
        kind = name[0]
        if kind not in "rvi":
            raise NetlistError(f"unsupported element {name!r}", num)
        if name in seen:
            raise NetlistError(f"duplicate element name {name!r}", num)
        seen.add(name)
        if len(tokens) < 4:
            raise NetlistError(f"{name!r} needs two nodes and a value", num)
        a, b = tokens[1], tokens[2]
        if kind == "r":
            if len(tokens) != 4:
                raise NetlistError(f"{name!r} takes exactly two nodes and a value", num)
            value = parse_value(tokens[3], num)
            if value <= 0:
                raise NetlistError(f"{name!r} must have a positive resistance", num)
            circuit.elements.append(Resistor(name, a, b, value))
        elif kind == "v":
            circuit.elements.append(VoltageSource(name, a, b, _source_value(tokens, num)))
        else:
            circuit.elements.append(CurrentSource(name, a, b, _source_value(tokens, num)))
    return circuit  # shortcut: .end is optional here, require it if strictness matters


def parse_file(path: str) -> Circuit:
    with open(path, encoding="utf-8") as f:
        return parse(f.read())
