from rfisher.cli import main


def test_figures_for_one_channel(tmp_path, capsys):
    main(["figures", "--out", str(tmp_path), "--channels", "19"])
    printed = capsys.readouterr().out.split()
    assert [p.split("/")[-1] for p in printed] == ["summary.png", "channel_19.png"]
    assert all((tmp_path / n).stat().st_size > 10_000 for n in ("summary.png", "channel_19.png"))


def test_table_for_one_channel(tmp_path, capsys):
    main(["table", "--out", str(tmp_path), "--channels", "37", "--workers", "1"])
    assert (tmp_path / "channel_table.json").exists() and (tmp_path / "channel_table.csv").exists()
