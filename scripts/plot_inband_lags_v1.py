#!/usr/bin/env python3
"""Scientific figures from the declared lag study; no fitted physical model."""
import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import LogNorm
import numpy as np


def main(study):
    plan=json.loads((study/'plan.json').read_text())
    records=[dict(np.load(study/f'data/ch{freq:04d}.npz')) for freq in plan['frequency_ids']]
    stack=lambda key:np.stack([r[key] for r in records])
    voltage=stack('voltage_all_normalized_centered')
    visibility=stack('visibility_all_normalized_centered')
    uncentered=stack('visibility_all_normalized_raw')
    lag=np.asarray(plan['lags_samples']); ms=lag*plan['delta_time_seconds']*1000
    plt.rcParams.update({'font.family':'serif','font.serif':['DejaVu Serif'],
                         'font.size':9,'axes.titlesize':10,'axes.labelsize':9,
                         'legend.fontsize':8,'pdf.fonttype':42,'savefig.dpi':160})
    figures=study/'figures'; figures.mkdir(exist_ok=True)
    blue='#206092'; orange='#bc5a18'; gray='#565656'
    def lag_axis(ax):
        ax.set_xscale('log'); ax.set_xlabel('Positive lag (ms)')
        ax.grid(alpha=.22,which='major'); ax.set_xlim(ms[1],ms[-1])
    def spread(ax,y,color,label,log=True,maximum=False):
        q=np.quantile(y,[.1,.5,.9],axis=0)
        ax.fill_between(ms[1:],q[0,1:],q[2,1:],color=color,alpha=.16,label='10th-90th percentile')
        ax.plot(ms[1:],q[1,1:],color=color,label=label,lw=1.8)
        if maximum: ax.plot(ms[1:],np.max(y,axis=0)[1:],color=gray,lw=.85,label='Maximum')
        if log: ax.set_yscale('log')
        lag_axis(ax)
    with PdfPages(figures/'inband-lag-diagnostics.pdf',metadata={'Title':'Short-timescale native digital lag diagnostics','Author':'RFIsher','CreationDate':None,'ModDate':None}) as pdf:
        fig,axs=plt.subplots(2,2,figsize=(12,8.5))
        fig.subplots_adjust(left=.075,right=.955,top=.85,bottom=.13,hspace=.48,wspace=.32)
        fig.suptitle('Native voltage autocorrelation across one 0.2943 s event',fontsize=16,y=.96)
        fig.text(.5,.916,'15 coarse frequencies | 32 selected inputs | all 114,964 contiguous samples | event 1153713684',ha='center',fontsize=10)
        y=np.abs(voltage).transpose(0,2,1).reshape(-1,len(lag))
        spread(axs[0,0],y,blue,'Median (480 series)',maximum=True)
        axs[0,0].set_title('Centered normalized amplitude; zero lag = 1')
        axs[0,0].set_ylabel('Voltage autocorrelation magnitude')
        axs[0,0].legend(loc='lower left',frameon=False)
        im=axs[0,1].imshow(abs(voltage[:,-1,:]),aspect='auto',origin='lower',
                            cmap='viridis',norm=LogNorm(vmin=1e-4,vmax=.15))
        axs[0,1].set_title('Amplitude at 83.886 ms: every retained series')
        axs[0,1].set_yticks(range(0,15,2),labels=plan['frequency_ids'][::2])
        axs[0,1].set_xticks(range(0,32,4),labels=[r['array_index'] for r in plan['inputs'][::4]])
        axs[0,1].set_ylabel('Native frequency ID'); axs[0,1].set_xlabel('Original dataset input column (selected order)')
        fig.colorbar(im,ax=axs[0,1],fraction=.046,pad=.025,label='Centered normalized magnitude')
        for values,color,label in [(voltage.real,blue,'Real'),(voltage.imag,orange,'Imaginary')]:
            q=np.quantile(values,[.1,.5,.9],axis=(0,2))
            axs[1,0].fill_between(ms[1:],q[0,1:],q[2,1:],color=color,alpha=.12)
            axs[1,0].plot(ms[1:],q[1,1:],color=color,label=label+' median')
        lag_axis(axs[1,0]); axs[1,0].axhline(0,color=gray,lw=.6)
        axs[1,0].set_title('Complex orientation: late voltage times conjugate(early)')
        axs[1,0].set_ylabel('Centered normalized component')
        axs[1,0].legend(frameon=False)
        support=plan['samples']-lag
        axs[1,1].plot(ms[1:],support[1:]/plan['samples'],color=blue,marker='.',ms=4)
        lag_axis(axs[1,1]); axs[1,1].set_ylim(.69,1.015)
        axs[1,1].set_ylabel('Fraction of event supporting each lag')
        axs[1,1].set_title('All early/late pairs, including storage-block crossings')
        axs[1,1].text(.05,.12,f'At largest lag: {support[-1]:,} pairs per series\nZero lag: {support[0]:,} samples per series\n0x00 exclusion changes no support in this event',transform=axs[1,1].transAxes,fontsize=9)
        fig.text(.075,.056,'Bands describe spread across retained series, not uncertainty. Positive magnitude has sampling bias.\nNo physical calibration, source identification, independent validation, or minute-to-hour coherence is established.',fontsize=9)
        fig.text(.95,.035,'1 / 2',ha='right',fontsize=8)
        pdf.savefig(fig); plt.close(fig)

        fig,axs=plt.subplots(3,2,figsize=(12,10))
        fig.subplots_adjust(left=.075,right=.96,top=.835,bottom=.17,hspace=.62,wspace=.32)
        fig.suptitle('Temporal fluctuations of three selected digital visibility pairs',fontsize=16,y=.965)
        fig.text(.5,.92,'Instantaneous z(t) = x_i(t) conjugate(x_j(t)); these are not voltage autocorrelations',ha='center',fontsize=10)
        frames=records[0]['visibility_all_frame_blocks']; complete=records[0]['visibility_all_frame_complete']
        centers=frames.mean(axis=1)*plan['delta_time_seconds']*1000
        sums=stack('visibility_all_frame_sum'); counts=stack('visibility_all_frame_count')
        means=sums/counts
        for pair,(i,j) in enumerate(plan['visibility_pair_slots']):
            ax=axs[pair,0]
            spread(ax,abs(visibility[:,:,pair]),blue,'Centered median',maximum=True)
            ax.plot(ms[1:],np.median(abs(uncentered[:,:,pair]),axis=0)[1:],color=orange,ls='--',lw=1.3,label='Uncentered median')
            left,right=plan['inputs'][i]['array_index'],plan['inputs'][j]['array_index']
            ax.set_title(f'Columns {left}/{right}: normalized visibility lag')
            ax.set_ylabel('Visibility lag magnitude')
            if pair==0: lag_handles,lag_labels=ax.get_legend_handles_labels()
            ax=axs[pair,1]
            for values,color,label in [(means.real,blue,'Real'),(means.imag,orange,'Imaginary')]:
                q=np.quantile(values[:,:,pair],[.1,.5,.9],axis=0)
                ax.plot(centers[complete],q[1,complete],color=color,marker='o',ms=3,label=label+' median')
                ax.fill_between(centers[complete],q[0,complete],q[2,complete],color=color,alpha=.12)
                ax.plot(centers[~complete],q[1,~complete],marker='D',ls='none',ms=5,color=color)
                ax.vlines(centers[~complete],q[0,~complete],q[2,~complete],color=color,lw=1)
            ax.set_title(f'Columns {left}/{right}: mean visibility by upgrade-size frame')
            ax.set_ylabel(r'Mean visibility (decoded-code$^2$)')
            ax.set_xlabel('Elapsed time at interval center (ms)'); ax.grid(alpha=.22)
            if pair==0: frame_handles,frame_labels=ax.get_legend_handles_labels()
        fig.legend(lag_handles+frame_handles,lag_labels+frame_labels,loc='upper center',bbox_to_anchor=(.5,.895),ncol=6,frameon=False,fontsize=8)
        fig.text(.075,.055,'Lag centering removes the mean of z on each overlapping window; it does not center the input voltages.\nRight: seven complete 16,384-sample frames (41.943 ms); diamonds mark the separate 276-sample tail (0.707 ms).\nFrames start at this retained interval, not verified operational boundaries. Bands span frequencies; they are not confidence intervals.',fontsize=9)
        fig.text(.95,.035,'2 / 2',ha='right',fontsize=8)
        pdf.savefig(fig); plt.close(fig)
    with (study/'descriptive_lag_summary.csv').open('w',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['lag_samples','lag_ms','support_per_series','voltage_median_abs','voltage_p10_abs','voltage_p90_abs','voltage_max_abs','visibility_median_abs','visibility_p90_abs','visibility_max_abs'])
        for k in range(len(lag)):
            v=abs(voltage[:,k,:]); z=abs(visibility[:,k,:])
            writer.writerow([lag[k],ms[k],support[k],np.median(v),np.quantile(v,.1),np.quantile(v,.9),v.max(),np.median(z),np.quantile(z,.9),z.max()])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--study',required=True,type=Path)
    main(parser.parse_args().study.resolve())
