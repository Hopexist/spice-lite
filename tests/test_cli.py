"""The `spicelite run` command line: output, files, exit codes."""
import csv
import subprocess
import sys
from pathlib import Path

import pytest

import spicelite
from spicelite.cli import main

EXAMPLES = Path(__file__).parent.parent / "examples"
RC_STEP = str(EXAMPLES / "rc_step.cir")


def test_version_and_help(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert f"spicelite {spicelite.__version__}" in capsys.readouterr().out
    with pytest.raises(SystemExit) as e:
        main(["run", "--help"])
    out = capsys.readouterr().out
    assert e.value.code == 0 and "--csv" in out and "--plot" in out and "--solver" in out


def test_op_output_has_the_divider_answer(capsys):
    assert main(["run", str(EXAMPLES / "divider.cir")]) == 0
    cap = capsys.readouterr()
    assert "6.66667" in cap.out  # 10 V * 2k / 3k
    assert "no analysis directive" in cap.err  # the .op fallback is announced, not silent


def test_usage_errors_exit_2(capsys):
    for argv in ([], ["run"], ["run", RC_STEP, "--solver", "magic"], ["bogus"]):
        with pytest.raises(SystemExit) as e:
            main(argv)
        assert e.value.code == 2


def test_missing_file_exits_2(capsys):
    assert main(["run", "no_such_file.cir"]) == 2
    assert "cannot read no_such_file.cir" in capsys.readouterr().err


def test_netlist_error_exits_1_with_line_number(tmp_path, capsys):
    bad = tmp_path / "bad.cir"
    bad.write_text("title\nR1 a b\n.end\n")
    assert main(["run", str(bad)]) == 1
    assert "line 2" in capsys.readouterr().err


def test_singular_circuit_exits_1(tmp_path, capsys):
    bad = tmp_path / "float.cir"
    bad.write_text("title\nV1 a 0 DC 1\nR1 a b 1k\nR2 c d 1k\n.op\n.end\n")  # c-d floats
    assert main(["run", str(bad)]) == 1
    assert "error" in capsys.readouterr().err


def test_csv_and_plots_are_written_per_analysis(tmp_path, capsys):
    assert main(["run", RC_STEP, "--csv", str(tmp_path), "-q", "--plot", str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""  # --quiet
    assert (tmp_path / "rc_step_tran.png").stat().st_size > 1000
    with open(tmp_path / "rc_step_tran.csv") as f:
        rows = list(csv.reader(f))
    assert rows[0][0] == "time" and "v(out)" in rows[0]
    assert float(rows[-1][0]) == pytest.approx(5e-3)  # .tran stops at tstop
    # tau = 1 ms, 2.5 ms pulse: charge to 1 - e^-2.5, then discharge 2.5 ms -> (1 - e^-2.5) e^-2.5 = 0.0754
    # (0.0766 simulated: the 10 us edges delay the discharge slightly)
    assert float(rows[-1][rows[0].index("v(out)")]) == pytest.approx(0.0754, abs=2e-3)


def test_csv_ac_has_mag_and_phase_columns(tmp_path):
    assert main(["run", str(EXAMPLES / "rc_lowpass.cir"), "--csv", str(tmp_path), "-q"]) == 0
    header = (tmp_path / "rc_lowpass_ac.csv").read_text().splitlines()[0].split(",")
    assert "mag_db(v(out))" in header and "phase_deg(v(out))" in header


def test_long_tables_are_abbreviated(capsys):
    assert main(["run", RC_STEP]) == 0
    assert "use --csv DIR to save all" in capsys.readouterr().out


def test_warnings_go_to_stderr_and_exit_0(tmp_path, capsys):
    open_loop = tmp_path / "open.cir"
    open_loop.write_text("t\nV1 in 0 DC 1e-6\nR1 in 0 1k\nE1 out 0 in 0 1e6\nR2 out 0 1k\n.op\n.end\n")
    assert main(["run", str(open_loop)]) == 0
    assert "warning:" in capsys.readouterr().err


def test_solver_choice_does_not_change_the_answer(capsys):
    outs = []
    for solver in ("dense", "sparse"):
        assert main(["run", RC_STEP, "--solver", solver]) == 0
        outs.append(capsys.readouterr().out)
    assert outs[0] == outs[1]


def test_installed_console_script_and_module_entry():
    r = subprocess.run([sys.executable, "-m", "spicelite.cli", "--version"], capture_output=True, text=True)
    assert r.returncode == 0 and spicelite.__version__ in r.stdout


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.cir")), ids=lambda p: p.name)
def test_every_example_runs_through_the_cli(path, capsys):
    assert main(["run", str(path), "-q"]) == 0
