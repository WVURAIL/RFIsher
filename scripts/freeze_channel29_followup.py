#!/usr/bin/env python3
"""Freeze the channel29 follow-up design and audit candidate metadata only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

import numpy as np
from rfisher import selection_policy
from rfisher_results.validation import followup


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def freeze(args):
    study = args.study.resolve()
    meta = args.metadata.resolve()
    out = args.output.resolve()
    if out.exists():
        raise ValueError('Freeze output must be a new directory')
    if not math.isfinite(args.minimum_retention) or not 0 < args.minimum_retention <= 1:
        raise ValueError('minimum retention must be in (0,1]')
    audit = json.loads((meta / 'audit.json').read_text())
    if audit.get('passed') is not True:
        raise ValueError('Metadata audit must pass before candidate freeze')
    meta_manifest = json.loads((meta / 'manifest.json').read_text())
    for name, identity in meta_manifest['files'].items():
        expected = identity['sha256'] if isinstance(identity, dict) else identity
        if sha(meta / name) != expected:
            raise ValueError(f'Metadata audit artifact hash mismatch: {name}')
    exclusions = json.loads((meta / 'exclusions.json').read_text())
    events = exclusions['excluded_event_ids']
    if not events or len(events) != len(set(events)) or len(events) != exclusions['excluded_acquisitions']:
        raise ValueError('Invalid development exclusion set')
    manifest = json.loads((study / 'release-manifest.json').read_text())
    bound = ['coarse/ch29.json', 'coarse/tradeoffs.csv',
             'coarse-worlds/coarse-world-sensitivity.csv',
             'forecast-verification/sampled-time-channel-envelopes.csv',
             'archive/ledger/run.json', 'archive/analysis-input-manifest.json']
    for name in bound:
        if sha(study / name) != manifest['files'][name]['sha256']:
            raise ValueError(f'Study source hash mismatch: {name}')
    channel = json.loads((study / 'coarse/ch29.json').read_text())
    policy = next(p for p in channel['policies'] if p['policy'] == 'cal_q0.5')
    if policy['eta_integer_ratio'] != [followup.ETA_NUMERATOR, followup.ETA_DENOMINATOR]:
        raise ValueError('Study does not contain the declared coarse candidate')
    names = ['schema_version','schema_revision','schema_name','source_event_key_schema_version',
             'detector_contract_json','decision_contract_json','mask_rule','physical_channel',
             'freq_id','chime_frequency_hz','nfft','detector_window_samples','num_input_streams',
             'sample_rate_hz','target_norm_sq','reference_norm_sum_sq','pilot_below_data_db',
             'bin_enbw_hz','dtv_bandwidth_hz','pilot_capture_efficiency', 'sense',
             'weights_hash','weight_bank_sha256','weight_manifest_sha256','weight_coefficients_sha256',
             'pilot_frequency_hz','detector_version']
    geometry = {}
    with np.load(args.product, allow_pickle=False) as product:
        for name in names:
            value = np.asarray(product[name])
            geometry[name] = value.item() if value.size == 1 else value.tolist()
    if geometry['physical_channel'] != 29 or geometry['freq_id'] != 614:
        raise ValueError('Expected channel29, frequency614 geometry')
    # Authenticate this one development product before binding its geometry.
    # Compressed bytes are hashed; only small geometry members are decoded.
    if sha(args.product) != channel['product_sha256']:
        raise ValueError('Development product bytes differ from the verified release')
    run = json.loads((study / 'archive/ledger/run.json').read_text())
    if run['products'].get(args.product.name) != channel['product_sha256']:
        raise ValueError('Development product identity is not bound by the completed run')
    out.mkdir(parents=True)
    source_dir = out / 'source_snapshots'
    source_dir.mkdir()
    repo = Path(__file__).resolve().parents[1]
    rail = repo.parent
    sources = [Path(__file__).resolve(), Path(followup.__file__).resolve(),
               repo/'src/rfisher_results/validation/holdout.py',
               repo/'src/rfisher_results/validation/causal_eras.py',
               repo/'src/rfisher_results/validation/coverage.py',
               repo/'src/rfisher_results/validation/tolerance.py',
               repo/'src/rfisher_results/archive/products.py',
               repo/'src/rfisher_results/archive/blocks.py',
               repo/'src/rfisher_results/archive/eras.py',
               repo/'src/rfisher/pilotproxy.py', repo/'src/rfisher/selection_policy.py',
               rail/'pilot-proxy/src/pilot_proxy/archive_health.py']
    identities = {}
    for path in sources:
        relative = path.relative_to(rail)
        copy = source_dir / relative
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, copy)
        identities[str(path)] = {'sha256': sha(path), 'role': 'current producing source; changes require a new design version'}
        identities[str(copy)] = {'sha256': sha(copy), 'role': 'preserved source copy'}
    for path in [study/'release-manifest.json', *[study/n for n in bound],
                 *sorted(meta.glob('*.json'))]:
        identities[str(path)] = {'sha256': sha(path), 'role': 'development evidence or metadata exclusion audit'}
    now = datetime.now(timezone.utc)
    scalar = channel['chain_gain'] * policy['calibration']['G1_allowance']
    cost_ratio = policy['evaluation']['mask_only_cost'] / policy['calibration']['mask_only_cost']
    declarations = {
        'scope': 'Candidate design only. Physical calibration and operational policy acceptance remain pending.',
        'retention': {'minimum_fraction': args.minimum_retention, 'maximum_mask_only_cost': 1/args.minimum_retention,
                      'status': 'provisional planning choice', 'origin': args.retention_origin,
                      'estimand': 'kept / eligible frames, reported with acquisition and day support; no frame-independence assumption'},
        'support_each_confirmation_half': {'kept_frames': 30, 'populated_months': 6,
              'span_days': 270, 'support_population': 'pre-policy eligible frames; kept-frame minimum is separate',
              'populated_month': {'eligible_frames': 30, 'distinct_eligible_acquisitions': 5, 'distinct_eligible_days': 3},
              'status': 'provisional candidate rules; not a derived precision or physical guarantee'},
        'drift': {'primary_estimand': 'symmetric ratios between two fixed future calendar halves',
              'maximum_cost_ratio': 1.05, 'maximum_assigned_residual_ratio': 1.10,
              'historical_calibration_vs_future': 'report separately; never substitute the favorable historical half ratio',
              'partition_origin': 'New fixed-window midpoint, not the old observed-time range midpoint; no claim of identical partition method',
              'status': 'point-screen hypotheses only; no equivalence claim without calibrated uncertainty'},
        'uncertainty': {'required_confidence': 0.95, 'independence_unit': 'validated acquisition/day blocks, never individual frames',
              'block_rule_status': 'must be measured and frozen with the physical calibration before confirmation',
              'method_binding_required': True,
              'marginal_intervals_are_not_joint': True,
              'unsupported_resamples': 'retain as infinite failure bounds; never discard',
              'joint_requirement': 'Simultaneous uncertainty for retention, cost drift and residual drift must be declared and coverage-validated before confirmation',
              'rule': 'Freeze block definition, estimator, source hashes and interval coverage evidence in the later calibration bundle; absent evidence is inconclusive, not pass'},
        'residual_coverage': {'target_joint_block_coverage': 0.95, 'calibration_confidence': 0.95,
              'evaluation_confidence': 0.95, 'unsupported_attempts': 'count as failures',
              'correction': 'No digital correction imported; fit only on separate calibration controls and freeze before confirmation',
              'population': 'known-truth independent controls under the declared measurement geometry; not automatically telescope coverage'},
        'science': {'primary_world': 'deployed', 'primary_world_delay_ns': 200,
              'selection_basis': 'retrospective development preference', 'primary_group': ['aperp','apar'],
              'secondary_group': ['fs8'], 'primary_zeta': 1.0, 'sensitivity_zeta': [.5,.3,.1],
              'retained_onsky_years': 1.0, 'all_channel_overlapping_bins_required': True,
              'assumed_suppression_db': 11.4, 'measured_filter_credit_enabled': False,
              'no_filter_and_other_worlds': 'prespecified sensitivity only; no post-confirmation winner selection',
              'physical_gates': ['known in-band signal/noise/RFI injections through actual cleaner including refit',
                   'coherent mean and stochastic covariance separately measured with units/exposure',
                   'science signal transfer and noise weighting calibrated for the same mask',
                   'residual-shape and quadrature checks with primary Fisher stability gates retained',
                   'joint bias upper allowances below frozen primary tolerances; missing evidence remains inconclusive']},
        'health': {'require_pilot_proxy_frame_health': True, 'valid_only_fallback_allowed': False,
                   'rule': 'same frozen Product(require_health=True) gate; report every invalid/untimed/excluded attempt'},
        'monitor': {'reference_input_map_sha256': '9283ed21a77b6e4549b53c785f0352dc137cf5f02905dc34ebc88c65b0679fae',
             'reference_state': channel['current_era']['current_state'], 'last_development_month': '2026-08',
             'rule': 'Use append-only causal-era monitoring. Geometry/map changes, ambiguous or changed state, or unresolved gaps halt the candidate. Never retrospectively relabel confirmation acquisitions.',
             'module': 'rfisher_results.validation.causal_eras', 'operational_activation': None},
    }
    payload = {'schema': followup.SCHEMA, 'status': 'candidate_frozen',
        'version_id': 'channel29-coarse-median-followup-v1', 'frozen_at': now.isoformat(),
        'scientific_certification': False, 'operational_acceptance': False,
        'policy': {'kind': 'coarse_exact_rational', 'eta_numerator': followup.ETA_NUMERATOR,
                   'eta_denominator': followup.ETA_DENOMINATOR, 'eta': followup.ETA,
                   'comparison': 'valid && p_target*reference_norm_sum_sq*eta_denominator > target_norm_sq*p_ref_sum*eta_numerator',
                   'equality': 'keep only if valid, healthy and eligible',
                   'kept_rule': 'eligible = valid & health.include & trusted_time_cohort; kept = eligible & ~reject_at_eta',
                   'frame_exposure_requirement': 'Equal frame exposure under fixed geometry required for count fraction to represent exposure; otherwise refuse',
                   'fine_Q16_conversion_allowed': False},
        'geometry': geometry,
        'development': {'excluded_event_ids': events, 'excluded_acquisitions': len(events),
            'exclusion_scope': 'all frequency shards; includes quarantined, unscored and previously evaluated events',
            'later_controls': 'append every subsequent development/calibration attempt to calibration exclusions',
            'study_manifest_sha256': sha(study/'release-manifest.json'),
            'geometry_product': str(args.product.resolve()), 'geometry_product_sha256_from_verified_release': channel['product_sha256'],
            'product_rehashed_this_step': True, 'geometry_only_read': names,
            'historical_calibration_retention': policy['calibration']['retention'],
            'historical_evaluation_retention': policy['evaluation']['retention'],
            'historical_whole_block_cost_ratio': cost_ratio,
            'historical_calibration_half_cost_ratio': policy['calibration_halves']['mask_only_cost_ratio'],
            'historical_assigned_floor_db': channel['floor']['db'],
            'historical_assigned_chain_gain': channel['chain_gain'], 'historical_assigned_residual': scalar,
            'physical_residual_measured': False},
        'confirmation': {'start_rule': 'first_utc_day_after_calibration_freeze', 'duration_days': 730,
            'partition': 'two_equal_calendar_halves', 'calibration_artifact': None,
            'calendar_interval': None, 'rule': 'Resolve once a separately frozen calibrated artifact exists; each half is365days. Whole acquisitions must fit one half. No sample-size or endpoint extension after outcomes.',
            'duration_origin': 'new planning choice to allow six populated months and270-day span per half',
            'short_calibration_experiments': 'allowed earlier; count as development, never confirmation',
            'stopping': 'fixed interval; insufficient support remains inconclusive; changes require a new version and fresh cohort',
            'final_evaluation': 'only after the fixed interval ends; any earlier metadata audit is interim, never final acceptance'},
        'declarations': declarations, 'selection_policy_sha256': selection_policy.sha256(),
        'source_artifacts': identities,
        'runtime': {'python': sys.version, 'numpy': np.__version__},
        'metadata_audit_schema': audit.get('schema')}
    protocol = followup.seal_protocol(payload)
    write_new(out/'protocol.json', protocol)
    write_new(out/'readiness.json', followup.audit_candidate_cohort(protocol, [], now=now))
    write_new(out/'manifest.json', {'schema': 'channel29-followup-freeze-artifacts-v1',
        'protocol_sha256': protocol['protocol_sha256'],
        'files': {str(p.relative_to(out)): {'sha256':sha(p),'bytes':p.stat().st_size}
                  for p in sorted(out.rglob('*')) if p.is_file()}})
    print(json.dumps({'status':protocol['status'],'protocol_sha256':protocol['protocol_sha256'],
                      'excluded_acquisitions':len(events),'output':str(out)},indent=2))


def audit_cohort(args):
    protocol = json.loads(args.protocol.read_text())
    raw = json.loads(args.units.read_text())
    units = raw['units'] if isinstance(raw, dict) else raw
    if not isinstance(units, list):
        raise ValueError('units must be a list or an object containing units')
    for unit in units:
        for name in ['start','end']:
            value = unit.get(name)
            if isinstance(value, str):
                try:
                    unit[name] = datetime.fromisoformat(value.replace('Z','+00:00'))
                except ValueError:
                    pass  # The metadata auditor records malformed timestamps as refusals.
    calibration = json.loads(args.calibration.read_text()) if args.calibration else None
    result = followup.audit_candidate_cohort(protocol, units, calibration=calibration)
    result['input_sha256'] = {str(args.protocol.resolve()):sha(args.protocol), str(args.units.resolve()):sha(args.units)}
    if args.calibration:
        result['input_sha256'][str(args.calibration.resolve())] = sha(args.calibration)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_new(args.output, result)
    print(json.dumps({k:v for k,v in result.items() if k in ['passes_candidate_metadata_checks','confirmation_metadata_ready','passes_confirmation_metadata_checks','confirmation_interval_complete','confirmation_stage',
                                                                                     'final_evaluation_metadata_prerequisites_met','scientific_certification']},indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    f = sub.add_parser('freeze')
    for name in ['study','metadata','product','output']:
        f.add_argument('--'+name, type=Path, required=True)
    f.add_argument('--minimum-retention', type=float, default=.25)
    f.add_argument('--retention-origin', default='assistant provisional planning default; user has not adopted a minimum')
    a = sub.add_parser('audit')
    for name in ['protocol','units','output']:
        a.add_argument('--'+name,type=Path,required=True)
    a.add_argument('--calibration',type=Path)
    args = p.parse_args()
    freeze(args) if args.action == 'freeze' else audit_cohort(args)

if __name__ == '__main__':
    main()
