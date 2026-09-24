#!/usr/bin/env python3
"""Separate, descriptive analysis of a completed frozen null-validation phase.

Freeze an explicit input inventory with --freeze, then run without that flag.
No campaign outputs, seeds, thresholds or scientific verdicts are changed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
import platform
import sys

import numpy as np
import scipy
from scipy.stats import binom

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from rfisher_results.validation.null_calibration import (
    calibration_reference, family_power_lower_bound, gate_count_limit,
    prospective_power,
)

MODULE = ROOT/'src/rfisher_results/validation/null_calibration.py'
Q16 = 'atsc_8vsb_fixed_transform_q16_cpu'
FIXED_FLOAT = 'atsc_8vsb_fixed_transform_float_decision'
STAGES = ['ideal_tone_float', 'atsc_8vsb_float', 'atsc_8vsb_input_int4_float',
          'atsc_8vsb_weight_int4_float', 'atsc_8vsb_joint_int4_float_transform', FIXED_FLOAT]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n')


def csv_save(path, rows):
    with Path(path).open('x', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def freeze(campaign, out):
    require(not out.exists(), 'output already exists; use a distinct analysis directory')
    cal_manifest = read(campaign/'scores/null_calibration/manifest.json')
    report = read(campaign/'reports/null_validation/report.json')
    files = ['plan.json', 'calibration.json', 'calibration.sha256',
             'scores/null_calibration/manifest.json', 'reports/null_validation/report.json',
             'reports/null_validation/report.sha256']
    for ch in range(14, 37):
        for rel in [f'scores/null_calibration/ch{ch}.npz', f'scores/null_calibration/ch{ch}.json']:
            require(digest(campaign/rel) == cal_manifest['outputs_sha256'][rel], 'calibration source mismatch '+rel)
            files.append(rel)
        rel = f'reports/null_validation/ch{ch}.npz'
        require(digest(campaign/rel) == report['outputs_sha256'][rel], 'validation source mismatch '+rel)
        files.append(rel)
    out.mkdir(parents=True)
    plan = {
        'schema': 'fine-null-calibration-diagnostic-plan-v1',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'descriptive reuse of previously inspected completed digital null data; not prospective validation',
        'campaign': str(campaign), 'campaign_files': {r: digest(campaign/r) for r in files},
        'analysis_sources': {str(p): digest(p) for p in [Path(__file__).resolve(), MODULE]},
        'cohort': 'every frozen primary row, including repeated geometry rows and both nominal levels',
        'failed_subset': 'post-hoc descriptive detail only; no selected-row confidence claim',
        'analyses': ['strict-threshold calibration and validation recounts',
                     'all-six-stage paired comparisons using independently calibrated stage thresholds',
                     'fixed-float comparison also at the Q16 threshold divided by 65536',
                     'continuous-IID order-statistic and beta-binomial reference',
                     'prospective fixed-count mixed-family power via union bound'],
        'prospective_calibration_trials': [4000, 8000, 16000, 32000],
        'prospective_validation_trials': [10000, 20000, 40000, 80000],
        'fixed_true_p_grid': [.005, .01, .012, .014, .016, .018, .02],
        'changes_to_campaign': False, 'new_trial_generation': False,
        'physical_certification': False,
    }
    save(out/'plan.json', plan)
    (out/'plan.sha256').write_text(digest(out/'plan.json')+'\n')
    print('Frozen diagnostic input inventory:', len(files), 'files', flush=True)


def verify_inputs(plan, campaign):
    for rel, want in plan['campaign_files'].items():
        require(digest(campaign/rel) == want, 'frozen input changed: '+rel)
    for path, want in plan['analysis_sources'].items():
        require(digest(path) == want, 'analysis source changed after plan: '+path)


def run(campaign, out):
    require(digest(out/'plan.json') == (out/'plan.sha256').read_text().strip(), 'plan digest mismatch')
    plan = read(out/'plan.json')
    require(plan['campaign'] == str(campaign), 'campaign path differs from plan')
    verify_inputs(plan, campaign)
    require(not (out/'summary.json').exists(), 'completed output already exists')
    original = read(campaign/'plan.json')
    cal = read(campaign/'calibration.json')
    report = read(campaign/'reports/null_validation/report.json')
    nc, nv = original['counts']['null_calibration'], report['trials_per_policy']
    family = original['false_alarm_gate']
    require((nc, nv, family['family_tests'], family['confidence'], family['cap_multiple']) == (4000, 10000, 1334, .95, 2.), 'unexpected frozen design')
    require(cal['plan_sha256'] == report['plan_sha256'] == digest(campaign/'plan.json'), 'plan binding mismatch')
    require(digest(campaign/'calibration.json') == (campaign/'calibration.sha256').read_text().strip(), 'calibration binding mismatch')
    require(digest(campaign/'reports/null_validation/report.json') == (campaign/'reports/null_validation/report.sha256').read_text().strip(), 'report binding mismatch')
    primary = [r for r in report['rows'] if r.get('primary_family')]
    require(len(primary) == 1334, 'primary family incomplete')
    require(sum(not r['gate_passed'] for r in primary) == 8, 'frozen primary outcome differs')
    lookup = {(r['channel'], r.get('geometry_slot'), r.get('rank_index'), r['pfa'], r['stage'], r['kind']): r for r in report['rows']}
    rows, stage_rows = [], []
    for ch in range(14, 37):
        with np.load(campaign/f'scores/null_calibration/ch{ch}.npz', allow_pickle=False) as f:
            c = {k: f[k] for k in f.files}
        with np.load(campaign/f'reports/null_validation/ch{ch}.npz', allow_pickle=False) as f:
            v = {k: f[k] for k in f.files}
        meta = json.loads(str(c['meta_json']))
        require(meta['float_stages'] == STAGES, 'stage order differs')
        for r in [r for r in primary if r['channel'] == ch]:
            p = r['pfa']; is_fine = r['kind'] == 'fine'
            slot, ri = r.get('geometry_slot'), r.get('rank_index')
            if is_fine:
                require(r['stage'] == Q16 and meta['anchors'][slot] == r['anchor'] and meta['ranks'][slot][ri] == r['rank'], 'fine geometry differs')
                cq, vq = c['required_q16'][:, slot, ri], v['required_q16'][:, slot, ri]
                require(c['fixed_valid'][:, slot, ri].all() and v['fixed_valid'][:, slot, ri].all(), 'invalid primary score')
                require(not c['always_masked'][:, slot, ri].any() and not v['always_masked'][:, slot, ri].any(), 'sentinel primary score')
                entry = cal['fine'][f'ch{ch}'][str(r['anchor'])][Q16][str(r['rank'])][str(p)]
            else:
                cq, vq = c['coarse_float'][:, 5], v['coarse_float'][:, 5]
                require(c['coarse_valid'][:, 5].all() and v['coarse_valid'][:, 5].all(), 'invalid coarse score')
                entry = cal['coarse'][f'ch{ch}'][FIXED_FLOAT][str(p)]
            require((cq.shape, vq.shape) == ((nc,), (nv,)), 'trial shape differs')
            t = r['threshold']; idx = entry['index']
            require(entry['threshold'] == t and np.partition(cq, idx)[idx] == t, 'threshold not recorded calibration order statistic')
            decision = vq > t
            require(int(decision.sum()) == r['exceedances'], 'primary decision recount differs')
            row = {k: r.get(k) for k in ['kind', 'channel', 'geometry_slot', 'anchor', 'rank', 'rank_index', 'pfa', 'threshold']}
            row.update(calibration_rank=idx+1, calibration_strict_exceedances=int((cq>t).sum()), calibration_equal_threshold=int((cq==t).sum()),
                       validation_exceedances=int(decision.sum()), validation_equal_threshold=int((vq==t).sum()),
                       validation_rate=float(decision.mean()), frozen_gate_passed=r['gate_passed'],
                       simultaneous_upper=r['statistics']['simultaneous_upper']['upper'])
            row.update(fixed_float_own_threshold=None, fixed_float_exceedances=None,
                       fixed_float_only=None, q16_only=None, paired_disagreements=None,
                       fixed_float_common_q16_boundary_exceedances=None, common_boundary_disagreements=None)
            if is_fine:
                for si, stage in enumerate(STAGES):
                    sr = lookup[(ch, slot, ri, p, stage, 'fine')]
                    ce = cal['fine'][f'ch{ch}'][str(r['anchor'])][stage][str(r['rank'])][str(p)]
                    cf, vf = c['fine_float'][:, slot, si, ri], v['fine_float'][:, slot, si, ri]
                    require(c['fine_valid'][:, slot, si, ri].all() and v['fine_valid'][:, slot, si, ri].all(), 'undefined floating score')
                    ft = ce['threshold']
                    require(ft == sr['threshold'] and np.partition(cf, ce['index'])[ce['index']] == ft, 'floating calibration mismatch')
                    fd = vf > ft
                    require(int(fd.sum()) == sr['exceedances'], 'floating recount differs')
                    stage_rows.append(dict(channel=ch, geometry_slot=slot, anchor=r['anchor'], rank=r['rank'], rank_index=ri,
                                           pfa=p, stage=stage, threshold=ft, calibration_equal_threshold=int((cf==ft).sum()),
                                           validation_exceedances=int(fd.sum()), stage_only=int((fd & ~decision).sum()),
                                           q16_only=int((~fd & decision).sum()), paired_disagreements=int((fd!=decision).sum())))
                    if stage == FIXED_FLOAT:
                        common = vf > float(t)/65536
                        row.update(fixed_float_own_threshold=ft, fixed_float_exceedances=int(fd.sum()),
                                   fixed_float_only=int((fd & ~decision).sum()), q16_only=int((~fd & decision).sum()),
                                   paired_disagreements=int((fd != decision).sum()),
                                   fixed_float_common_q16_boundary_exceedances=int(common.sum()),
                                   common_boundary_disagreements=int((common != decision).sum()))
            rows.append(row)
        print('Recounted channel', ch, flush=True)
    references = []
    for kind in ['fine', 'coarse']:
        for p in [.01, .05]:
            group = [r for r in rows if r['kind'] == kind and r['pfa'] == p]
            ref = prospective_power(nc, nv, p)
            ref.update(kind=kind, policy_rows=len(group), observed_failed_rows=sum(not r['frozen_gate_passed'] for r in group),
                       expected_failed_rows_continuous_reference=len(group)*ref['single_policy_failure_probability'],
                       calibration_reference=calibration_reference(nc, p))
            references.append(ref)
    powers = []
    for cn in plan['prospective_calibration_trials']:
        for vn in plan['prospective_validation_trials']:
            values = [prospective_power(cn, vn, p) for p in [.01, .05]]
            counts = [sum(r['pfa'] == p for r in rows) for p in [.01, .05]]
            fail = [v['single_policy_failure_probability'] for v in values]
            powers.append(dict(calibration_trials=cn, validation_trials=vn,
                               accepted_max_at_1pct=values[0]['accepted_exceedances_max'],
                               accepted_max_at_5pct=values[1]['accepted_exceedances_max'],
                               single_row_failure_at_1pct=fail[0], single_row_failure_at_5pct=fail[1],
                               expected_family_failed_rows=sum(n*p for n,p in zip(counts, fail)),
                               family_acceptance_lower_bound=family_power_lower_bound([fail[0]]*counts[0]+[fail[1]]*counts[1])))
    fixed_power = [dict(validation_trials=vn, true_pfa=p,
                        cap=.02, accepted_exceedances_max=gate_count_limit(vn, .01),
                        single_policy_acceptance_power=float(binom.cdf(gate_count_limit(vn, .01), vn, p)))
                   for vn in plan['prospective_validation_trials'] for p in plan['fixed_true_p_grid']]
    failed = [r for r in rows if not r['frozen_gate_passed']]
    unique = list({(r['channel'],r['anchor'],r['rank'],r['pfa']): r for r in failed}.values())
    summary = dict(schema='fine-null-calibration-diagnostic-v1', completed_utc=datetime.now(timezone.utc).isoformat(),
                   plan_sha256=digest(out/'plan.json'), input_count=len(plan['campaign_files']),
                   primary_rows=len(rows), paired_stage_rows=len(stage_rows),
                   failed_primary_rows=len(failed), distinct_failed_policies=len(unique),
                   failed_distinct=unique, reference_predictions=references,
                   max_paired_fixed_float_q16_disagreements=max(r['paired_disagreements'] for r in rows if r['kind']=='fine'),
                   max_failed_policy_disagreements=max(r['paired_disagreements'] for r in failed),
                   max_common_boundary_disagreements=max(r['common_boundary_disagreements'] for r in rows if r['kind']=='fine'),
                   scientific_gate_passed=False, campaign_changed=False, new_trials_generated=False,
                   python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__,
                   interpretation='Finite-calibration reference can produce cap refusals despite a nominal 1% target. Agreement in expected count is not a goodness-of-fit test or a causal diagnosis.',
                   limits=['The event count across policies is dependent; no binomial model for number of failed rows is used.',
                           'Order-statistic and beta-binomial results assume IID calibration/validation scores from the same null law.',
                           'The exact Beta law is continuous-score reference; strict discrete ties are stochastically conservative.',
                           'The six failed distinct policies are selected after inspection; their detail is descriptive.',
                           'Each stage has its own calibrated threshold; paired counts do not measure representation loss at a common operating point.',
                           'Prospective grids are hypothetical fresh fixed-count designs, not extensions of this campaign.',
                           'No physical receiver-noise certification or all-signal sensitivity acceptance is implied.'])
    verify_inputs(plan, campaign)
    save(out/'summary.json', summary)
    csv_save(out/'policy_diagnostics.csv', rows)
    csv_save(out/'paired_stages.csv', stage_rows)
    csv_save(out/'prospective_designs.csv', powers)
    csv_save(out/'fixed_true_p_power.csv', fixed_power)
    save(out/'input-integrity.json', {'all_frozen_inputs_unchanged': True, 'files': plan['campaign_files']})
    print('Finished:', len(rows), 'primary rows;', len(stage_rows), 'paired stage rows', flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--campaign', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--freeze', action='store_true')
    args = ap.parse_args()
    campaign, out = args.campaign.resolve(), args.output.resolve()
    (freeze if args.freeze else run)(campaign, out)
