"""The handover disposition over the 354 coarse channels."""
from __future__ import annotations

import json

from rfisher_results.archive.report import core, handover


def test_coarse_channels_cover_the_band_edge_inclusive():
    # the coarse channel whose band straddles 476.0 MHz (freq_id 829) is an edge bin of both channel 14 and channel 15
    assert handover.coarse_channels(470.0, 476.0)[0] == 829 and handover.coarse_channels(470.0, 476.0)[-1] == 845
    assert handover.coarse_channels(476.0, 482.0)[-1] == 829 and len(handover.coarse_channels(470.0, 476.0)) == 17
    assert handover.coarse_channels(602.0, 608.0)[0] == 492
    everything = set()
    for ch in range(14, 37):
        lo = 470.0 + 6 * (ch - 14)
        everything |= set(handover.coarse_channels(lo, lo + 6))
    assert everything == set(range(492, 846))


def _ledger(tmp_path, classes):
    ledger = tmp_path / "ledger"
    (ledger / "channels").mkdir(parents=True)
    names = []
    for ch, (cls, flag, f) in classes.items():
        fid = 845 - round((470 + 6 * (ch - 14) + 0.309441 - 470) / 0.390625)
        rec = {"channel": ch, "freq_id": fid, "product": f"{fid}.npz", "product_sha256": "b" * 64, "notes": [],
               "sections": {"geometry": {"allocation_low_mhz": 470.0 + 6 * (ch - 14), "allocation_high_mhz": 476.0 + 6 * (ch - 14)},
                            "screening": {"screening_class": cls, "survey_flag_rate_era": flag},
                            "selection": {"diagnostic_masked_fraction": f}}}
        (ledger / "channels" / f"ch{ch}_fid{fid}.json").write_text(json.dumps(rec))
        names.append(f"channels/ch{ch}_fid{fid}.json")
    (ledger / "run.json").write_text(json.dumps({"generated": "x", "producer": {"commit": "a" * 40}, "channels": names}))
    return core.load_run(tmp_path)


def test_disposition_rules(tmp_path):
    run = _ledger(tmp_path, {14: (handover.EXCISION, 0.95, 0.99), 15: (handover.EXCISION, 1.0, 0.995),
                             16: ("measurement-bound on floor", 0.9, 0.99), 17: (handover.EXCISION, 1.0, float("nan"))})
    rows, band = handover.disposition(run)
    by = {r["channel"]: r for r in rows}
    # 14 and 15 are both excised: their shared edge is discarded; 15 shares its upper edge with kept 16
    assert by[16]["kept"] == by[16]["n_bins"] and by[16]["discarded"] == 0
    assert by[15]["kept"] == 2                      # the edge shared with 16 and its own pilot tap
    # channel 14 keeps its own tap (844) and channel 15's tap (829), which sits on their shared edge
    assert by[14]["kept"] == 2 and by[14]["policy"].startswith("excised")
    assert by[15]["cost_flag"] == float("inf") and abs(by[14]["cost_flag"] - 20.0) < 1e-9
    assert band["kept"] + band["monitoring_taps"] + band["discarded"] == 354 and band["allocations_excised"] == 3
    frag = handover.build(run)
    assert frag.tex.count("\\\\") == 5 and "ch09.disposition.kept.ch15" in {n.key for n in frag.numbers}
    assert "$\\infty$" in frag.tex
