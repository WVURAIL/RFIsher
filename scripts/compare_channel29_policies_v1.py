#!/usr/bin/env python3
"""Fixed fine/coarse retention comparison on already inspected channel29 data."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import sys

import numpy as np

RAIL = Path(__file__).resolve().parents[2]
for src in (RAIL / 'RFIsher/src', RAIL / 'pilot-proxy/src'):
    sys.path.insert(0, str(src))

from rfisher.residual_scores.bundle import build_residual_score_bundle
from rfisher.thresholds import ALWAYS_MASKED_Q16
from rfisher_results.archive import anchors, blocks, tolerances, worlds
from rfisher_results.archive.products import Product
from rfisher_results.archive.selection import Floor, systematic_residuals
from rfisher_results.validation.policy_comparison import (
    coarse_quantile_threshold, fine_keep, fine_quantile_threshold,
    overlap_2x2, same_mask_summary,
)

PERCENTS = (25, 50, 75, 90)
RANK_FRACTIONS = ((1, 4), (1, 2), (3, 4), (1, 1))
WORLD_SUPPRESSION_DB = {'none': 0.0, 'deployed': 11.4}


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def clean(obj):
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return clean(obj.tolist())
    if isinstance(obj, np.generic):
        return clean(obj.item())
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def write(path, obj):
    with Path(path).open('x') as f:
        json.dump(clean(obj), f, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n')


def utc():
    return datetime.now(timezone.utc).isoformat()


def load_exporter():
    path = RAIL / 'RFIsher/scripts/export_coarse_histogram_frames_v1.py'
    spec = importlib.util.spec_from_file_location('coarse_export_for_policy_comparison', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def decoded_requirements(bundle, rank):
    """Decode the bundle's separate sentinel bits before quantile or replay."""
    col = int(rank) - 1
    if col < 0 or col >= bundle.rho.size or int(bundle.rho[col]) != rank:
        raise ValueError('Frozen rank unavailable; do not substitute another rank')
    values = bundle.required_multiplier_q16[:, col].astype(object)
    values[bundle.always_masked[:, col]] = ALWAYS_MASKED_Q16
    return values


def ratio(a, b):
    if a is None or b is None or not (math.isfinite(a) and math.isfinite(b)):
        return None
    if a == b == 0:
        return 1.0
    return max(a, b) / min(a, b) if min(a, b) > 0 else None


def read_budgets(release, ledger):
    path = release / 'archive/world_tolerances.csv'
    receipt = json.loads(path.with_suffix('.provenance.json').read_text())
    if receipt['csv_sha256'] != sha(path) or receipt['target_years'] != 1.0:
        raise ValueError('Target-time budget provenance differs')
    with path.open() as f:
        rows = [{**x, 'bin_index': int(x['bin_index']),
                 'z_lo': float(x['z_lo']), 'z_hi': float(x['z_hi']),
                 'at_target': x['at_target'] == 'True',
                 'tolerance': float(x['tolerance']) if x['tolerance'] else math.nan}
                for x in csv.DictReader(f)]
    if any(x['at_target'] and float(x['years_used']) != 1.0 for x in rows):
        raise ValueError('Budget is not at one retained on-sky year')
    primary = tolerances.channel_tolerances(channels=(29,), derived_rows=rows)[0]
    for key in ('r_tol_fs8', 'r_tol_aperp', 'r_tol_apar', 'r_tol_dilation'):
        if clean(getattr(primary, key)) != ledger['sections']['tolerance'][key]:
            raise ValueError('No-filter primary tolerance differs: ' + key)
    budgets = {}
    for world in WORLD_SUPPRESSION_DB:
        vals = {p: worlds.tolerance_of(rows, world, primary.bins, p)
                for p in ('aperp', 'apar', 'fs8')}
        vals['dilation'] = min(vals['aperp'], vals['apar']) if all(
            math.isfinite(vals[p]) and vals[p] > 0 for p in ('aperp', 'apar')) else math.nan
        budgets[world] = clean(vals)
    return budgets


def block_summary(mask, bundle, residual, floor, gain, budgets, cohort=None):
    if cohort is None:
        cohort = np.ones(mask.size, dtype=bool)
    keep = mask & cohort
    kept = int(keep.sum())
    frames = int(cohort.sum())
    exposure = bundle.exposure_seconds
    available = float(exposure[cohort].sum())
    retained = float(exposure[keep].sum())
    mean = float(np.average(residual[keep], weights=exposure[keep])) if kept else None
    support = blocks.month_support(bundle.frame_time, bundle.acquisition_index, keep)
    result = {
        'frames': frames, 'kept': kept, 'retention': kept / frames if frames else None,
        'available_exposure_seconds': available, 'retained_exposure_seconds': retained,
        'mask_only_cost_restore_one_retained_year': available / retained if retained else None,
        'allowance': mean, 'chain_allowance': mean * gain if mean is not None else None,
        'floor_only_kept': int(np.count_nonzero(keep & (residual == floor))),
        'minimum_30_kept_met': kept >= 30,
        'provisional_25pct_retention_met': retained >= 0.25 * available if available else False,
        'kept_acquisitions': int(np.unique(bundle.acquisition_index[keep]).size),
        'kept_days': int(np.unique(np.floor(bundle.frame_time[keep] / 86400)).size),
        'kept_supported_months': len(support),
        'generic_summary': same_mask_summary(mask[cohort], residual[cohort], exposure[cohort]),
    }
    prices = {}
    for world, db in WORLD_SUPPRESSION_DB.items():
        assigned = mean * gain * 10 ** (-db / 10) if mean is not None else None
        vals = {}
        for parameter, budget in budgets[world].items():
            R = assigned / budget if assigned is not None and budget is not None else None
            vals[parameter] = {
                'tolerance_zeta1': budget, 'assigned_residual': assigned, 'R': R,
                'additional_power_db': max(0.0, 10 * math.log10(R)) if R is not None and R > 0 else None,
                'status': 'conditional' if R is not None else 'unpriced',
            }
        prices[world] = vals
    result['pricing'] = prices
    return result


def run(args):
    release = args.release.resolve()
    output = args.output.resolve()
    if output.exists():
        raise ValueError('Analysis output must be a new directory')
    ledger_path = release / 'archive/ledger/channels/ch29_fid614.json'
    era_path = release / 'archive/channels/ch29/eras.json'
    prior_path = release / 'coarse/ch29.json'
    frames_path = RAIL / 'results/canfar_histogram_reference_comparison_2026-09-09/frames/ch29.json'
    ledger = json.loads(ledger_path.read_text())
    era = json.loads(era_path.read_text())
    metadata = json.loads(frames_path.read_text())
    prior = json.loads(prior_path.read_text())
    product_path = Path(metadata['product']['path'])
    if sha(product_path) != ledger['product_sha256'] or ledger['product_sha256'] != metadata['product']['sha256']:
        raise ValueError('Complete product hash differs from prior release')
    # Authentication of prior small inputs precedes reading new mask outcomes.
    previous_plan = json.loads((release / 'coarse/plan.json').read_text())
    for p in (ledger_path, era_path, frames_path):
        if previous_plan['inputs_sha256'][str(p)] != sha(p):
            raise ValueError('Prior input changed: ' + str(p))
    budgets = read_budgets(release, ledger)
    exporter = load_exporter()
    sources = [Path(__file__).resolve(), RAIL / 'RFIsher/scripts/export_coarse_histogram_frames_v1.py']
    for root in (RAIL / 'RFIsher/src', RAIL / 'pilot-proxy/src'):
        sources.extend(sorted(root.rglob('*.py')))
    inputs = [ledger_path, era_path, frames_path, prior_path, release / 'coarse/plan.json',
              release / 'archive/world_tolerances.csv', release / 'archive/world_tolerances.provenance.json']
    identities = {str(p): sha(p) for p in sources + inputs}
    identities[str(product_path)] = ledger['product_sha256']
    with Product(product_path, require_health=True) as product:
        _, _, _, current = exporter.memberships(product.frame_time, product.unit_time,
                                                era['eras'], era['current_era'])
        current &= product.selected
        timed = current & np.isfinite(product.frame_time)
        split = blocks.split_blocks(product.frame_unit_index, product.unit_time, timed,
                                    frame_time=product.frame_time, minimum_months=1,
                                    month_kwargs={k: era['config'][k] for k in ('min_frames', 'min_units', 'min_days')})
        for key in ('calibration_frames', 'evaluation_frames', 'calibration_units', 'evaluation_units', 'boundary_time'):
            if getattr(split, key) != ledger['sections']['blocks'][key]:
                raise ValueError('Split differs: ' + key)
        cal_units = set(product.unit_event_id[np.unique(product.frame_unit_index[split.calibration])])
        eva_units = set(product.unit_event_id[np.unique(product.frame_unit_index[split.evaluation])])
        if cal_units & eva_units:
            raise ValueError('Acquisition identity overlap')
        anchor = int(ledger['sections']['null']['anchor_bin'])
        bulk = anchors.bulk_mask(anchor, pad_factor=product.fine_pad_factor,
                                 guard_fine_bins=product.fine_guard_bins,
                                 census_excluded_bins=product.fine_census_excluded_bins)
        bulk_count = int(bulk.sum())
        if bulk_count != ledger['sections']['null']['bulk_size']:
            raise ValueError('Frozen selector bulk differs')
        ranks = sorted({(bulk_count * n + d - 1) // d for n, d in RANK_FRACTIONS})
        null = ledger['sections']['null']
        floor = Floor(null['floor_db'], null['floor_evidence'], null['floor_population'])
        gain = float(ledger['sections']['chain']['chain_gain'])
        output.mkdir(parents=True)
        plan = {
            'schema': 'channel29-practical-policy-comparison-v1', 'frozen_utc': utc(),
            'scope': 'Retrospective diagnostic; all archive acquisitions previously inspected. No new holdout or policy acceptance.',
            'channel': 29, 'freq_id': 614, 'product_path': str(product_path),
            'inputs_sha256': identities, 'retention_percents': PERCENTS,
            'rank_fractions': RANK_FRACTIONS, 'ranks': ranks, 'bulk_bins': np.flatnonzero(bulk),
            'anchor_bin': anchor, 'anchor_source': null['anchor_source'],
            'designated_half_width': anchors.DESIGNATED_HALF_WIDTH,
            'calibration_frames': split.calibration_frames, 'evaluation_frames': split.evaluation_frames,
            'boundary_time': split.boundary_time, 'acquisition_identity_overlap': 0,
            'coarse_threshold': 'Calibration float Q higher quantile, replay as exact binary rational; preserve actual ties.',
            'fine_threshold': 'Exact integer higher quantile of all calibration required Q16 scores at each fixed rank. Sentinel stays in denominator; refuse unavailable rank/threshold.',
            'rank_support': 'Require every frozen rank in both blocks; no replacement based on evaluation.',
            'keep_all': True, 'new_policy_selection': False, 'minimum_retention_planning_only': 0.25,
            'residual': 'Same per-frame max(finite coarse shelf, original stated floor), with missing shelf assigned floor. Exposure-weighted retained mean.',
            'floor_linear': floor.linear, 'chain_gain': gain, 'budgets_zeta1': budgets,
            'world_power_suppression_db': WORLD_SUPPRESSION_DB,
            'forecast_scope': 'One retained on-sky year, identical saved chain/template within each world; report mask-only time to restore it. No mask-dependent covariance/transfer refit.',
            'uncertainty': 'Descriptive full-cohort counts and means only. No frame-iid intervals or physical confidence bound.',
            'calibration_halves': 'Time midpoint of calibration min/max, equality in early. Point cost/allowance ratios only; existing family gate unchanged.',
            'limitations': ['Coarse-derived allowance favors the statistic used to define it; not a physical fine-versus-coarse residual comparison.',
                            '11.4 dB suppression and saved coherence gain are conditional.',
                            'Primary no-filter dilation refusal remains visible.',
                            'Failed September9 retained-control bound is not imported.'],
        }
        write(output / 'plan.json', plan)
        for path in sources:
            target = output / 'source_snapshots' / path.relative_to(RAIL)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        print('Plan frozen; building exact calibration scores', flush=True)
        cal = build_residual_score_bundle(product_path, split.calibration, anchor_bin=anchor,
                                         designated_half_width=anchors.DESIGNATED_HALF_WIDTH, bulk_mask=bulk)
        cal.save(output / 'calibration-scores.npz')
        policies = []
        for percent in PERCENTS:
            threshold = coarse_quantile_threshold(product.view.statistic[split.calibration], percent=percent)
            policies.append({'id': f'coarse_q{percent}', 'kind': 'coarse', 'percent': percent, 'rank': None, **threshold})
        for rank in ranks:
            req = decoded_requirements(cal, rank)
            for percent in PERCENTS:
                policies.append({'id': f'fine_r{rank}_q{percent}', 'kind': 'fine', 'percent': percent, 'rank': rank,
                                 **fine_quantile_threshold(req, percent=percent)})
        policies.append({'id': 'keep_all', 'kind': 'keep_all', 'percent': 100, 'rank': None, 'status': 'available'})
        receipt = {'frozen_utc': utc(), 'plan_sha256': sha(output / 'plan.json'),
                   'calibration_scores_sha256': sha(output / 'calibration-scores.npz'), 'policies': policies,
                   'fitting_inputs': 'Calibration scores only; ranks and percentages fixed by plan.'}
        write(output / 'thresholds.json', receipt)
        print('Thresholds frozen; building exact evaluation scores', flush=True)
        eva = build_residual_score_bundle(product_path, split.evaluation, anchor_bin=anchor,
                                         designated_half_width=anchors.DESIGNATED_HALF_WIDTH, bulk_mask=bulk)
        eva.save(output / 'evaluation-scores.npz')
        for bundle in (cal, eva):
            for rank in ranks:
                decoded_requirements(bundle, rank)
        results = []
        masks = {}
        data = {}
        for name, bundle in (('calibration', cal), ('evaluation', eva)):
            idx = bundle.source_row_index
            residual = systematic_residuals(product, idx, floor, 1.0)
            if not np.allclose(bundle.exposure_seconds, 16384 / 390625, rtol=0, atol=1e-15):
                raise ValueError('Exposure geometry differs; count-retention comparison needs revision')
            np.savez_compressed(output / f'{name}-context.npz', source_row_index=idx,
                                residual=residual, frame_time=bundle.frame_time,
                                acquisition_index=bundle.acquisition_index,
                                acquisition_event=product.unit_event_id[bundle.acquisition_index],
                                exposure_seconds=bundle.exposure_seconds,
                                coarse_Q=product.view.statistic[idx])
            data[name] = (bundle, residual)
        for policy in policies:
            record = {**policy, 'physical_recovery_certified': False, 'claim_status': 'diagnostic_only'}
            for name, (bundle, residual) in data.items():
                if policy['kind'] == 'keep_all':
                    keep = np.ones(bundle.frame_count, dtype=bool)
                elif policy['kind'] == 'coarse' and policy.get('eta') is not None:
                    keep = ~product.view.rejected_at_multiplier(policy['eta'])[bundle.source_row_index]
                elif policy.get('eta_q16') is not None:
                    keep = fine_keep(decoded_requirements(bundle, policy['rank']), policy['eta_q16'])
                else:
                    keep = np.zeros(bundle.frame_count, dtype=bool)
                masks[f'{name}__{policy["id"]}'] = keep
                record[name] = block_summary(keep, bundle, residual, floor.linear, gain, budgets)
                if name == 'calibration':
                    mid = 0.5 * (float(bundle.frame_time.min()) + float(bundle.frame_time.max()))
                    early = block_summary(keep, bundle, residual, floor.linear, gain, budgets, bundle.frame_time <= mid)
                    late = block_summary(keep, bundle, residual, floor.linear, gain, budgets, bundle.frame_time > mid)
                    record['calibration_halves'] = {
                        'midpoint': mid, 'early': early, 'late': late,
                        'cost_ratio': ratio(early['mask_only_cost_restore_one_retained_year'], late['mask_only_cost_restore_one_retained_year']),
                        'allowance_ratio': ratio(early['allowance'], late['allowance']),
                        'both_30_kept': early['kept'] >= 30 and late['kept'] >= 30,
                    }
            record['calibration_to_evaluation'] = {
                'cost_ratio': ratio(record['calibration']['mask_only_cost_restore_one_retained_year'], record['evaluation']['mask_only_cost_restore_one_retained_year']),
                'allowance_ratio': ratio(record['calibration']['allowance'], record['evaluation']['allowance']),
            }
            results.append(record)
        np.savez_compressed(output / 'masks.npz', **masks)
        overlaps = []
        for name in data:
            reference = masks[f'{name}__coarse_q50']
            for policy in policies:
                overlaps.append({'block': name, 'reference': 'coarse_q50', 'policy': policy['id'],
                                 **overlap_2x2(reference, masks[f'{name}__{policy["id"]}'])})
        write(output / 'overlaps.json', overlaps)
        # The common controls must reproduce the previous archived replay.
        for prior_id, new_id in (('cal_q0.5', 'coarse_q50'), ('cal_q0.9', 'coarse_q90'), ('keep_all', 'keep_all')):
            old = next(p for p in prior['policies'] if p['policy'] == prior_id)
            new = next(p for p in results if p['id'] == new_id)
            for name in data:
                if old[name]['kept'] != new[name]['kept'] or not math.isclose(old[name]['G1_allowance'], new[name]['allowance'], rel_tol=1e-12):
                    raise ValueError('Previous common control differs: ' + new_id)
        write(output / 'results.json', {'completed_utc': utc(), 'plan_sha256': sha(output / 'plan.json'),
                                       'thresholds_sha256': sha(output / 'thresholds.json'),
                                       'policies': results, 'prior_common_controls_reproduced': True,
                                       'physical_recovery_certified': False})
        flat = []
        for p in results:
            row = {k: p.get(k) for k in ('id', 'kind', 'rank', 'percent', 'eta', 'eta_q16', 'status')}
            for name in data:
                row.update({name + '_' + k: v for k, v in p[name].items() if not isinstance(v, dict)})
                for world in budgets:
                    for par in ('dilation', 'fs8'):
                        row[name + '_' + world + '_' + par + '_R'] = p[name]['pricing'][world][par]['R']
            row.update(calibration_half_cost_ratio=p['calibration_halves']['cost_ratio'],
                       calibration_half_allowance_ratio=p['calibration_halves']['allowance_ratio'])
            flat.append(clean(row))
        with (output / 'comparison.csv').open('x', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(flat[0]))
            writer.writeheader()
            writer.writerows(flat)
    for path, expected in identities.items():
        if sha(path) != expected:
            raise ValueError('Input changed during analysis: ' + path)
    write(output / 'manifest.json', {'completed_utc': utc(), 'passed_integrity': True,
                                   'physical_recovery_certified': False,
                                   'files': {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob('*'))
                                             if p.is_file()}})
    print(json.dumps({'policies': len(results), 'passed_integrity': True, 'output': str(output)}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, default=RAIL / 'results/canfar_reanalysis_2026-09-09')
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args())
