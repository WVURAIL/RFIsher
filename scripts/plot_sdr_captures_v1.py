#!/usr/bin/env python3
"""Render three descriptive pages from the frozen retained-capture measurements."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--pdf', type=Path, required=True)
    parser.add_argument('--png-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.pdf.exists():
        raise FileExistsError(args.pdf)
    args.pdf.parent.mkdir(parents=True, exist_ok=True)
    args.png_dir.mkdir(parents=True, exist_ok=True)
    data = [json.loads((args.study/'measurements'/f'smoke-{i:03d}.json').read_text()) for i in range(1, 8)]
    colors = ['#66788A', '#557C4C', '#D08B35', '#4165A4']
    plt.rcParams.update({'font.size': 9, 'axes.spines.top': False,
                         'axes.spines.right': False, 'pdf.fonttype': 42})
    with PdfPages(args.pdf, metadata={'Title': 'Retained SDR smoke-capture diagnostics',
                                    'Author': 'RFIsher development evidence'}) as pdf:
        fig, axes = plt.subplots(2, 2, figsize=(11, 8.5), sharex=True, sharey=True)
        fig.subplots_adjust(left=.085, right=.97, bottom=.205, top=.80, hspace=.29, wspace=.17)
        fig.suptitle('Effect on the measured 100 kHz smoke path', x=.085, ha='left', y=.975, fontsize=18)
        fig.text(.085, .89, 'All four successful transports retained; 1 ms fixed-frequency projections in saved IQ units.\n'
                 'The gold interval is the scheduled 50 ms tone. Zero guards have TX enabled.', fontsize=10)
        for ax, d in zip(axes.flat, data[3:]):
            rows = d['timeline']
            time = np.array([r['center_seconds']*1000 for r in rows])
            ax.plot(time, [r['tone_projection_power'] for r in rows], color='#205E9B', lw=1.15, label='100 kHz smoke projector')
            ax.plot(time, [r['line_projection_power'] for r in rows], color='#89928C', lw=1.1, label='+309.9 kHz diagnostic')
            ax.axvspan(50, 100, color='#E9C774', alpha=.24)
            for edge in (0, 50, 100): ax.axvline(edge, color='#777777', ls=':', lw=.7)
            ax.set_yscale('log'); ax.set_ylim(1e-11, 1e-3); ax.set_xlim(-60, 125)
            ax.grid(axis='y', alpha=.18)
            verdict = 'local-tone rule passed' if d['attempt']=='smoke-007' else 'original global-peak rule failed'
            ax.set_title(f"{d['attempt']} | TX gain readback {d['native_tx_gain_db_readback']}\n{verdict}", fontsize=10, loc='left')
        axes[0, 0].legend(loc='lower left', fontsize=8, frameon=False)
        for ax in axes[:, 0]: ax.set_ylabel('Projection power [IQ units squared]')
        for ax in axes[-1, :]: ax.set_xlabel('Time relative to scheduled TX payload [ms]')
        fig.text(.085, .09, 'A strong peak elsewhere does not by itself invalidate this projector. The next page quantifies its fitted coupling.\n'
                 'Captures stop near +128.5 ms: only 28.5 ms of the 50 ms trailing zero guard are recorded. Native gain is not measured dBm.', fontsize=9)
        fig.text(.97, .035, 'Development captures | 1 / 3', ha='right', fontsize=8, color='#555555')
        pdf.savefig(fig); fig.savefig(args.png_dir/'sdr-diagnostics-1.png', dpi=160); plt.close(fig)

        fig, axes = plt.subplots(2, 2, figsize=(11, 8.5))
        fig.subplots_adjust(left=.085, right=.97, bottom=.23, top=.80, hspace=.42, wspace=.30)
        fig.suptitle('Projector sensitivity, short-interval variation and startup', x=.085, ha='left', y=.975, fontsize=17)
        fig.text(.085, .89, 'No additional transmissions. All windows and diagnostic bands were fixed before this new payload analysis.\n'
                 'Two-sinusoid fits describe a narrow component; they do not bound all interference or qualify physical noise.', fontsize=10)
        ax = axes[0,0]
        change = [d['windows']['tone']['joint_projection']['joint_vs_single_power_change_db']*1000 for d in data[3:]]
        ax.bar(['004','005','006','007'], change, color=colors, width=.55)
        ax.axhline(0, color='#444444', lw=.7); ax.set_ylim(-9, 39)
        for i, value in enumerate(change): ax.text(i, value+(1.2 if value>=0 else -1.8), f'{value:.2f}', ha='center', va='bottom' if value>=0 else 'top', fontsize=8)
        ax.set_title('A  |  Joint fit changes the tone projection very little', fontsize=10, loc='left')
        ax.set_ylabel('Joint minus original power [millidB]'); ax.set_xlabel('Smoke attempt; fixed 60-90 ms window')
        ax.grid(axis='y', alpha=.18)
        ax = axes[0,1]
        for d, color in zip(data[5:], colors[2:]):
            rows = [r for r in d['five_ms'] if .06<=r['center_seconds']<.09]
            power = np.array([r['tone']['fixed_projection_power'] for r in rows])
            ax.plot([r['center_seconds']*1000 for r in rows], 10*np.log10(power/np.median(power)), 'o-', color=color, ms=4, label=d['attempt'])
        ax.axhline(0, color='#888888', lw=.6); ax.set_ylim(-.2,.2)
        ax.set_title('B  |  Strong-tone variation over six 5 ms blocks', fontsize=10, loc='left')
        ax.set_xlabel('Time relative to scheduled TX payload [ms]'); ax.set_ylabel('Projection power relative to median [dB]')
        ax.legend(frameon=False, fontsize=8); ax.grid(alpha=.18)
        ax = axes[1,0]
        for d, color in zip(data[2:], ['#9C9C9C']+colors):
            rows = [r for r in d['chunk_records'] if r['file']=='startup.cfile']
            time = np.array([r['timestamp'] for r in rows])/d['sample_rate_hz_readback']*1000
            rms = np.sqrt([r['mean_power'] for r in rows])
            ax.plot(time, rms, color=color, lw=1.05, label=d['attempt']+(' (failed)' if d['attempt']=='smoke-003' else ''))
            reset = [i for i,r in enumerate(rows) if r['action']=='startup_reset']
            ax.scatter(time[reset], rms[reset], color=color, s=14, marker='x')
        ax.set_yscale('log'); ax.set_xlabel('Hardware sample timestamp / rate [ms]'); ax.set_ylabel('Chunk RMS [saved IQ units]')
        ax.set_title('C  |  Startup chunks; crosses mark reset decisions', fontsize=10, loc='left')
        ax.legend(frameon=False, fontsize=7, ncol=2); ax.grid(axis='y', alpha=.18)
        ax = axes[1,1]; ax.axis('off')
        rows=[]
        for d in data[3:]:
            z=d['tone_interior_block_diagnostics']['tone']; lo,hi=z['frequency_fit_range_hz']
            rows.append([d['attempt'][-3:], f'{lo-100000:+.1f} to {hi-100000:+.1f}', f"{z['projection_power_max_min_db']:.3f}", 'yes' if z['all_blocks_prominence_at_least_10_db'] else 'no'])
        table=ax.table(cellText=rows, colLabels=['Attempt', 'Fitted offset [Hz]', 'Range [dB]', 'Prominent?'], loc='upper center', cellLoc='center', colWidths=[.16,.40,.22,.22])
        table.auto_set_font_size(False); table.set_fontsize(8); table.scale(1,1.5)
        for (row,col), cell in table.get_celld().items():
            cell.set_edgecolor('#D1D8DE')
            if row==0: cell.set_facecolor('#E8EDF1'); cell.set_text_props(weight='bold')
        ax.set_title('D  |  Tone-interior descriptive ranges', fontsize=10, loc='left', pad=11)
        ax.text(0,.30, 'Six contiguous blocks; FFT spacing 200 Hz. Sub-bin frequency\nfits are not accuracy bounds or confidence intervals.\n"Prominent" is only the predeclared 10 dB diagnostic marker.\n\n001: no IQ. 002/003: failed transports remain retained.\nA failed partial TX-disabled record appears on page 3.', transform=ax.transAxes, va='top', fontsize=8)
        fig.text(.085,.09, 'Scope: the 100 kHz smoke projector, not calibrated ATSC pilot/reference bins. At LO=500 MHz, +309.9 kHz would be near\n'
                 'the nominal channel 19 pilot under RF=LO+offset; source identity and the actual detector mapping remain undetermined.\n'
                 'A future relevant check binds the intended LO, spectral orientation and exact pilot/reference weights to bracketed controls.', fontsize=9)
        fig.text(.97,.035,'Development captures | 2 / 3',ha='right',fontsize=8,color='#555555')
        pdf.savefig(fig); fig.savefig(args.png_dir/'sdr-diagnostics-2.png',dpi=160); plt.close(fig)
        partial = json.loads((args.study/'partial-tx-disabled.json').read_text())
        fig = plt.figure(figsize=(11, 8.5))
        fig.suptitle('A retained RX-only fragment, with its failed status intact', x=.085, ha='left', y=.975, fontsize=18)
        fig.text(.085, .89, 'TX-disable registers were read before acquisition; no TX stream or payload was attempted. The after-readout is absent.\n'
                 'Only 1,680,768 of 4,000,000 requested samples were saved in the planned interval (0.840384 s).', fontsize=10)
        ax = fig.add_axes([.085,.48,.885,.32])
        rows = partial['chunk_records']
        time = np.array([r['center_seconds_relative_retained_start'] for r in rows])
        ax.plot(time, [r['tone_projection_power'] for r in rows], color='#205E9B', lw=1.1, label='100 kHz smoke projector')
        ax.plot(time, [r['line_projection_power'] for r in rows], color='#89928C', lw=1.1, label='+309.9 kHz diagnostic')
        last = rows[-1]
        rate = partial['sample_rate_hz_readback']
        fault_start = last['accepted_file_sample_offset']/rate
        ax.axvspan(fault_start, partial['retained_duration_seconds'], color='#B65A4C', alpha=.30, label='Terminal chunk: 64 drops reported')
        for name, w in partial['windows'].items():
            a,b = w['seconds_relative_retained_start']
            ax.axvspan(a,b,color='#75A5B5',alpha=.12)
        ax.set_yscale('log'); ax.set_ylim(1e-12,1e-4); ax.set_xlim(0,.85)
        ax.set_xlabel('Time relative to beginning of retained planned interval [s]')
        ax.set_ylabel('Projection power [IQ units squared]')
        ax.grid(axis='y',alpha=.18); ax.legend(loc='lower left',fontsize=8,frameon=False,ncol=2)
        ax.set_title('All 103 contributing chunks shown, including the fault-reporting chunk',fontsize=10,loc='left')
        ax=fig.add_axes([.085,.24,.885,.16]); ax.axis('off')
        table_rows=[]
        for name in ['early','middle','late']:
            w=partial['windows'][name]
            table_rows.append([name, f"{w['line']['fitted_frequency_hz']:.1f}",
                               f"{w['tone']['fixed_projection_power']:.2e}",
                               f"{w['joint_projection']['modeled_line_leakage_to_tone_projection_power']:.2e}",
                               f"{w['joint_projection']['joint_vs_single_power_change_db']:+.3f}"])
        table=ax.table(cellText=table_rows, colLabels=['30 ms window','Fitted line [Hz]','100 kHz power','Modeled line leakage','Joint change [dB]'],
                       loc='upper center',cellLoc='center',colWidths=[.17,.20,.20,.25,.18])
        table.auto_set_font_size(False); table.set_fontsize(9); table.scale(1,1.5)
        for (row,col),cell in table.get_celld().items():
            cell.set_edgecolor('#D1D8DE')
            if row==0: cell.set_facecolor('#E8EDF1'); cell.set_text_props(weight='bold')
        fig.text(.085,.12, 'Shaded 30 ms windows were fixed before reading this additional IQ. Their powers are in saved IQ units squared.\n'
                 'The narrow component is present in this failed RX-only fragment. Near-background 100 kHz coefficients are tiny, so\n'
                 'small coherent changes can produce noticeable relative dB shifts. This is not an accepted noise reference or a bound\n'
                 'on the actual ATSC pilot/reference response. The terminal fault and incomplete register evidence remain unresolved.', fontsize=9)
        fig.text(.97,.035,'Development captures | 3 / 3',ha='right',fontsize=8,color='#555555')
        pdf.savefig(fig); fig.savefig(args.png_dir/'sdr-diagnostics-3.png',dpi=160); plt.close(fig)
    print(args.pdf)


if __name__=='__main__': main()
