"""Draw manuscript figures from saved estimates and clustered uncertainty."""
from pathlib import Path
import argparse
import os
for key in ['OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS','NUMEXPR_NUM_THREADS']:
    os.environ[key]='1'
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator
from matplotlib.text import Annotation
import numpy as np
import pandas as pd

COLORS={'direct_percent':'#66727E','log_PeerCount':'#9256A6',
        'topic_continuity':'#C74951','network_consistency':'#287A9B'}
LABELS={'direct_percent':'DP','log_PeerCount':'PC','topic_continuity':'TC','network_consistency':'NC'}
NAMES={'direct_percent':'Direct_Percent','log_PeerCount':'PeerCount_log',
       'topic_continuity':'Topic_Continuity','network_consistency':'Net_Consistency'}
WINDOWS=['L5','L10','L20','overall_career']
LANDMARK=['early1_3_to_later4_10','early1_3_to_later6_20']
WINDOW_LABELS={'L5':'5-year window','L10':'10-year window','L20':'20-year window',
               'overall_career':'Overall career','pre_graduation':'Mentorship period',
               'early1_3_to_later4_10':'Years 4-10','early1_3_to_later6_20':'Years 6-20'}

def configure():
    plt.rcParams.update({'font.family':'Arial','font.size':15,'axes.labelsize':14,
                         'axes.titlesize':16,'xtick.labelsize':16,'ytick.labelsize':16,
                         'pdf.fonttype':42,'ps.fonttype':42,'axes.spines.top':False,
                         'axes.spines.right':False,'axes.linewidth':.7})

def limits(data):
    lo=min(0,float(data.ci_low.min()));hi=max(0,float(data.ci_high.max()))
    span=max(hi-lo,.03)
    return lo-.48*span,hi+.48*span

def forest(ax,data,reference,windows,variables,method):
    assert len(data)==len(windows)*len(variables)
    positions=[];tick_labels=[]
    for i,horizon in enumerate(windows):
        start=3*i
        ax.axhspan(start-.15,start+2.3,color='#F1F3F5' if i%2==0 else '#FAFAFB',zorder=0)
        ax.text(.025,start+.06,WINDOW_LABELS[horizon],transform=ax.get_yaxis_transform(),
                va='center',ha='left',fontsize=14,fontweight='bold',color='#49505A')
        for j,var in enumerate(variables):
            row=data[data.horizon.eq(horizon)&data.variable.eq(var)].iloc[0]
            y=start+.83+j
            color=COLORS[var]
            ax.errorbar(row.estimate,y,xerr=[[row.estimate-row.ci_low],[row.ci_high-row.estimate]],
                        fmt='o',markersize=8,markerfacecolor=color if row.p_value<.05 else 'white',
                        markeredgecolor=color,markeredgewidth=1.8,ecolor=color,elinewidth=1.8,
                        capsize=2.5,capthick=1.05,zorder=4)
            suffix=' pp' if method=='LPM' else ('%' if method=='PPML' else '')
            value=f'{row.estimate:+.1f}' if method=='PPML' else (f'{row.estimate:+.3f}' if abs(row.estimate)<.01 else f'{row.estimate:+.2f}')
            edge=row.ci_high if row.estimate>=0 else row.ci_low
            ax.annotate(value+suffix,(edge,y),xytext=(6 if row.estimate>=0 else -6,0),textcoords='offset points',
                        ha='left' if row.estimate>=0 else 'right',va='center',fontsize=16,color='#30363C',zorder=5)
            positions.append(y);tick_labels.append(LABELS[var])
    ax.axvline(0,color='#72777D',lw=.9,ls=(0,(3,3)),zorder=2)
    ax.set_ylim(3*(len(windows)-1)+2.35,-.3)
    ax.set_xlim(*limits(reference))
    ax.set_yticks(positions,tick_labels)
    ax.tick_params(axis='y',length=0,pad=6)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=4))
    ax.grid(axis='x',color='#DDE1E5',lw=.65,zorder=1)
    ax.set_axisbelow(True)
    for edge in ['bottom','left']:
        ax.spines[edge].set_color('#BEC4CA')
    ax.set_title(method,fontweight='bold',fontsize=16,pad=12)
    xlabel={'PSM0':'Matched mean difference','PSM1':'Matched mean difference',
            'PSM2':'Matched difference\n(publications/year)',
            'LPM':'Probability change\n(percentage points)',
            'PPML':'Expected publication-rate\nchange (%)'}[method]
    ax.set_xlabel(xlabel,labelpad=7)

def panel(fig,cell,data,all_data,figure,letter,title,windows,variables,methods,lag):
    inner=cell.subgridspec(1,2,wspace=.35)
    for col,method in enumerate(methods):
        ax=fig.add_subplot(inner[0,col])
        d=data[data.panel.eq(letter)&data.method.eq(method)]
        reference=all_data[all_data.figure.eq(figure)&all_data.panel.eq(letter)&all_data.method.eq(method)]
        forest(ax,d,reference,windows,variables,method)
    box=cell.get_position(fig)
    fig.text(box.x0-.042,box.y1+.038,letter,ha='left',va='bottom',fontsize=23,fontweight='bold')
    fig.text((box.x0+box.x1)/2,box.y1+.038,title,ha='center',va='bottom',fontsize=18,fontweight='bold')

def legend(fig,variables,lag):
    handles=[Line2D([0],[0],color=COLORS[v],marker='o',lw=2.3,markersize=9,label=NAMES[v]) for v in variables]
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.51,.997),ncol=2,
               frameon=False,fontsize=19,handlelength=2.1,columnspacing=2.2)

def save(fig,destination):
    destination.parent.mkdir(exist_ok=True,parents=True)
    fig.canvas.draw()
    renderer=fig.canvas.get_renderer()
    for ax in fig.axes:
        for label in ax.texts:
            if not isinstance(label,Annotation):
                continue
            bounds=label.get_window_extent(renderer)
            if bounds.x0<ax.bbox.x0+3:
                label.xy=(ax.get_xlim()[0],label.xy[1])
                label.set_position((4,-12))
                label.set_ha('left')
            elif bounds.x1>ax.bbox.x1-3:
                label.xy=(ax.get_xlim()[1],label.xy[1])
                label.set_position((-4,-12))
                label.set_ha('right')
    fig.savefig(destination.with_suffix('.png'),dpi=300,facecolor='white',bbox_inches='tight',pad_inches=.18)
    fig.savefig(destination.with_suffix('.pdf'),facecolor='white',bbox_inches='tight',pad_inches=.18)
    plt.close(fig)
    print(destination.name)

def make_figure3(all_data,lag,destination):
    d=all_data[all_data.figure.eq(3)&all_data.lag.eq(lag)]
    assert len(d)==36
    fig=plt.figure(figsize=(15,17))
    outer=fig.add_gridspec(3,1,left=.085,right=.97,bottom=.105,top=.895,
                          height_ratios=[.52,1.6,1.6],hspace=.59)
    variables=['direct_percent','log_PeerCount']
    panel(fig,outer[0,0],d,all_data,3,'A','Mentorship-period publishing: PSM0 + LPM',['pre_graduation'],variables,['PSM0','LPM'],lag)
    panel(fig,outer[1,0],d,all_data,3,'B','Post-graduation publishing: PSM1 + LPM',WINDOWS,variables,['PSM1','LPM'],lag)
    panel(fig,outer[2,0],d,all_data,3,'C','Post-graduation publication rate: PSM2 + PPML',WINDOWS,variables,['PSM2','PPML'],lag)
    legend(fig,variables,lag)
    save(fig,destination)

def make_figure4(all_data,lag,destination):
    d=all_data[all_data.figure.eq(4)&all_data.lag.eq(lag)]
    assert len(d)==48
    fig=plt.figure(figsize=(18,15))
    outer=fig.add_gridspec(2,2,left=.07,right=.975,bottom=.13,top=.89,hspace=.53,wspace=.26)
    variables=['topic_continuity','network_consistency']
    panel(fig,outer[0,0],d,all_data,4,'A','Conventional: PSM1 + LPM',WINDOWS,variables,['PSM1','LPM'],lag)
    panel(fig,outer[0,1],d,all_data,4,'B','Landmark: PSM1 + LPM',LANDMARK,variables,['PSM1','LPM'],lag)
    panel(fig,outer[1,0],d,all_data,4,'C','Conventional: PSM2 + PPML',WINDOWS,variables,['PSM2','PPML'],lag)
    panel(fig,outer[1,1],d,all_data,4,'D','Landmark: PSM2 + PPML',LANDMARK,variables,['PSM2','PPML'],lag)
    legend(fig,variables,lag)
    save(fig,destination)

def make_figures(root):
    from figure_inputs import prepare_estimates
    from make_group_figure import make_group_figure, configure as configure_group
    root=Path(root)
    configure()
    data=prepare_estimates(root)
    for lag in [3,2]:
        folder=root/'Figure'/f't{lag}'
        make_figure3(data,lag,folder/'figure3_resource_results')
        make_figure4(data,lag,folder/'figure4_continuity_results')
    configure_group()
    make_group_figure(root/'Results',root/'Figure/t3/figure2_group_profiles')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    make_figures(args.root)
