"""All results commands route arguments and propagate failures without real campaigns."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from rfisher_results import cli


@pytest.mark.parametrize("command", ["archive", "archive-report", "transfer-points", "census-psd", "estimator-transfer"])
def test_subcommands_have_help_and_reject_missing_inputs(command, capsys):
    with pytest.raises(SystemExit) as result:
        cli.main([command, "--help"])
    assert result.value.code == 0
    assert "usage:" in capsys.readouterr().out
    with pytest.raises(SystemExit) as result:
        cli.main([command])
    assert result.value.code == 2


@pytest.mark.parametrize("errors,expected", [([], 0), ([{"channel": 14, "error": "bad product"}], 1)])
def test_archive_routes_execution_settings_and_returns_pipeline_status(monkeypatch, capsys, errors, expected):
    from rfisher_results.archive import run

    execute = Mock(return_value={"channels": [14, 36], "errors": errors})
    monkeypatch.setattr(run, "run_archive", execute)
    assert cli.main(["archive", "--products", "products", "--out", "result", "--workers", "1",
                     "--replicates", "12", "--seed", "9", "--channels", "14,36"]) == expected
    execute.assert_called_once_with(Path("products"), Path("result"), workers=1, replicates=12,
                                    seed=9, channels=[14, 36])
    assert json.loads(capsys.readouterr().out) == {"channels": [14, 36]}


def test_archive_default_channel_selection_is_unrestricted(monkeypatch):
    from rfisher_results.archive import run

    execute = Mock(return_value={"errors": []})
    monkeypatch.setattr(run, "run_archive", execute)
    assert cli.main(["archive", "--products", "p", "--out", "o"]) == 0
    assert execute.call_args.kwargs["channels"] is None


@pytest.mark.parametrize("preview", [False, True])
def test_report_controls_figure_and_tex_work(monkeypatch, capsys, preview):
    from rfisher_results.archive.report import build

    execute = Mock(return_value={"artifacts": [{"name": "table.tex"}]})
    monkeypatch.setattr(build, "build_report", execute)
    argv = ["archive-report", "--results", "results"]
    if preview:
        argv += ["--no-figures", "--no-tex", "--out", "preview"]
    assert cli.main(argv) == 0
    execute.assert_called_once_with("results", "preview" if preview else None,
                                    figures=not preview, require_tex=not preview)
    assert json.loads(capsys.readouterr().out)["artifacts"] == ["table.tex"]


@pytest.mark.parametrize("conditioning", [False, True])
def test_transfer_points_routes_conditioning_and_bootstrap(monkeypatch, conditioning):
    shards, conditioned, points = object(), object(), object()
    monkeypatch.setattr(cli, "digital_sweep_layout", Mock(return_value="layout"))
    monkeypatch.setattr(cli, "load_evaluations", Mock(return_value=shards))
    monkeypatch.setattr(cli.Conditioning, "from_json", Mock(return_value=conditioned))
    transfer = Mock(return_value=points)
    write = Mock(return_value="points.csv")
    monkeypatch.setattr(cli, "transfer_points", transfer)
    monkeypatch.setattr(cli, "write_points", write)
    argv = ["transfer-points", "--sweep", "sweep", "--out", "out.csv", "--bootstrap-samples", "25"]
    if conditioning:
        argv += ["--conditioning", "conditioning.json"]
    assert cli.main(argv) == 0
    transfer.assert_called_once_with(shards, conditioning=conditioned if conditioning else None, bootstrap_samples=25)
    write.assert_called_once_with(points, Path("out.csv"))


def test_census_command_preserves_explicit_provenance(monkeypatch, capsys):
    configure = Mock()
    render = Mock(return_value="census.pdf")
    monkeypatch.setattr(cli.style, "configure", configure)
    monkeypatch.setattr(cli, "figure_census_psd", render)
    assert cli.main(["census-psd", "--csv", "input.csv", "--out", "census.pdf",
                     "--provenance", "accepted channel cohort", "--no-tex"]) == 0
    configure.assert_called_once_with(require_tex=False)
    render.assert_called_once_with(Path("input.csv"), out=Path("census.pdf"), provenance="accepted channel cohort")
    assert capsys.readouterr().out.strip() == "census.pdf"


def test_estimator_transfer_routes_explicit_calibration(monkeypatch):
    release = object()
    load = Mock(return_value=release)
    render = Mock(return_value="transfer.pdf")
    monkeypatch.setattr(cli.style, "configure", Mock())
    monkeypatch.setattr(cli, "load_release", load)
    monkeypatch.setattr(cli, "figure_estimator_transfer", render)
    assert cli.main(["estimator-transfer", "--release", "release", "--out", "transfer.pdf",
                     "--calibration", "11,100,6000000,0.8", "--title", "Experiment", "--y-min", "-40"]) == 0
    assert load.call_args.kwargs["calibration"] == cli.Calibration(11, 100, 6000000, 0.8)
    render.assert_called_once_with(release, out=Path("transfer.pdf"), title="Experiment", y_min_db=-40)
    assert cli._calibration(None) is None
    assert cli._calibration("11,100,6000000") == cli.Calibration(11, 100, 6000000)
    with pytest.raises(SystemExit, match="--calibration takes"):
        cli._calibration("1,2")
