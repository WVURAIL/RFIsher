"""Band weighting and incumbent summaries previously lacked direct benches."""
import math
from pathlib import Path

import numpy as np
import pytest

from rfisher_results.archive.report import core, figures_masking_cost as masking, flagger_survey


def _run(*sections):
    channels = tuple(core.Channel(14 + i, 844 - i, "product.npz", "a" * 64, (), section,
                                   Path(f"channel{i}.json")) for i, section in enumerate(sections))
    return core.Run(Path("results"), {}, channels)


def _numbers(fragment):
    return {number.key: number.value for number in fragment.numbers}


def test_masking_marks_use_frame_weighted_kept_channels_and_distinct_denominators():
    run = _run(
        {"era": {"current_frames": 100}, "selection": {"diagnostic_masked_fraction": 0.2},
         "screening": {"survey_flag_rate_era": 0.1}},
        {"era": {"current_frames": 300}, "selection": {"diagnostic_masked_fraction": 0.6},
         "screening": {"survey_flag_rate_era": None}},
        {"era": {"current_frames": 10000}, "selection": {"diagnostic_masked_fraction": 1},
         "screening": {"screening_class": masking.EXCISION, "survey_flag_rate_era": 1}},
        {"era": {"current_frames": 0}})
    point, flag = masking.band_masks(run)
    assert point.masked_fraction == pytest.approx(0.5) and point.cost == pytest.approx(2)
    assert point.frames == 400 and flag.frames == 100
    assert point.channels == flag.channels == (14, 15)
    assert flag.masked_fraction == 0.1
    curves = {name: np.array([[0, 1], [1, 3]]) for name in masking.SERIES}
    fragment = masking.build(run, curves=curves)
    numbers = _numbers(fragment)
    assert numbers["ch09.masking_cost.years.dilation.reported_points"] == pytest.approx(2)
    assert numbers["ch09.masking_cost.frames.survey_flag"] == 100


def test_masking_curve_reader_sorts_each_series(tmp_path):
    path = tmp_path / "curves.csv"
    path.write_text("series,masked_fraction,time_year\na,1,3\nb,0,4\na,0,1\n", encoding="utf-8")
    curves = masking.read_curves(path)
    np.testing.assert_array_equal(curves["a"], [[0, 1], [1, 3]])
    np.testing.assert_array_equal(curves["b"], [[0, 4]])


def test_absent_band_mask_has_undefined_cost_instead_of_full_excision_cost():
    point, flag = masking.band_masks(_run({}))
    for mark in (point, flag):
        assert math.isnan(mark.masked_fraction) and mark.frames == 0
        assert math.isnan(mark.cost)
    assert math.isinf(masking.BandMask("excised", 1.0, 100, (14,)).cost)
    fragment = masking.build(_run({}), curves={})
    assert any("undefined" in note for note in fragment.notes)


def test_flagger_summary_separates_masking_support_from_measured_suppression():
    run = _run(
        {"flaggers": {"scored_frames": 100, "mad_masked_fraction": 0.2,
                     "mad_suppression_db": 2, "mad_status": "measured"}},
        {"flaggers": {"scored_frames": 300, "mad_masked_fraction": 1.0,
                     "mad_suppression_db": 999, "mad_status": "empty"}},
        {})
    fragment = flagger_survey.build(run)
    numbers = _numbers(fragment)
    assert numbers["ch09.flaggers.scored_frames"] == 400
    assert numbers["ch09.flaggers.mad.masked_fraction.median"] == pytest.approx(0.6)
    assert numbers["ch09.flaggers.mad.masked_fraction.channels"] == 2
    assert numbers["ch09.flaggers.mad.suppression_db.median"] == 2
    assert numbers["ch09.flaggers.mad.suppression_db.channels"] == 1
    ledger = flagger_survey.build_ledger(run)
    assert "16 & --" in ledger.tex
    assert _numbers(ledger)["appC.flaggers.mad.masked_fraction.ch14"] == 0.2


@pytest.mark.parametrize("missing", [None, np.nan, "unavailable"])
def test_partial_flagger_sections_render_without_crashing(missing):
    run = _run({"flaggers": {"scored_frames": missing, "notes": "incomplete measurement"}})
    for builder in flagger_survey.BUILDERS:
        fragment = builder(run)
        assert "\\begin{tabular}" in fragment.tex
    assert math.isnan(_numbers(flagger_survey.build_ledger(run))["appC.flaggers.scored_frames.ch14"])
    assert "only the recorded counts" in " ".join(flagger_survey.build(run).notes)
    assert "incomplete measurement" in " ".join(flagger_survey.build_ledger(run).notes)


def test_empty_flagger_run_reports_zero_support():
    numbers = _numbers(flagger_survey.build(_run()))
    assert numbers["ch09.flaggers.channels"] == 0
    assert numbers["ch09.flaggers.scored_frames"] == 0
    assert numbers["ch09.flaggers.mad.suppression_db.channels"] == 0


@pytest.mark.parametrize("has_point", [False, True])
def test_masking_figure_renders_available_marks_and_closes_figures(tmp_path, monkeypatch, has_point):
    import matplotlib
    import matplotlib.pyplot as plt

    curves = {name: np.array([[0, 0.1], [0.5, 0.2], [0.99, 10]]) for name in masking.SERIES}
    monkeypatch.setattr(masking, "read_curves", lambda: curves)
    run = _run({"era": {"current_frames": 100},
                "selection": {"diagnostic_masked_fraction": 0.5 if has_point else None},
                "screening": {"survey_flag_rate_era": 0.2}})
    before = plt.get_fignums()
    with matplotlib.rc_context({"text.usetex": False}):
        paths = masking.render(run, tmp_path)
    assert len(paths) == 2
    assert paths[0].read_bytes().startswith(b"%PDF-")
    assert paths[1].read_bytes().startswith(b"\x89PNG")
    assert plt.get_fignums() == before
