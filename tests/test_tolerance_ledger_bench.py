"""Legacy ledger readers retain failures and estimator/family boundaries."""
import json
import math

from rfisher_results.archive import tolerances


def test_historical_tolerances_take_only_accepted_parameter_values(tmp_path):
    def point(value, **extra):
        return {"parameters": {"aperp": {
            "accepted": True, "metadata": "ignored",
            "finite": {"r_tolerance": value, "failure_reason": None},
            "failed": {"r_tolerance": 1e-20, "failure_reason": "singular"},
            "missing": {"r_tolerance": None}, **extra},
            "apar": None}}
    bins = [{"bin_index": 7, "z_low": 1.0, "z_high": 1.1,
             "points": [point(0.02), point(0.01)]},
            {"bin_index": 8, "z_low": 1.1, "z_high": 1.2, "points": []}]
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps({"ledgers": {"chosen": {"bins": bins},
                                            "unrelated": {"bins": []}}}))
    result = tolerances.ledger_bin_tolerances(path, estimator="chosen")
    assert set(result) == {7, 8}
    assert result[7]["aperp"] == 0.01
    assert (result[7]["z_low"], result[7]["z_high"]) == (1.0, 1.1)
    assert math.isnan(result[7]["apar"]) and math.isnan(result[7]["fs8"])
    assert all(math.isnan(result[8][p]) for p in tolerances.TARGETS)


def test_mapping_keeps_all_overlaps_and_empty_channels_in_the_selected_family(tmp_path):
    path = tmp_path / "mapping.csv"
    path.write_text("family,channel,overlap_bin_indices\n"
                    "selected,14,3;4;5\nother,14,99\nselected,15,\nselected,16,7\n")
    assert tolerances.ledger_channel_bins(path, family="selected") == {14: (3, 4, 5), 15: (), 16: (7,)}
    assert tolerances.ledger_channel_bins(path, family="absent") == {}
