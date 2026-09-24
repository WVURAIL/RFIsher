#!/usr/bin/env python3
"""Render descriptive null-calibration figures from a completed diagnostic."""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
from scipy.stats import betabinom, binom

BLUE, GOLD, RED = '#0062A3', '#7F6310', '#8D4638'
plt.rcParams.update({'text.usetex': True, 'font.family': 'serif',
                     'text.latex.preamble': r'\usepackage[T1]{fontenc}\usepackage{lmodern}',
                     'font.size': 9, 'axes.labelsize': 9, 'axes.titlesize': 10,
                     'legend.fontsize': 8, 'axes.spines.top': False,
                     'axes.spines.right': False, 'pdf.fonttype': 42})


def read_csv(path):
    with path.open() as f:
        return list(csv.DictReader(f))


def save(fig, root, stem):
    epoch = datetime(2026, 9, 9, tzinfo=timezone.utc)
    fig.savefig(root/(stem+'.pdf'), bbox_inches='tight', metadata={'CreationDate': epoch, 'ModDate': epoch})
    fig.savefig(root/(stem+'.png'), bbox_inches='tight', dpi=190)
    plt.close(fig)


def plot(root):
    summary = json.loads((root/'summary.json').read_text())
    rows = read_csv(root/'policy_diagnostics.csv')
    fine = [r for r in rows if r['kind']=='fine' and float(r['pfa'])==.01]
    require_count = 644
    assert len(fine) == require_count
    k = np.array([int(r['validation_exceedances']) for r in fine])
    bins = np.arange(-.5, 220.5, 10)
    x = np.arange(0, 220)
    base = binom.pmf(x, 10000, .01)
    predictive = betabinom.pmf(x, 10000, 40, 3961)
    fig, ax = plt.subplots(1, 2, figsize=(8.7, 3.7), gridspec_kw={'width_ratios':[1.35,1]})
    observed, _ = np.histogram(k, bins)
    ax[0].stairs(observed/len(fine), bins, fill=True, alpha=.23, color=BLUE, label='644 fine policies (shared trials)')
    for values, color, label in [(base, GOLD, r'Fixed true false-alarm rate: 1\%'),
                                 (predictive, BLUE, 'Including 4,000-draw calibration')]:
        heights, _ = np.histogram(x, bins, weights=values)
        ax[0].stairs(heights, bins, color=color, linewidth=1.5, label=label)
    ax[0].axvline(146.5, color=RED, linestyle='--', linewidth=1, label='Cap demonstrated: at most 146')
    ax[0].set(xlabel='False alarms in 10,000 validation trials', ylabel='Fraction per 10-count bin',
              title='(a) Calibration broadens validation outcomes', xlim=(29.5, 199.5))
    ax[0].legend(loc='upper center', bbox_to_anchor=(.5,-.22), fontsize=7)
    failed = summary['failed_distinct']
    labels = [f"ch {r['channel']}, rank {r['rank']}" for r in failed]
    for i,r in enumerate(failed):
        q,f = r['validation_exceedances'],r['fixed_float_exceedances']
        ax[1].plot([q,f],[i,i],color='#555555',lw=1)
        ax[1].scatter(q,i,color=BLUE,s=32,label='Exact Q16' if i==0 else None,zorder=3)
        ax[1].scatter(f,i,color=GOLD,marker='x',s=38,label='Fixed transform, float decision' if i==0 else None,zorder=4)
    ax[1].axvline(146.5, color=RED, linestyle='--', linewidth=1)
    ax[1].set(yticks=range(len(labels)), yticklabels=labels, xlabel='False alarms in 10,000 trials',
              title='(b) Six distinct failing policies', xlim=(143,167))
    ax[1].invert_yaxis()
    ax[1].legend(loc='upper center', bbox_to_anchor=(.5,-.22), fontsize=7)
    fig.subplots_adjust(wspace=.4, bottom=.22)
    fig.text(.02,-.15, 'Same-null IID reference; policy rows are dependent. Each stage uses its own frozen calibration threshold.\n'
             'At the common Q16 boundary, all paired decisions agree. Failed policies are a post-inspection subset.', fontsize=8)
    save(fig, root, 'null_calibration_diagnosis')

    designs = read_csv(root/'prospective_designs.csv')
    cn = sorted({int(r['calibration_trials']) for r in designs})
    vn = sorted({int(r['validation_trials']) for r in designs})
    values = np.array([[float(next(r for r in designs if int(r['calibration_trials'])==c and int(r['validation_trials'])==v)['family_acceptance_lower_bound']) for v in vn] for c in cn])
    fig, ax = plt.subplots(figsize=(6.6,3.8))
    im = ax.imshow(values, vmin=0, vmax=1, cmap='Blues', aspect='auto')
    for i in range(len(cn)):
        for j in range(len(vn)):
            v=values[i,j]
            label = r'$>99.99\%$' if v>.9999 else (r'$0^\ast$' if v==0 else f'{100*v:.2f}'+r'\%')
            ax.text(j,i,label,ha='center',va='center',color='white' if v>.65 else 'black')
    ax.add_patch(Rectangle((.5,.5),1,1,fill=False,edgecolor=GOLD,linewidth=2.5))
    ax.set(xticks=range(len(vn)), xticklabels=[f'{v:,}' for v in vn],
           yticks=range(len(cn)), yticklabels=[f'{c:,}' for c in cn],
           xlabel='Fresh validation trials per policy', ylabel='Fresh calibration trials per profile',
           title='Prospective probability of passing the entire frozen-size family\nUnion-bound lower bound; 667 rows at each nominal level')
    fig.colorbar(im, ax=ax, label='All-family acceptance probability lower bound')
    fig.text(.01,-.08, r'$^\ast$Zero means the bound is uninformative, not that acceptance is impossible.'+'\n'
             'Continuous IID same-null planning reference; no independence between policies is required.\n'
             'Each cell describes a new fixed-count design. It does not extend or retune the running campaign.', fontsize=8)
    fig.tight_layout()
    save(fig, root, 'null_validation_prospective_design')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('diagnostic',type=Path)
    plot(ap.parse_args().diagnostic.resolve())
