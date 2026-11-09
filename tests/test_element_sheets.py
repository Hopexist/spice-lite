"""The web page's "Supported elements" spec sheets (web/src/element-sheets.json) must not drift from the parser:
one sheet per element letter it accepts, every documented example accepted by it, and the documented model defaults
equal to the dataclass defaults."""
import json
import re
from dataclasses import fields
from pathlib import Path

import pytest

from spicelite import parse
from spicelite.circuit import DiodeModel, MosModel
from spicelite.parser import ELEMENT_LETTERS

WEB = Path(__file__).parent.parent / "web" / "src"
RAW = json.loads((WEB / "element-sheets.json").read_text(encoding="utf-8"))
SHEETS = {k: v for k, v in RAW.items() if not k.startswith("_")}

# lines an example needs around it to be a complete netlist (a model, or the V source an F / H senses)
SUPPORT = {"d": ".model dmod D", "m": ".model nm NMOS", "f": "Vs x 0 DC 0", "h": "Vs x 0 DC 0"}


def test_there_is_exactly_one_sheet_per_element_letter_the_parser_accepts():
    assert set(SHEETS) == set(ELEMENT_LETTERS)
    assert all(s["code"] == k.upper() for k, s in SHEETS.items())


def test_every_symbol_a_sheet_names_is_drawn():
    drawn = set(re.findall(r"^\s+(\w+): wrap\(", (WEB / "symbols.ts").read_text(encoding="utf-8"), re.M))
    assert {s["symbol"] for s in SHEETS.values()} <= drawn


@pytest.mark.parametrize("letter", sorted(SHEETS))
def test_every_documented_example_is_accepted_by_the_parser(letter):
    example = SHEETS[letter]["example"]
    circuit = parse("\n".join(["sheet example", example, SUPPORT.get(letter, ""), ".end"]))
    assert circuit.elements[0].name == example.split()[0].lower()


@pytest.mark.parametrize("letter,model", [("d", DiodeModel), ("m", MosModel)])
def test_documented_model_defaults_match_the_dataclass_defaults(letter, model):
    defaults = {f.name: f.default for f in fields(model)}
    documented = 0
    for name, _unit, default in SHEETS[letter]["params"]:
        for part in (p.strip() for p in name.split(",")):
            if part in defaults:
                assert float(default) == pytest.approx(defaults[part]), part
                documented += 1
    assert documented >= 3
