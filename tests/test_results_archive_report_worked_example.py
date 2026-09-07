"""``worked_example``: chapter 6's worked frame, on a synthetic product then the real run."""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest

from rfisher_results import style
from rfisher_results.archive import numbers as nb
from rfisher_results.archive.report import core
from rfisher_results.archive.report import worked_example as m

ROOT = Path(__file__).resolve().parents[1]
REAL_RUN = Path("/home/djg/rail/results/archive_v5_2026-09-07")

_SPEC = importlib.util.spec_from_file_location("v5_fixture", ROOT / "tests" / "test_pilotproxy_v5.py")
v5_fixture = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v5_fixture)

CHANNEL, FREQ_ID = 36, 506
ANCHOR = 62
FRAMES, UNITS = 8, 4                       # two frames per unit under the fixture's coordinates
IN_ERA = ("2025-01", "2025-12")
# unit 0 holds the exemplar, unit 1 the companion's day, unit 2 another era day, unit 3 is before the era
UNIT_TIMES = (
    m.EXEMPLAR_TIME.timestamp(),
    dt.datetime(2025, 5, 16, 19, 51, 43, tzinfo=dt.timezone.utc).timestamp(),
    dt.datetime(2025, 3, 1, 6, 0, 0, tzinfo=dt.timezone.utc).timestamp(),
    dt.datetime(2024, 6, 1, 6, 0, 0, tzinfo=dt.timezone.utc).timestamp(),
)
# ratio = p_target * 12650 / (200000 * 6338): 120000 -> 1.198 (flagged), 90000 -> 0.898 (kept, no shelf)
TARGETS = (120000, 118000, 90000, 95000, 99000, 85000, 130000, 88000)
EXEMPLAR_ROW, COMPANION_ROW, WEAKEST_ROW = 0, 2, 5


def _finalize(path: Path, target: np.ndarray) -> None:
    """Rewrite ``p_target_u64`` and every float the v5 view checks against it."""
    with np.load(path, allow_pickle=False) as archive:
        reference = np.array(archive["p_ref_sum_u64"], copy=True).astype(np.float64)
        target_norm = float(np.asarray(archive["target_norm_sq"]).reshape(-1)[0])
        reference_norm = float(np.asarray(archive["reference_norm_sum_sq"]).reshape(-1)[0])
        below = float(np.asarray(archive["pilot_below_data_db"]))
        enbw = float(np.asarray(archive["bin_enbw_hz"]))
        bandwidth = float(np.asarray(archive["dtv_bandwidth_hz"]))
        efficiency = float(np.asarray(archive["pilot_capture_efficiency"]))
    target = target.astype(np.uint64).reshape(-1, 1)
    ratio = target.astype(np.float64) * reference_norm / (reference * target_norm)
    excess = ratio - 1.0
    ratio_db = np.full(ratio.shape, np.nan)
    ratio_db[ratio > 0] = 10.0 * np.log10(ratio[ratio > 0])
    excess_db = np.full(ratio.shape, np.nan)
    excess_db[excess > 0] = 10.0 * np.log10(excess[excess > 0])
    offset = below - 10.0 * np.log10(bandwidth / enbw) - 10.0 * np.log10(efficiency)
    rejected = (target.astype(object) * int(reference_norm)
                > int(target_norm) * reference.astype(np.int64).astype(object)).astype(np.uint8)
    v5_fixture._replace(path, p_target_u64=target, coarse_power_ratio=2.0 * target.astype(np.float64) / reference,
                        normalized_coarse_power_ratio_db=ratio_db, normalized_pilot_excess=excess,
                        pilot_excess_db=excess_db, estimated_data_shelf_snr_db=excess_db + offset,
                        reject_mask=rejected)


def _fine_terms(frames: int) -> np.ndarray:
    """A flat bulk at ``T = 1`` with a peak on the anchor: exemplar tall, companion low."""
    terms = np.zeros((frames, 3, 256), dtype=np.uint64)
    terms[:, 0, :] = 1000
    terms[:, 1, :] = 1000
    terms[:, 2, :] = 1000
    terms[EXEMPLAR_ROW, 0, ANCHOR] = 9000                      # T = 9
    terms[EXEMPLAR_ROW, 0, ANCHOR - 1] = 4000
    terms[EXEMPLAR_ROW, 0, ANCHOR + 1] = 4000
    terms[COMPANION_ROW, 0, ANCHOR] = 1500                     # T = 1.5
    terms[WEAKEST_ROW, 0, ANCHOR] = 1200
    return terms


def _product(tmp_path: Path, *, times=UNIT_TIMES, targets=TARGETS) -> Path:
    root = tmp_path / "campaign" / "products" / "_per_pilot"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{FREQ_ID}.npz"
    v5_fixture._write_product(path, CHANNEL, frames=FRAMES, units=UNITS)
    v5_fixture._replace(path, baseband_power_linear=np.full((FRAMES, 1), 4.0),
                        unit_time0_ctime=np.asarray(times, dtype=np.float64),
                        fine_power_u64=_fine_terms(FRAMES))
    _finalize(path, np.asarray(targets))
    return path


def _run(tmp_path: Path, *, product: Path | None, era_frames: int = 6, selection: dict | None = None,
         anchor: dict | None = None, channel: int = CHANNEL) -> core.Run:
    ledger = tmp_path / "ledger"
    (ledger / "channels").mkdir(parents=True, exist_ok=True)
    sections = {
        "era": {"current_first_month": IN_ERA[0], "current_last_month": IN_ERA[1],
                "current_state": "proxy-high", "current_frames": era_frames},
        "anchor": {"anchor_bin": ANCHOR, "designated_half_width": 2, "bulk_size": 125} if anchor is None else anchor,
        "selection": selection if selection is not None else {
            "status": "refused", "refusal": "no floor for frames without a shelf estimate", "surface_points": 0,
            "rho": None, "eta": None, "diagnostic_rho": None, "diagnostic_eta": None},
    }
    record = {"channel": channel, "freq_id": FREQ_ID, "product": f"{FREQ_ID}.npz", "product_sha256": "b" * 64,
              "notes": [], "sections": sections}
    (ledger / "channels" / f"ch{channel}_fid{FREQ_ID}.json").write_text(json.dumps(record))
    run = {"generated": "2026-09-07T00:00:00+00:00", "producer": {"commit": "a" * 40},
           "channels": [f"channels/ch{channel}_fid{FREQ_ID}.json"]}
    if product is not None:
        run["products_dir"] = str(product.parent)
    (ledger / "run.json").write_text(json.dumps(run))
    return core.load_run(tmp_path)


# ------------------------------------------------------------------ the frames
def test_both_frames_are_found_by_time_and_read_exactly(tmp_path):
    run = _run(tmp_path, product=_product(tmp_path))
    ex = m.example(run, channel=CHANNEL)
    assert ex.complete and ex.reasons == []
    assert ex.anchor_bin == ANCHOR and ex.designated_bins == (60, 61, 62, 63, 64) and ex.bulk_size == 125
    exemplar, companion = ex.frames[m.EXEMPLAR], ex.frames[m.COMPANION]
    assert exemplar.row == EXEMPLAR_ROW and companion.row == COMPANION_ROW
    assert m._utc(exemplar.time) == m.EXEMPLAR_TIME
    assert m._utc(companion.time).date() == m.COMPANION_DATE
    # T = 2 S_0 / (S_1 + S_2) on the exact integers the fixture wrote
    assert exemplar.designated_max == pytest.approx(9.0) and exemplar.bulk_median == pytest.approx(1.0)
    assert exemplar.ratio == pytest.approx(9.0) and companion.designated_max == pytest.approx(1.5)
    assert exemplar.target_terms == 2 * 9000 and exemplar.reference_terms == 2000
    # the coarse verdicts: the exemplar is flagged and has a shelf, the companion is kept and has none
    assert exemplar.rejected and math.isfinite(exemplar.shelf_db)
    assert not companion.rejected and not math.isfinite(companion.shelf_db)
    assert exemplar.statistic > 1.0 > companion.statistic


def test_the_cohort_is_the_ledger_era_and_the_weakest_frame_is_reported(tmp_path):
    run = _run(tmp_path, product=_product(tmp_path))
    ex = m.example(run)
    assert ex.cohort_frames == 6                      # units 0-2; unit 3 is before the era's first month
    assert ex.era_label == "2025-01..2025-12 (proxy-high)"
    assert ex.kept_frames == 4                        # 90000, 95000, 99000 and 85000 sit below mu_0
    assert m._utc(ex.weakest_time) == m._utc(UNIT_TIMES[2] + 1 * 16384 / 390625.0)
    assert ex.weakest_statistic == pytest.approx(85000 * 12650 / (200000 * 6338), rel=1e-9)
    assert ex.weakest_is_companion is False


def test_the_companion_can_be_the_weakest_frame_of_the_cohort(tmp_path):
    targets = list(TARGETS)
    targets[WEAKEST_ROW] = 99000                       # lift the other weak frame above the companion
    run = _run(tmp_path, product=_product(tmp_path, targets=targets))
    ex = m.example(run)
    assert ex.weakest_is_companion is True
    frag = m.build(run)
    assert not any("not of the cohort" in note for note in frag.notes)


def test_an_absent_exemplar_is_named_not_guessed(tmp_path):
    shifted = (UNIT_TIMES[0] + 3600.0,) + UNIT_TIMES[1:]
    run = _run(tmp_path, product=_product(tmp_path, times=shifted))
    ex = m.example(run)
    assert m.EXEMPLAR not in ex.frames and m.COMPANION in ex.frames
    assert any("the exemplar frame is not in this product" in reason for reason in ex.reasons)
    frag = m.build(run)
    assert frag.tex.count(core.DASH) >= 10
    assert any("exemplar frame is not in this product" in note for note in frag.notes)


def test_an_absent_companion_day_is_named(tmp_path):
    times = (UNIT_TIMES[0], dt.datetime(2025, 4, 4, tzinfo=dt.timezone.utc).timestamp()) + UNIT_TIMES[2:]
    run = _run(tmp_path, product=_product(tmp_path, times=times))
    ex = m.example(run)
    assert m.COMPANION not in ex.frames and m.EXEMPLAR in ex.frames
    assert any("the companion frame is not in this product" in reason for reason in ex.reasons)


def test_a_missing_product_or_channel_refuses_rather_than_invents(tmp_path):
    run = _run(tmp_path, product=None)
    ex = m.example(run)
    assert ex.frames == {} and any("no readable product" in reason for reason in ex.reasons)
    other = _run(tmp_path / "other", product=_product(tmp_path / "other"), channel=21)
    assert any("carries no channel 36" in reason for reason in m.example(other, channel=CHANNEL).reasons)


def test_a_cohort_that_disagrees_with_the_ledger_is_a_note(tmp_path):
    frag = m.build(_run(tmp_path, product=_product(tmp_path), era_frames=99))
    assert any("differs from the ledger's era count" in note for note in frag.notes)


# ------------------------------------------------------------------ the boundary
def test_no_point_means_no_boundary_and_no_fine_decision(tmp_path):
    run = _run(tmp_path, product=_product(tmp_path))
    ex = m.example(run)
    assert ex.has_point is False and ex.point_basis == ""
    assert not math.isfinite(ex.frames[m.EXEMPLAR].boundary)
    frag = m.build(run)
    assert r"boundary $\eta^\star T_{(\rho^\star)}$ & -- & --" in frag.tex
    assert "fine decision & -- & --" in frag.tex
    assert any("no boundary is drawn" in note for note in frag.notes)
    values = {n.key: n for n in frag.numbers}
    for key in (f"{m.PREFIX}.rho", f"{m.PREFIX}.eta"):
        assert values[key].value is None and values[key].status == "refused"
    assert values[f"{m.PREFIX}.operating_point_boundary.{m.EXEMPLAR}"].status == "refused"


def test_a_diagnostic_point_draws_its_boundary_and_decides_each_frame(tmp_path):
    """rho = 1 on a flat bulk: T_(1) = 1.0, so the boundary is eta and the exemplar is masked."""
    selection = {"status": "no feasible point", "refusal": "within-era stability refused", "surface_points": 12345,
                 "rho": None, "eta": None, "diagnostic_rho": 1, "diagnostic_eta": 2.5}
    run = _run(tmp_path, product=_product(tmp_path), selection=selection)
    ex = m.example(run)
    assert ex.has_point and ex.point_basis == "diagnostic" and ex.rho == 1 and ex.eta == 2.5
    assert ex.frames[m.EXEMPLAR].boundary == pytest.approx(2.5)
    assert ex.frames[m.COMPANION].boundary == pytest.approx(2.5)
    frag = m.build(run)
    assert r"boundary $\eta^\dagger T_{(\rho^\dagger)}$" in frag.tex
    assert "fine decision & masked & kept" in frag.tex     # 9.0 > 2.5 > 1.5
    assert any("declared a diagnostic and not a selection" in note for note in frag.notes)
    values = {n.key: n.value for n in frag.numbers}
    assert values[f"{m.PREFIX}.rho"] == 1 and values[f"{m.PREFIX}.eta"] == 2.5
    assert values[f"{m.PREFIX}.operating_point_boundary.{m.EXEMPLAR}"] == pytest.approx(2.5)


def test_a_selected_point_carries_the_star(tmp_path):
    selection = {"status": "selected", "refusal": "", "surface_points": 9, "rho": 3, "eta": 1.25}
    run = _run(tmp_path, product=_product(tmp_path), selection=selection)
    ex = m.example(run)
    assert ex.point_basis == "selected" and m._star(ex) == r"^\star"
    assert ex.frames[m.EXEMPLAR].boundary == pytest.approx(1.25)   # a flat bulk: every order statistic is 1.0
    frag = m.build(run)
    assert r"rank $\rho^\star$" in frag.tex and "fine decision & masked & masked" in frag.tex


def test_a_rank_outside_the_bulk_leaves_the_boundary_undefined(tmp_path):
    selection = {"status": "selected", "refusal": "", "surface_points": 9, "rho": 999, "eta": 1.25}
    run = _run(tmp_path, product=_product(tmp_path), selection=selection)
    ex = m.example(run)
    assert ex.has_point and not math.isfinite(ex.frames[m.EXEMPLAR].boundary)


def test_boundary_uses_the_ascending_one_based_rank():
    values = np.array([4.0, 1.0, 3.0, 2.0])
    assert m._boundary(values, 1, 1.0) == pytest.approx(1.0)
    assert m._boundary(values, 4, 1.0) == pytest.approx(4.0)
    assert m._boundary(values, 2, 2.0) == pytest.approx(4.0)
    assert math.isnan(m._boundary(values, 0, 1.0)) and math.isnan(m._boundary(values, 5, 1.0))
    assert math.isnan(m._boundary(values, float("nan"), 1.0))


# ------------------------------------------------------------------ the fragment
def test_fragment_keys_every_number_it_prints(tmp_path):
    frag = m.build(_run(tmp_path, product=_product(tmp_path)))
    assert frag.name == m.NAME and frag.label == m.LABEL
    assert frag.tex.count(r"\begin{tabular}") == 3     # the stacking box and two panels
    keys = {n.key for n in frag.numbers}
    for suffix in ("capture_time", "coarse_statistic", "designated_max", "bulk_median", "ratio", "target_terms"):
        assert f"{m.PREFIX}.{suffix}.{m.EXEMPLAR}" in keys and f"{m.PREFIX}.{suffix}.{m.COMPANION}" in keys
    for bin_index in (60, 61, 62, 63, 64):
        assert f"{m.PREFIX}.T_bin{bin_index}.{m.EXEMPLAR}" in keys
    for name in ("cohort_frames", "bulk_size", "anchor_bin", "kept_frames", "weakest_statistic", "selection_status"):
        assert f"{m.PREFIX}.{name}" in keys
    assert len(keys) == len(frag.numbers)
    doc = nb.NumbersDocument.new(frag.name, repository="x", commit="y", script="z", generated="w")
    for number in frag.numbers:
        doc.add(number)                                # raises on a duplicate key


# ------------------------------------------------------------------ the figure
def test_render_writes_both_formats(tmp_path):
    style.configure(require_tex=False)
    run = _run(tmp_path, product=_product(tmp_path))
    paths = m.render(run, tmp_path / "figures")
    assert [p.suffix for p in paths] == [".pdf", ".png"]
    assert all(p.exists() and p.stat().st_size > 5000 for p in paths)


def test_render_survives_a_missing_frame(tmp_path):
    style.configure(require_tex=False)
    shifted = (UNIT_TIMES[0] + 3600.0,) + UNIT_TIMES[1:]
    run = _run(tmp_path, product=_product(tmp_path, times=shifted))
    assert all(p.exists() for p in m.render(run, tmp_path / "figures"))


def test_render_survives_a_product_that_is_not_there(tmp_path):
    style.configure(require_tex=False)
    run = _run(tmp_path, product=None)
    assert all(p.exists() for p in m.render(run, tmp_path / "figures"))


# ------------------------------------------------------------------ the real run
@pytest.mark.skipif(not (REAL_RUN / "ledger" / "run.json").exists(), reason="the archive run of record is not on this machine")
def test_real_run_reproduces_the_chapter_numbers():
    ex = m.example(core.load_run(REAL_RUN))
    assert ex.channel == 36 and ex.freq_id == 506 and ex.anchor_bin == 62
    assert ex.designated_bins == (60, 61, 62, 63, 64) and ex.bulk_size == 125
    exemplar, companion = ex.frames[m.EXEMPLAR], ex.frames[m.COMPANION]
    # the chapter prints T[60..64] = (1.066, 8.730, 18.615, 7.598, 1.083)
    np.testing.assert_allclose(exemplar.designated, [1.066, 8.729, 18.615, 7.598, 1.083], atol=5e-4)
    assert exemplar.statistic == pytest.approx(1.258, abs=5e-4)      # the chapter's F/mu_0 = 1.258
    assert exemplar.bulk_median == pytest.approx(1.009, abs=5e-4)
    assert exemplar.bulk_p90 == pytest.approx(1.165, abs=5e-4)
    assert exemplar.ratio == pytest.approx(18.45, abs=5e-3)
    assert companion.statistic == pytest.approx(0.897, abs=5e-4)     # the chapter's 0.897
    assert companion.designated_max == pytest.approx(2.585, abs=5e-4)
    assert companion.bulk_median == pytest.approx(0.833, abs=5e-4)
    assert companion.ratio == pytest.approx(3.10, abs=5e-3)
    assert not math.isfinite(companion.shelf_db)                     # the refusal's own cause
    # the run leaves no point on this channel, so no boundary exists
    assert ex.status == "refused" and ex.surface_points == 0
    assert ex.has_point is False and not math.isfinite(exemplar.boundary)
    assert ex.cohort_frames >= 28945                                 # 28,945 with the v1 health gate
    assert ex.weakest_is_companion is False
