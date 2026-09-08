"""A populated synthetic era through calibration, selection, replay and written spectra."""
import datetime as dt
import json
from types import SimpleNamespace

import numpy as np
import pytest

from rfisher.npzio import load_npz
from rfisher_results.archive import blocks, eras, run
from rfisher_results.archive.products import Product, NFFT
from test_pilotproxy_v5 import _write_product, _replace


@pytest.mark.parametrize("spectra", [False, True])
def test_populated_era_pipeline_fits_only_calibration_and_records_replay(
        tmp_path, monkeypatch, synthetic_archive_health, spectra):
    frames, units = 384, 24
    path = _write_product(tmp_path / "product.npz", 14, frames=frames, units=units)
    times = np.array([dt.datetime(2023 + m // 12, 1 + m % 12, 2, tzinfo=dt.timezone.utc).timestamp()
                      for m in range(units)])
    values = load_npz(path)
    with Product(path) as product:
        geometry = product.geometry
    fine = values["fine_power_u64"]
    fine[:, 0, :] = 20
    fine[:, 1:, :] = 20
    # Four repeating interference levels give a real mask/residual frontier;
    # each acquisition contains the same mix, with no artificial time drift.
    fine[:, 0, geometry.nominal_fine_bin] = np.tile([40, 80, 160, 500], frames // 4)
    changes = dict(unit_time0_ctime=times, unit_input_map_sha256=np.full(units, "a" * 64),
                   fine_power_u64=fine, baseband_power_linear=np.tile([4.0, 4.1, 5.0, 10.0], frames // 4)[:, None])
    reference = values["p_ref_sum_u64"]
    target = np.rint(reference * float(values["target_norm_sq"][0]) / float(values["reference_norm_sum_sq"][0])
                     * np.tile([0.99, 1.01, 1.08, 20.0], frames // 4)[:, None]).astype(np.uint64)
    ratio = target * float(values["reference_norm_sum_sq"][0]) / (reference * float(values["target_norm_sq"][0]))
    excess = ratio - 1.0
    excess_db = np.full(excess.shape, np.nan)
    excess_db[excess > 0] = 10 * np.log10(excess[excess > 0])
    shelf_offset = (float(values["pilot_below_data_db"])
                    - 10 * np.log10(float(values["dtv_bandwidth_hz"]) / float(values["bin_enbw_hz"]))
                    - 10 * np.log10(float(values["pilot_capture_efficiency"])))
    changes.update(p_target_u64=target, coarse_power_ratio=2.0 * target / reference,
                   normalized_coarse_power_ratio_db=10 * np.log10(ratio),
                   normalized_pilot_excess=excess, pilot_excess_db=excess_db,
                   estimated_data_shelf_snr_db=excess_db + shelf_offset,
                   reject_mask=(ratio > 1).astype(np.uint8))
    if spectra:
        codes = np.zeros((frames, NFFT), dtype=np.int16)
        pilot = int(round(geometry.nominal_psd_bin)) % NFFT
        codes[:, [(pilot - 1) % NFFT, pilot, (pilot + 1) % NFFT]] = [1000, 2000, 1000]
        changes.update(psd_frame_db_i16=codes, psd_db_reference=np.ones((frames, 1)),
                       psd_db_step_per_code=np.float64(0.01), psd_db_invalid_code=np.int16(-32768))
    _replace(path, **changes)
    calibrated_rows = []

    def calibrated_chain(product, selected, **kwargs):
        calibrated_rows.extend(np.flatnonzero(selected))
        return SimpleNamespace(gain=1.0, tau_quality="measured",
                               as_row=lambda: {"channel": 14, "gain": 1.0, "tau_quality": "synthetic"})

    # This bench supplies a known transfer. The chain's estimator has its own
    # statistical tests; here we verify which frames the pipeline fits it on.
    monkeypatch.setattr(run.chain, "residual_chain_on_frames", calibrated_chain)
    monkeypatch.setattr(run.chain, "residual_chain", lambda *a, **kw: SimpleNamespace(as_row=lambda: {"gain": 999}))
    config = eras.EraConfig(min_frames=1, min_units=1, min_days=1, min_peak_cohort=1,
                            units_sensitivity=(1,), threshold_sensitivity_db=((0.5, 1.0),))
    out = tmp_path / "result"
    result = run.process_channel(str(path), str(out), campaign_last_month=int(blocks.month_index([times[-1]])[0]),
                                 replicates=8, seed=91, era_config=config,
                                 tolerance_row={"r_tol_dilation": 100.0})
    record = result["record"].sections
    assert record["era"]["n_eras"] == 1
    assert record["blocks"]["status"] == "supported"
    assert record["blocks"]["calibration_frames"] == record["blocks"]["evaluation_frames"] == frames // 2
    assert calibrated_rows == list(range(frames // 2))
    assert record["selection"] is not None
    assert record["selection"]["gain_basis"] == "era chain"
    assert record["selection"]["claim_status"] != "operational"
    assert record["null_evaluation"] is not None
    assert record["containment"] is not None if spectra else record["containment"] is None
    channel = out / "channels" / "ch14"
    assert (channel / "coarse_frontier.csv").is_file(), (record["null"], result["record"].notes)
    assert json.loads((channel / "eras.json").read_text())["channel"] == 14
    if spectra:
        assert record["operating"] is not None
        assert record["held_out"] is not None, (record["operating"], result["record"].notes)
        assert (channel / "held_out_spectra.npz").is_file()
