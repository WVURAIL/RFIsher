#!/usr/bin/env python3
"""Freeze and inspect retained LimeSDR smoke captures, without hardware access."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np

from rfisher_results.validation.sdr_capture import (
    db_ratio, joint_tone_line, narrow_feature, projection,
)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()


def write(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n')


def freeze(workspace, study):
    workspace, study = workspace.resolve(), study.resolve()
    if study.exists():
        raise FileExistsError(study)
    source = workspace/'results/calibration_progress_2026-09-09/sdr'
    status = json.loads((source/'final-status.json').read_text())
    files, attempts = {}, []
    for attempt in status['attempts']:
        root = source/attempt['attempt']
        receipt = json.loads((root/'receipt.json').read_text())
        plan = json.loads((root/'plan.json').read_text())
        if sha(root/'receipt.json') != attempt['receipt_sha256']:
            raise ValueError('old receipt identity changed')
        for name, digest in receipt['artifacts'].items():
            path = root/name
            if sha(path) != digest:
                raise ValueError('old artifact identity changed: ' + str(path))
            files[str(path)] = digest
        files[str(root/'receipt.json')] = sha(root/'receipt.json')
        if (root/'independent-iq-review.json').exists():
            files[str(root/'independent-iq-review.json')] = sha(root/'independent-iq-review.json')
        report = receipt['worker_report']
        attempts.append({'attempt': attempt['attempt'], 'root': str(root),
                         'transport_success': attempt['transport_success'],
                         'original_tone_presence_passed': attempt['tone_presence_passed'],
                         'original_rule': attempt['tone_presence_rule'],
                         'worker': report, 'plan': {k: plan.get(k) for k in
                         ('sample_rate_hz', 'tone_offset_hz', 'tone_seconds',
                          'zero_prefix_seconds', 'zero_tail_seconds', 'tone_peak_component')},
                         'rx_bytes': (root/'rx.cfile').stat().st_size})
    for name in ('README.md', 'final-status.json', 'hardware-verification.json'):
        files[str(source/name)] = sha(source/name)
    nominal = workspace/'dtv-census/ingest/apply_ised_overlay.py'
    files[str(nominal)] = sha(nominal)
    sources = [Path(__file__).resolve(), workspace/'RFIsher/src/rfisher_results/validation/sdr_capture.py',
               workspace/'RFIsher/tests/test_sdr_capture.py']
    plan = {
        'schema': 'retained-sdr-capture-diagnostics-v1',
        'frozen_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Previously inspected short development captures; no hardware or line-origin investigation',
        'selection_frozen_before_new_payload_analysis': True,
        'development_basis': 'Prior reports identify a strong +309.9 kHz component and a +100 kHz smoke tone; all seven attempts retained.',
        'source_sha256': {str(p): sha(p) for p in sources}, 'input_sha256': files,
        'attempts': attempts, 'sample_encoding': 'little-endian complex64, interleaved float32 I/Q',
        'tone_hz': 100000., 'line_hz': 309900.,
        'windows_seconds_relative_tx_payload': {'before_tx': [-.05, -.02], 'zero_prefix': [.01, .04],
                                               'tone': [.06, .09], 'zero_tail': [.11, .12]},
        'one_ms_projection_intervals': [-.06, .125],
        'five_ms_spectral_intervals': [-.05, .125],
        'feature_search_halfwidth_hz': 500, 'diagnostic_band_halfwidth_hz': 2000,
        'adjacent_diagnostic_offsets_hz': [3000, 5000],
        'reported_prominence_marker_db': 10,
        'time_rule': 'Use recorded hardware sample timestamps and sample-rate readback. No fitted timing lag, trimming, or independent-bin confidence interval.',
        'startup_rule': 'Each saved read chunk separately, retain reset/drop flags; qualification overlap is duplicated data, not an independent control.',
        'failed_attempt_rule': 'No payload for001; descriptive retained-chunk data for002/003, never accepted controls or a contiguous success.',
        'projector_test': 'Joint least-squares 100 kHz tone plus fitted narrow line; record signed target-power change and modeled finite-window line coupling.',
        'projector_limit': 'Two-sinusoid sensitivity only; not a bound on stochastic/broadband leakage or actual ATSC pilot/reference response.',
        'conditional_channel19_coordinate_comparison': {'nominal_pilot_hz': 500309441., 'smoke_rx_lo_hz': 500000000., 'condition': 'Only if RF=LO+complex offset; no calibrated source-frequency or detector-weight mapping is established'},
        'atsc_detector_geometry_available': False,
        'atsc_geometry_reason': '2 MHz smoke capture and 100 kHz tone are not the channelized ATSC detector configuration; no saved pilot/reference weights are bound to these attempts.',
        'transmitter_off_reference_available': False,
        'transmitter_off_reason': '004-007 started the TX stream before qualification; zero-valued payload is not disabled TX. Failed002/003 are not qualified transmitter-off controls.',
        'physical_power_calibration': False, 'scientific_acceptance': False,
    }
    study.mkdir(parents=True)
    (study/'source_snapshots').mkdir()
    for source_path in sources:
        (study/'source_snapshots'/source_path.name).write_bytes(source_path.read_bytes())
    write(study/'plan.json', plan)
    print(json.dumps({'frozen': str(study), 'plan_sha256': sha(study/'plan.json'),
                      'input_files': len(files), 'attempts': len(attempts)}), flush=True)


def sample_stats(x):
    finite = bool(np.isfinite(x).all())
    if not x.size or not finite:
        return {'samples': int(x.size), 'finite': finite, 'mean_power': None, 'peak_component': None}
    return {'samples': int(x.size), 'finite': finite,
            'mean_power': float(np.mean(x.real.astype(float)**2+x.imag.astype(float)**2)),
            'peak_component': float(max(np.max(abs(x.real)), np.max(abs(x.imag)))),
            'component_magnitude_at_least_one_count': int(np.count_nonzero(abs(x.real) >= 1)+np.count_nonzero(abs(x.imag) >= 1))}


def run(study):
    os.nice(10)
    plan_path = study/'plan.json'
    plan = json.loads(plan_path.read_text())
    for group in ('source_sha256', 'input_sha256'):
        for path, expected in plan[group].items():
            if sha(path) != expected:
                raise ValueError('frozen identity changed: ' + path)
    outdir = study/'measurements'
    outdir.mkdir()
    summaries = []
    for item in plan['attempts']:
        root, worker = Path(item['root']), item['worker']
        rate = float(worker['rx_rate_hz'])
        rx = np.fromfile(root/'rx.cfile', dtype='<c8')
        startup = np.fromfile(root/'startup.cfile', dtype='<c8') if (root/'startup.cfile').exists() else np.empty(0, dtype=complex)
        result = {'attempt': item['attempt'], 'transport_success': item['transport_success'],
                  'original_tone_presence_passed': item['original_tone_presence_passed'],
                  'original_rule': item['original_rule'], 'sample_rate_hz_readback': rate,
                  'rx_frequency_hz_readback': worker.get('rx_frequency_hz'),
                  'native_tx_gain_db_readback': worker.get('native_tx_gain_db'),
                  'requested_native_tx_gain_db': worker.get('requested_native_tx_gain_db', 0),
                  'raw_rx': sample_stats(rx), 'raw_startup': sample_stats(startup),
                  'rx_timestamp_span_matches_count': worker['next_rx_timestamp']-worker['first_rx_timestamp'] == len(rx),
                  'chunk_records': [], 'windows': {}, 'timeline': [], 'five_ms': [],
                  'physical_calibration': False}
        if len(rx) != worker['captured_samples']:
            raise ValueError('capture sample count changed')
        chunks = [json.loads(l) for l in (root/'rx-chunks.jsonl').read_text().splitlines()] if (root/'rx-chunks.jsonl').exists() else []
        for row in chunks:
            x = startup if row['file'] == 'startup.cfile' else rx
            offset, n = row['file_sample_offset'], row['received_count']
            if not 0 <= offset < offset+n <= len(x):
                raise ValueError('chunk outside saved data')
            block = x[offset:offset+n]
            stats = sample_stats(block)
            stats.update({k: row[k] for k in ('chunk_index', 'phase', 'file', 'file_sample_offset',
                         'timestamp', 'timestamp_gap', 'dropped_delta', 'underrun_delta',
                         'overrun_delta', 'action', 'candidate_samples')})
            stats['tone_projection_power'] = abs(projection(block, rate, plan['tone_hz']))**2
            stats['line_projection_power'] = abs(projection(block, rate, plan['line_hz']))**2
            result['chunk_records'].append(stats)
        if startup.size:
            offset, count = worker['qualification_overlap_startup_sample_offset'], worker['qualification_samples']
            overlap_equal = np.array_equal(startup[offset:offset+count], rx[:count])
            if not overlap_equal:
                raise ValueError('qualification duplicate differs')
            result['qualification_duplicate'] = {'samples': count, 'startup_offset': offset, 'equal_bytes': True,
                                                  'pooled_as_independent_samples': False}
            start_rows = [r for r in result['chunk_records'] if r['file'] == 'startup.cfile']
            qualified = [r for r in start_rows if r['action'] == 'qualification_candidate']
            result['startup_first_vs_qualification_power_db'] = db_ratio(start_rows[0]['mean_power'],
                float(np.median([r['mean_power'] for r in qualified])))
        if not item['transport_success']:
            result['measurement_status'] = 'empty_payload' if not rx.size else 'failed_transport_retained_diagnostics_only'
            if rx.size and not chunks:
                result['retained_single_read_tone'] = narrow_feature(rx, rate, plan['tone_hz'])
                result['retained_single_read_line'] = narrow_feature(rx, rate, plan['line_hz'])
        else:
            result['measurement_status'] = 'complete_descriptive_success_capture'
            if not result['rx_timestamp_span_matches_count'] or not result['raw_rx']['finite']:
                raise ValueError('success capture has invalid continuity/finite values')
            first, tx = worker['first_rx_timestamp'], worker['tx_start_timestamp']
            result['available_relative_tx_seconds'] = [(first-tx)/rate, (first+len(rx)-tx)/rate]
            result['scheduled_zero_tail_captured_seconds'] = max(0., min(.15, (first+len(rx)-tx)/rate)-.1)
            def interval(a, b):
                lo, hi = round(tx+a*rate)-first, round(tx+b*rate)-first
                if not 0 <= lo < hi <= len(rx):
                    raise ValueError('predeclared interval unavailable')
                return rx[lo:hi], lo+first, hi+first
            for name, (a, b) in plan['windows_seconds_relative_tx_payload'].items():
                x, lo, hi = interval(a, b)
                tone, line = narrow_feature(x, rate, plan['tone_hz']), narrow_feature(x, rate, plan['line_hz'])
                result['windows'][name] = {'start_timestamp': lo, 'stop_timestamp': hi,
                    'seconds_relative_tx': [a, b], 'stats': sample_stats(x), 'tone': tone, 'line': line,
                    'joint_projection': joint_tone_line(x, rate, plan['tone_hz'], line['fitted_frequency_hz'])}
            for a_ms in range(-60, 125):
                x, _, _ = interval(a_ms/1000, (a_ms+1)/1000)
                result['timeline'].append({'center_seconds': (a_ms+.5)/1000,
                    'mean_power': sample_stats(x)['mean_power'],
                    'tone_projection_power': abs(projection(x, rate, plan['tone_hz']))**2,
                    'line_projection_power': abs(projection(x, rate, plan['line_hz']))**2})
            for a_ms in range(-50, 125, 5):
                x, _, _ = interval(a_ms/1000, (a_ms+5)/1000)
                result['five_ms'].append({'center_seconds': (a_ms+2.5)/1000,
                    'tone': narrow_feature(x, rate, plan['tone_hz']),
                    'line': narrow_feature(x, rate, plan['line_hz'])})
            inside = [r for r in result['five_ms'] if .06 <= r['center_seconds'] < .09]
            result['tone_interior_block_diagnostics'] = {}
            for feature in ('tone', 'line'):
                rows = [r[feature] for r in inside]
                result['tone_interior_block_diagnostics'][feature] = {
                    'blocks': len(rows), 'frequency_fit_range_hz': [min(r['fitted_frequency_hz'] for r in rows), max(r['fitted_frequency_hz'] for r in rows)],
                    'all_blocks_prominence_at_least_10_db': all(r['prominence_at_least_10_db'] for r in rows),
                    'projection_power_max_min_db': db_ratio(max(r['fixed_projection_power'] for r in rows), min(r['fixed_projection_power'] for r in rows)),
                    'interpretation': 'Observed six-block range, not an uncertainty interval or accepted stationarity criterion'}
            control_names = ('before_tx', 'zero_prefix', 'zero_tail')
            result['tone_vs_controls_projection_db'] = {name: db_ratio(result['windows']['tone']['tone']['fixed_projection_power'], result['windows'][name]['tone']['fixed_projection_power']) for name in control_names}
            result['line_vs_controls_projection_db'] = {name: db_ratio(result['windows']['tone']['line']['fixed_projection_power'], result['windows'][name]['line']['fixed_projection_power']) for name in control_names}
            # The signed difference stays signed; diagnostic sidebands are not a noise calibration.
            baseline = np.mean([result['windows'][name]['tone']['band_power_plus_minus_2000_hz'] for name in control_names])
            result['signed_tone_band_power_excess_over_control_mean'] = result['windows']['tone']['tone']['band_power_plus_minus_2000_hz'] - float(baseline)
        destination = outdir/(item['attempt']+'.json')
        write(destination, result)
        summaries.append({'attempt': item['attempt'], 'path': str(destination.relative_to(study)), 'sha256': sha(destination),
                          'measurement_status': result['measurement_status']})
        print(json.dumps(summaries[-1]), flush=True)
    write(study/'summary.json', {'schema': 'retained-sdr-diagnostics-summary-v1', 'plan_sha256': sha(plan_path),
          'completed_utc': datetime.now(timezone.utc).isoformat(), 'python': sys.version, 'numpy': np.__version__,
          'attempts': summaries, 'physical_calibration': False, 'independent_validation': False,
          'hardware_access': False, 'atsc_science_bin_conclusion': 'not determined by these smoke captures'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('freeze'); p.add_argument('--workspace', type=Path, required=True); p.add_argument('--study', type=Path, required=True)
    p = sub.add_parser('run'); p.add_argument('--study', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'freeze': freeze(args.workspace, args.study)
    else: run(args.study.resolve())


if __name__ == '__main__': main()
