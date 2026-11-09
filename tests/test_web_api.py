"""The JSON entry point used by the browser: shape, strict JSON, errors with line numbers, guards, warnings."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from spicelite import parse
from spicelite.analysis.ac import ac, magnitude_db
from spicelite.analysis.dc import op
from spicelite.web_api import Limits, run_netlist

ROOT = Path(__file__).parent.parent
EXAMPLES = sorted((ROOT / "examples").glob("*.cir"))
RC = "RC\nV1 in 0 DC 1 AC 1\nR1 in out 1k\nC1 out 0 1u\n.op\n.ac dec 10 10 100k\n.end\n"


def strict(result: dict) -> dict:
    """Round-trip through strict JSON: NaN / Infinity would raise here."""
    return json.loads(json.dumps(result, allow_nan=False))


# ---- every bundled example --------------------------------------------------------------------

@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_every_example_runs_and_is_strict_json(path):
    r = strict(run_netlist(path.read_text()))
    assert r["ok"] is True and r["title"] and r["analyses"]
    for a in r["analyses"]:
        assert a["type"] in ("op", "dc", "ac", "tran")
        assert a["meta"]["runtime_ms"] >= 0 and isinstance(a["meta"]["warnings"], list) and a["meta"]["points"] >= 1
        assert a["signals"], a["type"]
        for s in a["signals"]:
            assert isinstance(s["name"], str) and s["unit"] in ("V", "A", "dB", "deg")
            assert len(s["values"]) == (1 if a["x"] is None else len(a["x"]["values"]))
        if a["x"] is not None:
            assert a["x"]["name"] and a["x"]["unit"] in ("V", "A", "Hz", "s")


def test_the_result_has_one_analysis_per_directive_in_a_fixed_order():
    r = run_netlist(RC.replace(".op\n", ".op\n.dc V1 0 1 0.5\n"))
    assert [a["type"] for a in r["analyses"]] == ["op", "dc", "ac"]


def test_op_values_match_the_direct_analysis():
    text = (ROOT / "examples" / "divider.cir").read_text()
    a = run_netlist(text)["analyses"][0]
    direct = op(parse(text))
    got = {s["name"]: s["values"][0] for s in a["signals"]}
    assert got["v(out)"] == direct.voltages["out"] and got["i(v1)"] == direct.currents["v1"]
    assert a["x"] is None


def test_ac_comes_as_magnitude_phase_pairs_matching_the_direct_analysis():
    a = next(x for x in run_netlist(RC)["analyses"] if x["type"] == "ac")
    direct = ac(parse(RC))
    mag = next(s for s in a["signals"] if s["name"] == "v(out)" and s["part"] == "magnitude")
    ph = next(s for s in a["signals"] if s["name"] == "v(out)" and s["part"] == "phase")
    assert mag["unit"] == "dB" and ph["unit"] == "deg" and a["x"]["log"] is True
    assert np.allclose(mag["values"], magnitude_db(direct.voltages["out"])) and np.allclose(a["x"]["values"], direct.freqs)
    assert ph["values"][-1] < -80  # the RC pole has taken the phase toward -90 degrees by 100 kHz


def test_a_zero_ac_signal_is_null_not_infinity():
    text = (ROOT / "examples" / "nmos_common_source.cir").read_text()  # vdd carries no AC signal
    a = next(x for x in run_netlist(text)["analyses"] if x["type"] == "ac")
    vdd = next(s for s in a["signals"] if s["name"] == "v(vdd)" and s["part"] == "magnitude")
    assert all(v is None for v in vdd["values"])
    json.dumps(a, allow_nan=False)


def test_no_directive_runs_op_with_a_note():
    r = run_netlist((ROOT / "examples" / "divider.cir").read_text())
    assert r["ok"] and r["analyses"][0]["type"] == "op" and "no analysis directive" in r["warnings"][0]["message"]


def test_transient_metadata_and_adaptive_step_counts():
    r = run_netlist((ROOT / "examples" / "stiff_adaptive.cir").read_text())["analyses"][0]
    assert r["type"] == "tran" and r["meta"]["step_control"] == "adaptive" and r["meta"]["steps"] < 250
    assert r["meta"]["method"] == "trap" and r["x"]["unit"] == "s"
    fixed = run_netlist((ROOT / "examples" / "rc_step.cir").read_text())["analyses"][0]
    assert fixed["meta"]["steps"] == 500 and fixed["meta"]["step_control"] == "fixed"


# ---- errors: never raises, line numbers ---------------------------------------------------------

@pytest.mark.parametrize("text,line,fragment", [
    ("bad title\nR1 a b\n.end\n", 2, "needs two nodes and a value"),  # first line after the title
    ("t\nV1 a 0 DC 1\nR1 a 0 1k\nQ1 a 0 0 npn\n", 4, "unsupported element 'q1'"),  # last line
    ("t\nV1 a 0 DC 1\nR1 a 0 abc\n.op\n", 3, "bad value 'abc'"),
    ("t\nR1 a 0 1k\n.noise\n", 3, "unsupported directive '.noise'"),
    ("t\nM1 d g s b nope\n", 2, "unknown model 'nope'"),
])
def test_netlist_errors_return_the_line_number_and_a_message_without_the_prefix(text, line, fragment):
    r = strict(run_netlist(text))
    assert r["ok"] is False and r["error"]["line"] == line and fragment in r["error"]["message"]
    assert not r["error"]["message"].startswith("line ")


@pytest.mark.parametrize("text,fragment", [
    ("", "no elements"),
    ("only a title\n", "no elements"),
    ("t\nV1 a 0 DC 1\nR1 a 0 1k\nR2 b c 1k\n.op\n", "no DC path to ground"),
    ("t\nV1 a 0 DC 1\nV2 a 0 DC 2\n.op\n", "loop of voltage sources"),
])
def test_solver_level_errors_have_no_line_but_a_clear_message(text, fragment):
    r = strict(run_netlist(text))
    assert r["ok"] is False and r["error"]["line"] is None and fragment in r["error"]["message"]


@pytest.mark.parametrize("junk", ["\x00\x01\x02", "\n" * 1000, "R" * 5000, ".tran\n.tran\n",
                                  "t\nR1 a 0 1k\n.ac dec 0 1 10\n", 123, None, b"bytes"])
def test_garbage_in_never_raises(junk):
    r = strict(run_netlist(junk))
    assert r["ok"] is False and isinstance(r["error"]["message"], str)


# ---- guards -------------------------------------------------------------------------------------

def test_netlist_size_limit():
    r = run_netlist("t\n" + "* padding\n" * 30_000 + "R1 a 0 1k\n")
    assert r["ok"] is False and "characters; the limit is 200,000" in r["error"]["message"]


def ladder(n: int, tail: str) -> str:
    lines = (["ladder", "V1 n0 0 DC 1 AC 1"] + [f"R{k} n{k - 1} n{k} 1k" for k in range(1, n + 1)]
             + [f"C{k} n{k} 0 1n" for k in range(1, n + 1)])
    return "\n".join(lines + [tail, ".end"]) + "\n"


def test_node_limit_and_nonlinear_node_limit():
    r = run_netlist(ladder(600, ".op"))
    assert not r["ok"] and "601 nodes; the limit is 500 for circuits" in r["error"]["message"]
    diodes = ("d\nV1 n0 0 DC 1\n" + "".join(f"R{k} n{k - 1} n{k} 1k\n" for k in range(1, 120))
              + "D1 n119 0 dm\n.model dm D\n.op\n")
    r = run_netlist(diodes)
    assert not r["ok"] and "limit is 100 for circuits with diodes or MOSFETs" in r["error"]["message"]
    assert run_netlist(ladder(600, ".op"), {"max_nodes": 1000})["ok"]  # the limit is a parameter


def test_point_and_work_limits_fail_before_running():
    r = run_netlist(RC.replace(".ac dec 10 10 100k", ".ac lin 200000 1 1meg"))
    assert not r["ok"] and "needs 200,000 points; the limit is 100,000" in r["error"]["message"]
    r = run_netlist("t\nV1 a 0 PULSE(0 1 0 1n 1n 1 2)\nR1 a b 1k\nC1 b 0 1u\n.tran 1n 1\n")
    assert not r["ok"] and "tran analysis needs 1,000,000,001 points" in r["error"]["message"]
    r = run_netlist(ladder(300, ".ac lin 5000 1 1meg"))
    assert not r["ok"] and "too large" in r["error"]["message"] and "exceeds the limit of 2,000,000" in r["error"]["message"]


def test_adaptive_transient_gets_a_step_budget_from_the_limits():
    text = "t\nV1 a 0 PULSE(0 1 0 1u 1u 1 2)\nR1 a b 1k\nC1 b 0 1u\n.options step=adaptive\n.tran 1u 1\n"
    r = run_netlist(text, {"max_points": 20})
    assert not r["ok"] and "more than max_steps = 20 accepted steps" in r["error"]["message"]


def test_time_budget_is_checked_before_each_analysis():
    r = run_netlist(RC, {"max_seconds": 0.0})
    assert not r["ok"] and "exceeded its 0 s time budget before the .op analysis" in r["error"]["message"]


def test_unknown_or_bad_options_are_errors():
    assert "unknown option(s): bogus" in run_netlist(RC, {"bogus": 1})["error"]["message"]
    assert "solver must be one of" in run_netlist(RC, {"solver": "fast"})["error"]["message"]
    assert run_netlist(RC, {"solver": "sparse"})["ok"] and Limits().max_nodes == 500


# ---- warnings ---------------------------------------------------------------------------------

def test_resolution_and_open_loop_warnings_are_reported_in_the_metadata():
    coarse = "t\nV1 a 0 PULSE(0 1 0 1u 1u 1m 2m)\nR1 a b 1k\nC1 b 0 1u\n.tran 100u 2m\n"
    meta = run_netlist(coarse)["analyses"][0]["meta"]
    assert any(w["type"] == "ResolutionWarning" and "rise/fall" in w["message"] for w in meta["warnings"])
    openloop = "t\nV1 in 0 DC 1e-6\nR1 in 0 1k\nE1 out 0 in 0 1e6\nR2 out 0 1k\n.op\n"
    meta = run_netlist(openloop)["analyses"][0]["meta"]
    assert any(w["type"] == "OpenLoopWarning" for w in meta["warnings"])


# ---- the CLI is unchanged ---------------------------------------------------------------------

@pytest.mark.parametrize("name", ["divider", "rc_lowpass", "rc_step", "diode_clamp", "nmos_common_source", "stiff_adaptive"])
def test_cli_output_matches_the_golden_text_captured_before_the_web_api_existed(name):
    r = subprocess.run([sys.executable, "-m", "spicelite.cli", "run", str(ROOT / "examples" / f"{name}.cir")],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0
    golden = (ROOT / "tests" / "golden_cli" / f"{name}.txt").read_text()
    assert r.stdout.replace("\r\n", "\n") == golden.replace("\r\n", "\n")


def test_importing_the_web_api_does_not_load_matplotlib_or_the_ngspice_runner():
    code = ("import sys, spicelite.web_api as w; w.run_netlist('t\\nR1 a 0 1k\\nV1 a 0 DC 1\\n.op\\n'); "
            "print([m for m in ('matplotlib', 'spicelite.plotting', 'spicelite.ngspice', 'spicelite.cli')"
            " if m in sys.modules])")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT)
    assert r.stdout.strip() == "[]", r.stdout + r.stderr
