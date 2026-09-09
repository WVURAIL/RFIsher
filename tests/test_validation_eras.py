from dataclasses import asdict, replace

import pytest

from rfisher_results.archive import blocks, eras
from rfisher_results.validation.eras import audit_era_document, audit_era_prefixes, monthly_records_from_document


def rec(month, level=2.0, *, populated=True, peak=0.0):
    return eras.MonthRecord(month=2020 * 12 + month, frames=30 if populated else 1,
                           units=5 if populated else 1, days=3 if populated else 1,
                           populated=populated, level_db=level, state=eras.state_of(level),
                           peak_offset_bins=peak, peak_cohort="detected", peak_frames=30,
                           input_maps=("input-map-A",), software_tags=("not-used",))


def test_no_revisions_for_stable_extension_after_initial_confirmation():
    result = audit_era_prefixes([rec(i) for i in range(8)], eras.DEFAULT_CONFIG)
    assert result["revision_events"] == 1  # First month becomes definite at second month.
    assert result["revisions"][0]["as_of"] == "2020-02"
    assert all(x["previous_assignments_revised"] == 0 for x in result["snapshots"][2:])
    assert result["scientific_certification"] is False


def test_future_months_cannot_change_earlier_prefix_snapshots():
    past = [rec(0, 0.0), rec(1, 0.0), rec(2, 0.75), rec(3, 0.75)]
    first = audit_era_prefixes(past, eras.DEFAULT_CONFIG)
    second = audit_era_prefixes(past + [rec(4, 2.0), rec(5, 2.0)], eras.DEFAULT_CONFIG)
    assert second["snapshots"][:len(past)] == first["snapshots"]
    assert second["revisions"][:len(first["revisions"])] == first["revisions"]
    assert any(r["revised_month"] == "2020-03" and r["age_calendar_months"] == 3
               for r in second["revisions"])
    assert second["boundaries"][0]["new_first"] == "2020-05"
    assert second["boundaries"][0]["first_seen"] == "2020-06"


def test_populated_confirmation_is_distinct_from_calendar_delay():
    records = [rec(0, 0.0), rec(1, 0.0), rec(2), rec(3, populated=False), rec(9)]
    result = audit_era_prefixes(records, eras.DEFAULT_CONFIG)
    boundary = result["boundaries"][0]
    assert boundary["new_first"] == "2020-03"
    assert boundary["first_seen"] == "2020-10"
    assert boundary["stable_seen_lag_months"] == 7
    revision = next(r for r in result["revisions"] if r["revised_month"] == "2020-03")
    assert revision["age_calendar_months"] == 7
    assert revision["age_populated_months"] == 1


def test_empty_and_unpopulated_histories_remain_uncertified():
    result = audit_era_prefixes([], eras.DEFAULT_CONFIG)
    assert result["snapshots"] == []
    assert result["final_eras"] == 0
    result = audit_era_prefixes([rec(0, populated=False)], eras.DEFAULT_CONFIG)
    assert result["snapshots"][0]["latest_state"] is None


@pytest.mark.parametrize("records", [[rec(1), rec(0)], [rec(0), rec(0)]])
def test_bad_chronology_is_rejected(records):
    with pytest.raises(ValueError, match="unique months"):
        audit_era_prefixes(records, eras.DEFAULT_CONFIG)


def test_inconsistent_monthly_support_is_rejected():
    with pytest.raises(ValueError, match="population flag"):
        audit_era_prefixes([replace(rec(0), frames=1)], eras.DEFAULT_CONFIG)
    with pytest.raises(ValueError, match="nonnegative integers"):
        audit_era_prefixes([replace(rec(0), units=-1)], eras.DEFAULT_CONFIG)


def document():
    config = eras.DEFAULT_CONFIG
    records = [rec(i) for i in range(4)]
    seg = eras.segment(records, config)
    return {"channel": 35, "config": asdict(config), "config_digest": config.digest,
            "months": [{**asdict(r), "month": r.label, "software_tags": 1} for r in records],
            "eras": [{"first_month": e.first_label, "last_month": e.last_label,
                      "state": e.state, "evidence": e.evidence,
                      "months": [blocks.month_label(m) for m in e.months]} for e in seg.eras]}


def test_document_reproduction_preserves_used_features_and_ignores_final_labels():
    doc = document()
    doc["months"][0]["state"] = "deliberately wrong stored derived label"
    doc["months"][0]["resolved"] = "not an input"
    config, records = monthly_records_from_document(doc)
    assert records[0].software_tags == ()
    assert records[0].input_maps == ("input-map-A",)
    assert audit_era_document(doc)["source_segmentation_reproduced"] is True


def test_tampered_policy_and_full_segmentation_are_rejected():
    doc = document()
    doc["config"]["high_db"] = 1.5
    with pytest.raises(ValueError, match="digest mismatch"):
        audit_era_document(doc)
    doc = document()
    doc["eras"][0]["first_month"] = "2020-02"
    with pytest.raises(ValueError, match="does not reproduce"):
        audit_era_document(doc)


def test_malformed_month_is_rejected():
    doc = document()
    doc["months"][0]["month"] = "2020-13"
    with pytest.raises(ValueError, match="YYYY-MM"):
        audit_era_document(doc)
