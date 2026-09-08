# coding=utf-8
"""Gate the dissertation number checker itself.

The checker is only trustworthy if its matching surface is: normalization
must fold the unicode variants LaTeX and PDF extraction produce into one
form, the three check kinds must fail in exactly their advertised
directions, and the CSV row selectors must keep resolving the operating rows
of the shipped tables (so a column rename breaks CI here, loudly,
rather than silently green-lighting the dissertation).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "check_dissertation_numbers",
    ROOT / "scripts" / "check_dissertation_numbers.py")
cdn = importlib.util.module_from_spec(spec)
sys.modules["check_dissertation_numbers"] = cdn
spec.loader.exec_module(cdn)

SHIPPED_TABLES = (
    "three_worlds.csv",
    "fig31_validation.csv", "required_times.csv", "bin_level_targets.csv",
    "forecast_completion_all_dtv_bins.json",
    "forecast_completion_template_comparison.csv")
requires_shipped_tables = pytest.mark.skipif(
    not all((cdn.OUT / name).is_file() for name in SHIPPED_TABLES),
    reason=f"shipped tables not found under {cdn.OUT}; "
           "point RFISHER_OUT at the results tree")


@pytest.fixture(autouse=True)
def _without_archive_products(monkeypatch):
    """Keep the product-recomputed table checks inert here. These tests drive
    the gate over synthetic corpora carrying only the registry-derived
    needles, so the flagger and eta-sweep sections have no table to find;
    without this the module's result would depend on whether the developer
    happens to have RFISHER_PRODUCT_DIRS exported."""
    monkeypatch.delenv("RFISHER_PRODUCT_DIRS", raising=False)


def test_normalize_folds_unicode_and_commas():
    s = "1,566\u00d7 over \u2014 5.9\u20137.8 dB \u2248 \u22120.00026"
    n = cdn.normalize(s)
    assert "1566x over" in n
    assert "5.9-7.8 dB" in n
    assert "~ -0.00026" in n


def test_normalize_tex_strips_comments_not_escaped_percent():
    n = cdn.normalize("48.5\\% kept % trailing comment\nnext", tex=True)
    assert "48.5%" in n and "trailing" not in n and "next" in n


def test_normalize_tex_math_idioms():
    n = cdn.normalize(r"$1.4\times$ margin, 1\,566$\times$, $-0.00026$~dB",
                      tex=True)
    assert "1.4x" in n and "1566x" in n and "-0.00026 dB" in n


def test_wide_surface_only_reaches_wide_checks(capsys):
    ck = cdn.Checker("prose only", extra="316x from figure data")
    ck.value("narrow", ["316x"], "m")
    ck.value("wide", ["316x"], "m", wide=True)
    out = capsys.readouterr().out
    assert ck.failures == 1
    assert "FAIL  narrow" in out and "PASS  wide" in out


def test_check_kinds_fail_in_their_directions(capsys):
    ck = cdn.Checker("keep 1566x and 316x over; both 104 ns and 110 ns")
    ck.require("present", r"1566x", "m")
    ck.require("absent", r"9999x", "m")
    ck.forbid("stale present", r"316x over", "m")
    ck.forbid("stale absent", r"555x", "m")
    ck.forbid_pair("both present", r"104 ns", r"110 ns", "m")
    ck.forbid_pair("one present", r"104 ns", r"777 ns", "m")
    out = capsys.readouterr().out
    assert ck.n == 6 and ck.failures == 3
    assert out.count("FAIL") == 3 and out.count("PASS") == 3


def test_value_accepts_any_rendering():
    ck = cdn.Checker("kept fraction 51.8% of frames")
    ck.value("f", ["0.5183", "51.8%", "51.8 %"], "m")
    assert ck.failures == 0


@requires_shipped_tables
def test_csv_operating_rows_resolve():
    # The channel set follows the worlds bank's conventions and may move
    # with a regeneration; what must stay fixed is that the selectors
    # resolve populated rows, so a column rename fails loudly.
    worlds = cdn.worlds_rows()
    assert len(worlds) == 16
    assert cdn.world_provenance_ok(worlds, cdn.era_rows())
    assert cdn.world_results_ok(worlds)
    assert all(worlds[(world, 32)]["residual_status"]
               == "insufficient_kept_frames" for world in cdn.WORLD_ORDER)
    assert all(worlds[(world, 35)]["floor_evidence"] == "measured"
               and worlds[(world, 35)]["tau_quality"] == "measured"
               for world in cdn.WORLD_ORDER)
    era = cdn.era_rows()
    assert set(era) == {32, 35}
    assert cdn.era_provenance_ok(era)
    assert era[32]["tau_quality"] == "bounded_above"
    assert era[35]["tau_quality"] == "measured"


def test_era_provenance_rejects_changed_inputs_and_ratios():
    original = cdn.era_rows()
    for key, value in (
        ("product_sha256", "0" * 64),
        ("analysis_source_sha256", "0" * 64),
        ("r_over_rtol", "1"),
        ("floor_basis", "unknown"),
        ("masked_fraction", "0.1"),
        ("best_cost_masked_fraction", "0.1"),
        ("tau_seconds", "1"),
        ("floor_frames", "1"),
    ):
        rows = {ch: dict(row) for ch, row in original.items()}
        rows[32][key] = value
        assert not cdn.era_provenance_ok(rows)


@requires_shipped_tables
def test_world_provenance_rejects_changed_inputs():
    original = cdn.worlds_rows()
    for key, value in (
        ("bank_sha256", "0" * 64),
        ("product_sha256", "0" * 64),
        ("floor_epoch", "unknown"),
        ("generator_sha256", "0" * 64),
        ("selection_policy_sha256", "0" * 64),
    ):
        rows = {item: dict(row) for item, row in original.items()}
        rows[("none", 35)][key] = value
        assert not cdn.world_provenance_ok(rows, cdn.era_rows())


@requires_shipped_tables
def test_world_results_reject_changed_values():
    original = cdn.worlds_rows()
    for item, key, value in (
        (("peak1", 33), "pass_fs8", "False"),
        (("peak1", 33), "r_fine", "999"),
        (("peak1", 33), "suppression_db", "999"),
        (("none", 29), "tau_capped", "False"),
        (("none", 32), "pass_fs8", "False"),
    ):
        rows = {row_item: dict(row)
                for row_item, row in original.items()}
        rows[item][key] = value
        assert not cdn.world_results_ok(rows)


@requires_shipped_tables
def test_world_results_reject_coordinated_changes():
    original = cdn.worlds_rows()
    rows = {item: dict(row) for item, row in original.items()}
    for world in cdn.WORLD_ORDER:
        row = rows[(world, 33)]
        residual = 2.0 * float(row["r_fine"])
        row["r_fine"] = str(residual)
        for name in ("aperp", "apar", "fs8"):
            row[f"pass_{name}"] = str(residual <= float(row[f"tol_{name}"]))
    assert not cdn.world_results_ok(rows)

    rows = {item: dict(row) for item, row in original.items()}
    rows[("peak1", 33)]["tol_fs8"] = "999"
    rows[("peak1", 33)]["pass_fs8"] = "True"
    assert not cdn.world_results_ok(rows)


@requires_shipped_tables
def test_end_to_end_exit_codes(tmp_path):
    # A source containing every stale literal must fail; the same source
    # with requires satisfied and forbids absent must pass. Build the green
    # text from the registry's own CSV needles so the test tracks out/.
    green = " ".join(
        ["1566x over now", "the fs/2 legacy epoch quarterly table",
           "3.2-7.8 dB", "46748 LRGs", "7.6 yr", "XOR 0x88",
           "48.5% of verified-quiet time", "fine_gain_mc evidence",
           "Youden-J table", r"\input{tables/archive/worlds.tex}",
           r"\input{tables/archive/saveability.tex}",
           r"\input{tables/archive/protector.tex}",
           r"\input{tables/archive/zeta_sensitivity.tex}",
           r"\input{tables/archive/drift_screen.tex}",
           r"\input{tables/archive/flagger_survey.tex}",
           r"\input{tables/archive/tolerance_eta.tex}",
           _forecast_headline_rows()])
    red = green + " eight years; 316x over; 5.9-7.8 dB; ten measured channels"
    g, r = tmp_path / "g.txt", tmp_path / "r.txt"
    g.write_text(green)
    r.write_text(red)
    assert cdn.main(["--tex", str(g)]) == 0
    assert cdn.main(["--tex", str(r)]) == 1


@requires_shipped_tables
def test_summary_invariant_flags_split_population(tmp_path, capsys):
    src = tmp_path / "s.txt"
    src.write_text("316x 1587x 382x 24x 1566x over; " + _green_min())
    sj = tmp_path / "summary.json"
    sj.write_text(
        '{"bao_policy_case": {"policies": ['
        '{"policy_key": "keep_everything", "residual_multiple": 316},'
        '{"policy_key": "mad_1p8", "residual_multiple": 1587},'
        '{"policy_key": "sk", "residual_multiple": 382},'
        '{"policy_key": "pilot", "residual_multiple": 24}]}}')
    rc = cdn.main(["--tex", str(src), "--summary-json", str(sj)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "one population" in out and "ratio 5.0" in out


def _green_min() -> str:
    return " ".join(
        ["fs/2 legacy quarterly", "3.2-7.8", "46748", "7.6 yr", "1566x",
           "XOR 0x88", "48.5%", "fine_gain_mc", "Youden",
           r"\input{tables/archive/worlds.tex}",
           r"\input{tables/archive/saveability.tex}",
           r"\input{tables/archive/protector.tex}",
           r"\input{tables/archive/zeta_sensitivity.tex}",
           r"\input{tables/archive/drift_screen.tex}",
           r"\input{tables/archive/flagger_survey.tex}",
           r"\input{tables/archive/tolerance_eta.tex}",
           _forecast_headline_rows()])


def _forecast_headline_rows() -> str:
    """Synthetic renderings of the forecast headline tables, built from the
    same out/ sources the registry reads and shaped like the normalized
    rows the column-anchored checks expect, so the green text tracks a
    forecast rerun exactly as the dissertation would."""
    cols = cdn.fig31_clean_columns()
    yrs = cdn.required_times_years()
    pens = cdn.required_time_penalties()
    byrs = cdn.bin_target_years()
    # The substituted and band-wide rows of Table 9.1 are not rows of
    # required_times.csv, but they are shipped scenarios the gate recomputes,
    # so take them from the same source it uses. SUB_YR is the fallback when
    # the archive products are unreachable and only the band-wide row can be
    # rebuilt from the pinned bank.
    SUB_YR = 0.0253
    hist = cdn.table91_historical_rows() or {}
    band = hist.get("band", {"survey_years": 0.0295,
                             "survey_penalty": 1.239})
    sub = hist.get("sub")
    tol = cdn.perbin_fs8_tolerances()
    trs = cdn.template_rows()
    per = [float(r["perbin_binding_tolerance"]) for r in trs]
    joint = [float(r["combined_binding_tolerance"]) for r in trs]
    worlds = cdn.worlds_rows()

    def worlds_line(ch: int) -> str:
        """One worlds row as the table prints it: R = r_sys/r_tol, bold
        where the world passes, terminated so the cell reader can cut it."""
        cells = []
        for world in cdn.WORLD_ORDER:
            row = worlds[(world, ch)]
            value = f"{cdn.world_ratio(row):.4g}"
            cells.append(
                rf"\mathbf{{{value}}}" if row["pass_fs8"] == "True"
                else value)
        return f"ch{ch} & " + " & ".join(cells) + r" \\"

    deployed29 = worlds[("deployed", 29)]
    aperp_over = (float(deployed29["r_fine"])
                  / float(deployed29["tol_aperp"]))
    return " ".join(
        ["sigma(D_V)/D_V [%], clean, 1 on-sky yr & "
         + " & ".join(f"{v:.3f}" for _, v in cols),
         f"uncontaminated baseline & {yrs['clean']:.4f} & 1.000 &"
         f" {byrs['clean']:.3f} & 1.000 \\\\",
         f"legacy detector rate table, 23 ch (published) &"
         f" {yrs['legacy_rate_table']:.4f} &"
         f" {pens['legacy_rate_table']:.3f} &"
         f" {byrs['legacy_rate_table']:.3f} &"
         f" {byrs['legacy_rate_table'] / byrs['clean']:.3f} \\\\",
         # Row terminators matter: the cell-anchored checks cut a row at
         # its trailing \\, so a row without one is invisible to them.
         # The substituted and band-wide cells come from the same shipped
         # scenarios the gate recomputes, so the green text tracks a bank
         # rebuild the way the dissertation would.
         f"with products substituted on ch 34-36 &"
         f" {sub['survey_years']:.4f} & {sub['survey_penalty']:.3f} &"
         f" {sub['bin_years']:.3f} & {sub['bin_penalty']:.3f} \\\\"
         if sub else
         f"with products substituted on ch 34-36 & {SUB_YR:.4f} &"
         f" {SUB_YR / yrs['clean']:.3f} & 0.258 & 1.474 \\\\",
         f"bootstrap rule band-wide (f = 0.942, excised) &"
         f" {band['survey_years']:.4f} & {band['survey_penalty']:.3f} &"
         f" never & \\infty \\\\",
         "r_tol (x 10^{-3}) & "
         + " & ".join(f"{1e3 * tol[b]:.2f}" for b in range(5, 12)),
         f"{min(per):.6f}-{max(per):.6f}",
         f"{min(joint):.6f}-{max(joint):.6f}",
         f"{sum(int(r['perbin_accepted']) for r in trs)}"
         f"/{sum(int(r['perbin_rejected']) for r in trs)}",
         # The worlds rows are read past the table's own header.
         cdn.WORLDS_HEADER + r" & 55 ns & 110 ns & 200 ns \\\\",
         worlds_line(33), worlds_line(35),
         r"ch32 & \multicolumn{4}{c}{not evaluated: 16<30 kept frames at "
         r"\eta=1 in its transmitter-on era}",
         f"ch29 & fails all & fails all & fails all & fails all "
         rf"(\alpha_\perp {aperp_over:.1f}x over)",
         "Channel 35's parallel dilation alone passes at 110 ns",
         "Channel 35 uses its measured off-era floor"])


@requires_shipped_tables
def test_forecast_sources_resolve():
    cols = cdn.fig31_clean_columns()
    assert len(cols) == 7
    assert [z for z, _ in cols] == [0.85, 1.05, 1.25, 1.45, 1.65, 1.85, 2.43]
    yrs = cdn.required_times_years()
    byrs = cdn.bin_target_years()
    assert 0 < yrs["clean"] < yrs["legacy_rate_table"]
    assert 0 < byrs["clean"] < byrs["legacy_rate_table"]
    tol = cdn.perbin_fs8_tolerances()
    assert set(tol) >= {5, 6, 10, 11}
    assert all(0 < v < 0.01 for v in tol.values())
    assert cdn.template_rows()


def test_legacy_projects_excluded_from_tex_sweep(tmp_path):
    (tmp_path / "chapters").mkdir()
    keep = tmp_path / "chapters" / "ch01.tex"
    keep.write_text("kept prose")
    legacy = tmp_path / "evidence" / "legacy_projects" / "old_paper"
    legacy.mkdir(parents=True)
    (legacy / "main.tex").write_text("the present draft")
    text, files = cdn.load_tex([str(tmp_path)])
    assert files == [keep]
    assert "the present draft" not in text


@requires_shipped_tables
def test_the_worlds_table_must_be_the_generated_fragment(capsys):
    """The hand-written four-row worlds table is retired: the check now
    requires the generated fragment, so a chapter that inlines its own rows
    again fails rather than being recomputed against a superseded snapshot."""
    good = _green_min()
    without = good.replace(r"\input{tables/archive/worlds.tex}", "")
    assert without != good
    for text, want in ((good, "PASS"), (without, "FAIL")):
        ck = cdn.Checker(cdn.normalize(text))
        cdn.run_checks(ck, None)
        out = capsys.readouterr().out
        lines = [ln for ln in out.splitlines()
                 if "worlds table generated from the run" in ln]
        assert lines and lines[0].startswith(want), lines


@requires_shipped_tables
def test_table91_penalty_consistency_direction(capsys):
    byrs = cdn.bin_target_years()
    pen = f"{byrs['legacy_rate_table'] / byrs['clean']:.3f}"
    good = _green_min()
    # Keep the CSV-derived needle present so only the internal-consistency
    # check can fail on the corrupted row.
    bad = good.replace(f"& {pen}", "& 9.999") + f" {pen}"
    for text, want in ((good, "PASS"), (bad, "FAIL")):
        ck = cdn.Checker(cdn.normalize(text))
        cdn.run_checks(ck, None)
        out = capsys.readouterr().out
        lines = [ln for ln in out.splitlines()
                 if "penalty consistent" in ln]
        assert lines and lines[0].startswith(want)


@requires_shipped_tables
def test_baseline_ratchet(tmp_path):
    red = tmp_path / "r.txt"
    red.write_text(_green_min() + " eight years")   # exactly one regression
    base = tmp_path / "baseline"
    base.write_text("1")
    assert cdn.main(["--tex", str(red), "--baseline", str(base)]) == 0
    base.write_text("0")
    assert cdn.main(["--tex", str(red), "--baseline", str(base)]) == 1
    assert cdn.main(["--tex", str(red),
                     "--baseline", str(tmp_path / "missing")]) == 1


def test_archive_report_checks_verify_markers_against_the_numbers_documents(tmp_path, capsys):
    """The archive report's numbers verify bound and unbound markers; a changed marker fails, an unsourced one skips."""
    import json
    from rfisher_results.archive import numbers as nb
    report = tmp_path / "dissertation"
    doc = nb.NumbersDocument.new("demo", repository="WVURAIL/RFIsher", commit="a" * 40, script="x", generated="2026-09-07T00:00:00Z")
    doc.add(nb.Number("ch08.demo.width.ch29", 1.654, precision=2))
    doc.add(nb.Number("ch08.demo.floor.ch33", -35.9, precision=1))
    doc.write(report / "numbers" / "demo.numbers.json")
    (report / "export_manifest.json").write_text(json.dumps({"schema": {"name": "rfisher-archive-report", "version": 1},
                                                             "source": {"repository": "WVURAIL/RFIsher", "commit": "a" * 40}, "artifacts": []}))
    inv = tmp_path / "inv.csv"
    inv.write_text("file,line,section,value,context,key\n"
                   "chapters/ch08.tex,10,Nulls,$1.65$,...,ch08.demo.width.ch29\n"
                   "chapters/ch08.tex,12,Floors,$-38.5$~dB,...,ch08.demo.floor.ch33\n"
                   "chapters/ch09.tex,20,Eta,\\rerun{$99$},...,\n")
    ck = cdn.Checker("")
    report_by_chapter = cdn.archive_report_checks(ck, report, inv)
    out = capsys.readouterr().out
    assert ck.failures == 1 and "update the marker" in out
    assert report_by_chapter["chapters/ch08.tex"]["verified"] == 1 and report_by_chapter["chapters/ch08.tex"]["changed"] == 1
    # the unbound ch09 marker is reported as unbound, never verified by a coincidence of value
    assert "1 rerun markers not bound to a report key" in out and "chapters/ch09.tex" not in report_by_chapter
    assert "2 of 3 markers bound to a report key" in out
