import json

import pytest

from rfisher import figures, overview, table
from rfisher.cli import main


def fake_forecast(bins, workers=None, cosmology=overview.OVERVIEW_COSMOLOGY):
    """overview.forecast's output shape, without the forecast."""
    return {"sigma_dv": [0.01] * len(bins), "sigma_fs8": [0.02] * len(bins), "cosmology": cosmology,
            "bins": [{"z_min": lo, "z_max": hi, "z_center": 0.5 * (lo + hi)} for lo, hi in bins]}


def fake_row(band, **options):
    return {"channel": band.channel, "role": band.role, "low_mhz": band.low_mhz, "high_mhz": band.high_mhz,
            "z_center": band.z_center, "sigma_dv": 0.01, "response_dv": -1.0e4, "a_tol": 1.0e-4}


def test_figures_for_one_channel(tmp_path, capsys):
    main(["figures", "--out", str(tmp_path), "--channels", "19"])
    printed = capsys.readouterr().out.split()
    assert [p.split("/")[-1] for p in printed] == ["summary.png", "channel_19.png"]
    assert all((tmp_path / n).stat().st_size > 10_000 for n in ("summary.png", "channel_19.png"))


def test_table_for_one_channel(tmp_path, monkeypatch):
    # The forecast is checked in test_table.py. This test checks the command around it.
    monkeypatch.setattr(table, "row", fake_row)
    main(["table", "--out", str(tmp_path), "--channels", "37", "--workers", "1"])
    assert [r["channel"] for r in table.read_table(tmp_path / "channel_table.json")["channels"]] == [37]
    assert (tmp_path / "channel_table.csv").read_text().splitlines()[1].startswith("37,control,")


def test_overview_reference(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(overview, "forecast", fake_forecast)
    main(["overview", "--out", str(tmp_path)])
    printed = [p.split("/")[-1] for p in capsys.readouterr().out.split()]
    assert printed == ["overview_planck2018.json", "overview_reference.png"]
    assert all((tmp_path / n).stat().st_size > 0 for n in printed)
    ref = json.loads((tmp_path / "overview_planck2018.json").read_text())
    assert len(ref["overview_bins"]["bins"]) == 15


@pytest.mark.parametrize("cosmology, label", [("planck2018", "Planck 2018"), ("cmbspa2026", "cmbspa2026")])
def test_the_overview_title_names_its_cosmology(tmp_path, monkeypatch, cosmology, label):
    titles = []
    monkeypatch.setattr(figures.plt.Figure, "savefig", lambda fig, *a, **k: titles.append(fig.get_suptitle()))
    ref = {"cosmology": cosmology, "overview_bins": fake_forecast(overview.overview_bins(), cosmology=cosmology),
           "channels": fake_forecast(overview.channel_bins(), cosmology=cosmology)}
    figures.overview_figure(ref, tmp_path)
    assert titles == [f"CHIME Overview forecast, one clean year ({label}, CHIME, 8,760 h)"]


def test_the_summary_title_names_what_differs_from_the_shipped_table():
    t = table.read_table()
    assert figures.summary_title(t) == ("RFIsher channel table: one RadioFisher forecast per 6 MHz channel, "
                                        "flat additive DTV power, 8,760 retained hours, D_V (cmbspa2026)")
    other = dict(t, channels=[dict(t["channels"][0], high_mhz=472.0), dict(t["channels"][1], high_mhz=479.0)],
                 inputs=dict(t["inputs"], telescope="chord", experiment="CHORD (nominal), all baselines",
                             residual="mymodule:shelf", backend="mymodule:fisher"))
    assert figures.summary_title(other) == ("RFIsher channel table: one mymodule:fisher forecast per channel, "
                                            "residual mymodule:shelf, CHORD (nominal), all baselines, "
                                            "8,760 retained hours, D_V (cmbspa2026)")


def test_figures_use_the_table_exposure(tmp_path, monkeypatch):
    durations = []
    monkeypatch.setattr(figures, "plate", lambda row, out, hours: durations.append(hours) or out / "plate.png")
    t = table.read_table()
    t["inputs"]["retained_hours"] = 100
    figures.draw_all(t, tmp_path, channels={19})
    assert durations == [100]

def test_unknown_requested_channel_is_not_silently_ignored(tmp_path):
    with pytest.raises(SystemExit) as error:
        main(["table", "--out", str(tmp_path), "--channels", "19,99"])
    assert error.value.code == 2


def test_table_options_reach_the_rows(tmp_path, monkeypatch):
    from rfisher import residual
    seen = []
    monkeypatch.setattr(table, "row", lambda band, **options: seen.append(options) or fake_row(band))
    bands = tmp_path / "bands.csv"
    bands.write_text("channel,low_mhz,high_mhz,role\n7,600.0,606.0,test\n")
    main(["table", "--out", str(tmp_path), "--bands", str(bands), "--target", "apar",
          "--template", "rfisher.residual:unit_power", "--workers", "1"])
    assert seen == [{"template": residual.unit_power, "target": "apar", "telescope": "chime",
                     "backend": "radiofisher"}]
    assert (tmp_path / "channel_table.csv").read_text().splitlines()[1].startswith("7,test,600.0,606.0,")


def test_figures_take_their_channels_from_the_table(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(table, "row", fake_row)
    bands = tmp_path / "bands.csv"
    bands.write_text("channel,low_mhz,high_mhz\n7,600.0,606.0\n")
    main(["table", "--out", str(tmp_path), "--bands", str(bands), "--workers", "1"])
    capsys.readouterr()
    drawn = ["figures", "--table", str(tmp_path / "channel_table.json"), "--out", str(tmp_path)]
    main([*drawn, "--channels", "7"])
    assert [p.split("/")[-1] for p in capsys.readouterr().out.split()] == ["summary.png", "channel_07.png"]
    # channel 19 is in the default band file and not in this table
    for refused in ([*drawn, "--channels", "19"], ["figures", "--table", str(tmp_path / "missing.json"), "--out", str(tmp_path)]):
        with pytest.raises(SystemExit) as error:
            main(refused)
        assert error.value.code == 2


@pytest.mark.parametrize("extra", [["--target", "nope"], ["--template", "nope"], ["--telescope", "nope"], ["--backend", "nope"],
                                   ["--bands", "missing.csv"], ["--channels", "19,99"]])
def test_bad_table_options_are_refused(tmp_path, extra):
    with pytest.raises(SystemExit) as error:
        main(["table", "--out", str(tmp_path), *extra])
    assert error.value.code == 2
