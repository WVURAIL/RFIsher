#!/usr/bin/env python3
"""Measure predeclared native lags from an authenticated retained-byte release."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

import numpy as np

from rfisher_results.validation.lag_moments import frame_moments, lag_moments, summarize_lags
from rfisher_results.validation.voltage_coherence import decode_excess8


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_sources(plan):
    source = Path(plan['source'])
    for relative, expected in plan['source_files_sha256'].items():
        if sha(source/relative) != expected:
            raise ValueError(f"source changed: {relative}")


def run(study):
    plan = json.loads((study/'plan.json').read_text())
    verify_sources(plan)
    if (study/'data').exists():
        raise FileExistsError('measurement outputs already exist')
    os.nice(10)
    for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:
        if os.environ.get(key) != '1':
            raise ValueError(f'{key} must be 1')
    (study/'data').mkdir(); (study/'source_snapshots').mkdir()
    repo = Path(__file__).resolve().parents[1]
    source_paths = [Path(__file__), repo/'src/rfisher_results/validation/lag_moments.py',
                    repo/'src/rfisher_results/validation/voltage_coherence.py',
                    repo/'tests/test_lag_moments.py']
    snapshots = {}
    for path in source_paths:
        target = study/'source_snapshots'/path.name
        shutil.copyfile(path, target); snapshots[path.name] = sha(target)
    (study/'implementation-before-run.json').write_text(json.dumps({
        'frozen_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'plan_sha256':sha(study/'plan.json'), 'source_sha256':snapshots},indent=2)+'\n')
    start = time.monotonic(); summaries=[]
    lags=np.asarray(plan['lags_samples']); pairs=np.asarray(plan['visibility_pair_slots'])
    original_summary=json.loads((Path(plan['source'])/'summary.json').read_text())
    payloads={r['freq_id']:r for r in original_summary['frequencies']}
    for freq in plan['frequency_ids']:
        relative=f'data/ch{freq:04d}.npz'
        with np.load(Path(plan['source'])/relative) as source:
            packed=source['packed']
        if sha(Path(plan['source'])/relative) != plan['source_files_sha256'][relative]:
            raise ValueError('source payload changed')
        if hashlib.sha256(packed.tobytes()).hexdigest()!=payloads[freq]['selected_packed_sha256']:
            raise ValueError('packed byte hash mismatch')
        x=decode_excess8(packed); z=x[:,pairs[:,0]]*x[:,pairs[:,1]].conj()
        vm=packed != 0; zm=vm[:,pairs[:,0]] & vm[:,pairs[:,1]]
        output={'lags_samples':lags,'pair_slots':pairs}
        for kind, values, mask in [('voltage',x,vm),('visibility',z,zm)]:
            all_m=lag_moments(values,lags)
            all_s=summarize_lags(all_m)
            all_f=frame_moments(values,plan['frame_samples'])
            for policy in ['all','exclude_00']:
                if policy=='all' or mask.all():
                    moments,stats,frames=all_m,all_s,all_f
                else:
                    moments=lag_moments(values,lags,mask); stats=summarize_lags(moments)
                    frames=frame_moments(values,plan['frame_samples'],mask)
                output.update({f'{kind}_{policy}_{key}':value for key,value in {**moments,**stats}.items()})
                output.update({f'{kind}_{policy}_frame_{key}':value for key,value in frames.items()})
        out=study/relative
        np.savez_compressed(out,**output)
        centered=np.abs(output['voltage_all_normalized_centered'])
        row={'freq_id':freq,'frequency_mhz':payloads[freq]['frequency_mhz'],
             'file':relative,'sha256':sha(out),'zero_code_count':int((packed==0).sum()),
             'minimum_support':int(output['voltage_all_count'].min()),
             'median_voltage_centered_abs_by_lag':np.median(centered,axis=1).tolist(),
             'median_visibility_centered_abs_by_lag':np.median(np.abs(output['visibility_all_normalized_centered']),axis=1).tolist()}
        summaries.append(row)
        print(json.dumps({'completed_freq_id':freq,'elapsed_seconds':round(time.monotonic()-start,2)}),flush=True)
    verify_sources(plan)
    summary={'schema':'inband-native-lag-summary-v1','plan_sha256':sha(study/'plan.json'),
             'elapsed_seconds':time.monotonic()-start,'created_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
             'source_files_unchanged':True,'channels':summaries,'independent_validation':False,
             'physical_calibration':False,'numpy_version':np.__version__,'thread_limits':{k:os.environ[k] for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']}}
    (study/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',type=Path,required=True)
    args=parser.parse_args(); run(args.study.resolve())
