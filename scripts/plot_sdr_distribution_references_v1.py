#!/usr/bin/env python3
"""Plot two source-bound PDF references without refitting their theoretical laws."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import f, ncf


def render(study, output=None):
    plan_bytes = (study/'plan.json').read_bytes()
    summary = json.loads((study/'summary.json').read_text())
    if hashlib.sha256(plan_bytes).hexdigest() != summary['plan_sha256']:
        raise ValueError('Summary does not bind this plan')
    plt.rcParams.update({'text.usetex': True, 'font.family': 'serif',
                         'font.serif': ['Latin Modern Roman'], 'font.size': 12,
                         'text.latex.preamble': r'\usepackage{lmodern}',
                         'axes.spines.top': False, 'axes.spines.right': False})
    output = study/'figures' if output is None else Path(output)
    output.mkdir(exist_ok=True)
    outputs = []
    stages = [('natural_float', 'Floating adapter', '#16806A'),
              ('quantized_weights_float', 'Quantized weights', '#BD6D00'),
              ('packed', 'Packed adapter', '#0068A9')]
    for case, title in [('noise', 'Noise-only reference'), ('steady', 'Steady tone plus noise reference')]:
        values = summary['cases'][case]
        law = f(256, 512) if case == 'noise' else ncf(256, 512, 2304)
        fig, ax = plt.subplots(figsize=(10, 7.2))
        fig.subplots_adjust(left=.11, right=.97, bottom=.38, top=.86)
        for stage, label, color in stages:
            row = values['stages'][stage]
            edges = np.asarray(row['histogram_edges'])
            density = np.asarray(row['histogram_counts'])/(row['count']*np.diff(edges))
            ax.stairs(density, edges, color=color, linewidth=1.5,
                      linestyle='--' if stage == 'quantized_weights_float' else '-',
                      label='GNU Radio: '+label.lower(), zorder=3)
            if stage == 'packed':
                ax.stairs(density, edges, color=color, fill=True, alpha=.12, zorder=1)
        x = np.linspace(edges[0], edges[-1], 1500)
        ideal = r'Ideal $F(256,512)$' if case == 'noise' else r'Ideal noncentral $F(256,512;2304)$'
        ax.plot(x, law.pdf(x), color='#303030', linewidth=2, label=ideal, zorder=4)
        ax.set(xlabel=r'Coarse frame ratio $Q$', ylabel='Probability density',
               xlim=(edges[0], edges[-1]), ylim=(0, None))
        ax.legend(loc='upper right', fontsize=9, frameon=False)
        fig.suptitle(title, fontsize=18, y=.96)
        fig.text(.5, .905, r'One input $\mid$ 16,384 samples/frame $\mid$ $K=L=128$ $\mid$ 1,128 frames per case',
                 ha='center', fontsize=11)
        ideal_row = values['ideal_reference']
        rows = [['Ideal', f"{ideal_row['mean']:.5f}", f"{ideal_row['median']:.5f}", f"{ideal_row['std']:.5f}"]]
        for stage, label, _ in stages:
            r = values['stages'][stage]
            rows.append([label, f"{r['mean']:.5f}", f"{r['median']:.5f}", f"{r['std_ddof1']:.5f}"])
        table = ax.table(cellText=rows, colLabels=['Reference', 'Mean', 'Median', 'Std. deviation'],
                         cellLoc='center', colLoc='center', bbox=[.02, -.50, .96, .32])
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        for (row, _), cell in table.get_celld().items():
            cell.set_edgecolor('#dddddd')
            cell.set_linewidth(.4)
            if row == 0:
                cell.set_facecolor('#eeeeee')
        tails = sum(values['stages']['packed'][key] for key in ('histogram_underflow','histogram_overflow'))
        fig.text(.02, .095, 'Theory fixes the full-band ideal noise level and tone amplitude; no fitted normalization.', fontsize=10)
        fig.text(.02, .066, 'Simulation uses the actual FIR and fixed scale 5. Twenty-four independent records; within-record frames may depend.', fontsize=9)
        fig.text(.02, .039, f'Packed histogram: {tails} observations outside the displayed range. Qualified SDR reference curves remain unavailable.', fontsize=9)
        metadata = {'Title': title, 'CreationDate': datetime(2026, 9, 9, tzinfo=timezone.utc),
                    'ModDate': datetime(2026, 9, 9, tzinfo=timezone.utc)}
        fig.savefig(output/(case+'-reference.pdf'), metadata=metadata)
        fig.savefig(output/(case+'-reference.png'), dpi=170)
        outputs.append(output/(case+'-reference.pdf'))
        plt.close(fig)
    return outputs


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study', type=Path)
    render(parser.parse_args().study.resolve())
