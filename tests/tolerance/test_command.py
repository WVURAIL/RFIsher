"""``rfisher tolerance {build, bands, show, bias}``."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from rfisher import cli
from rfisher.forecast.radiofisher_bao import model, response
from rfisher.tolerance import table

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "projects" / "chime_bao"


def test_show_prints_the_authenticated_packaged_table(capsys):
    assert cli.main(["tolerance", "show"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "csv_sha256 authenticated" in out[0]
    assert len(out) == 1 + 180
    assert any("refused" in line for line in out)


def test_bands_writes_both_tables_and_their_provenance(tmp_path):
    bands = tmp_path / "bands.csv"
    bands.write_text("band_id,low_mhz,high_mhz\n18,494,500\n33,584,590\n")
    out = tmp_path / "out"
    assert cli.main(["tolerance", "bands", "--project", str(PROJECT),
                     "--bands", str(bands), "--out", str(out)]) == 0
    with (out / "tolerances.csv").open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert [(r["band_id"], r["scenario"]) for r in rows][:2] == [
        ("18", "none"), ("18", "peak1")]
    assert rows[0]["r_tol"] == "0.011958214197006222"
    record = json.loads((out / "tolerances.provenance.json").read_text())
    assert record["bands_sha256"] == table.sha256_file(bands)
    assert record["table_csv_sha256"] == table.sha256_file(model.packaged_table())
    assert record["profile_sha256"] == table.sha256_file(
        PROJECT / "science_model.yaml")


@pytest.mark.parametrize("argv,name", [
    ([], "filter_scenarios_T1yr.csv"),
    (["other.csv"], "other.csv"),
])
def test_build_writes_into_a_directory_or_a_named_file(tmp_path, monkeypatch,
                                                       argv, name):
    seen = {}
    monkeypatch.setattr(model, "RadioFisherBAO",
                        lambda project, **kwargs: seen.update(kwargs) or "model")
    monkeypatch.setattr(table, "build", lambda built, out, accept_new: seen.update(
        model=built, out=out, accept_new=accept_new) or [])
    out = tmp_path / argv[0] if argv else tmp_path
    assert cli.main(["tolerance", "build", "--project", str(PROJECT),
                     "--out", str(out), "--accept-new"]) == 0
    assert seen["out"] == tmp_path / name
    assert seen["accept_new"] is True and seen["model"] == "model"
    assert seen["response_banks_dir"] is None and seen["rf_dir"] is None


def test_build_refuses_a_changed_table_through_the_command(tmp_path,
                                                          monkeypatch):
    def refuse(built, out, accept_new):
        raise ValueError("the rebuilt tolerance table differs")

    monkeypatch.setattr(model, "RadioFisherBAO", lambda project, **kw: None)
    monkeypatch.setattr(table, "build", refuse)
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["tolerance", "build", "--project", str(PROJECT), "--out",
                  str(tmp_path)])
    assert excinfo.value.code == 2


def test_a_table_without_provenance_is_refused(tmp_path):
    bare = tmp_path / "bare.csv"
    bare.write_text("world\n")
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["tolerance", "show", "--table", str(bare)])
    assert excinfo.value.code == 2


def test_bias_runs_the_response_report(monkeypatch):
    seen = []
    monkeypatch.setattr(response, "bias_main",
                        lambda argv, prog: seen.append((argv, prog)) or 0)
    assert cli.main(["tolerance", "bias", "--zeta", "1.0"]) == 0
    assert seen == [(["--zeta", "1.0"], "rfisher tolerance bias")]


def test_tolerance_needs_an_action():
    with pytest.raises(SystemExit):
        cli.main(["tolerance"])


def _recorded_copy(path, **changes):
    """A copy of the packaged table with a sidecar of the current inputs."""
    copy = path
    copy.write_bytes(model.packaged_table().read_bytes())
    record = table.identity(model.RadioFisherBAO(PROJECT), copy,
                            responses=False)
    record.update(changes)
    table.sidecar(copy).write_text(json.dumps(record))
    return copy


def test_show_with_a_project_verifies_the_packaged_table(capsys):
    assert cli.main(["tolerance", "show", "--project", str(PROJECT)]) == 0
    assert "inputs verified" in capsys.readouterr().out.splitlines()[0]


def test_bands_and_show_refuse_a_table_whose_inputs_changed(tmp_path, capsys):
    bands = tmp_path / "bands.csv"
    bands.write_text("band_id,low_mhz,high_mhz\n18,494,500\n")
    current = _recorded_copy(tmp_path / "current.csv")
    assert cli.main(["tolerance", "bands", "--project", str(PROJECT),
                     "--bands", str(bands), "--table", str(current),
                     "--out", str(tmp_path / "out")]) == 0
    stale = _recorded_copy(tmp_path / "stale.csv", profile_sha256="0" * 64)
    for argv in (["bands", "--bands", str(bands), "--out",
                  str(tmp_path / "stale")], ["show"]):
        with pytest.raises(SystemExit) as excinfo:
            cli.main(["tolerance", *argv, "--project", str(PROJECT),
                      "--table", str(stale)])
        assert excinfo.value.code == 2
        assert "profile_sha256" in capsys.readouterr().err
    assert not (tmp_path / "stale").exists()
    # without a project, show checks the table's own digest only
    assert cli.main(["tolerance", "show", "--table", str(stale)]) == 0
    assert "inputs not verified" in capsys.readouterr().out.splitlines()[0]
