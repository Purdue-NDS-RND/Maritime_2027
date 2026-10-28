#!/usr/bin/env python3
"""Save standalone course/speed/clearance figures from independent evidence."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def plot(result, object_map, commanded_speed, output):
    samples=result['trajectory']
    if not samples:raise ValueError('no independent trajectory samples')
    start=samples[0]['time_s']; t=[p['time_s']-start for p in samples]
    fig,axes=plt.subplots(1,3,figsize=(15,4),layout='constrained')
    axes[0].plot([p['x']for p in samples],[p['y']for p in samples],color='#2468a8',label='actual base_link')
    for buoy in object_map['buoys']:
        x,y,z=buoy['world_centre'];colour={'red':'#c9343e','green':'#23976c','white':'#aaa','blue':'#3479bf'}[buoy['category']]
        axes[0].add_patch(plt.Circle((x,y),buoy['radius_m'],color=colour))
    axes[0].set(xlabel='World X / east (m)',ylabel='World Y / north (m)',title='Independent trajectory')
    axes[0].axis('equal');axes[0].legend(fontsize=8)
    axes[1].plot(t,[p['speed_m_s']for p in samples],label='actual physics velocity')
    axes[1].axhline(commanded_speed,color='#a64d21',linestyle='--',label=f'command {commanded_speed:g} m/s')
    axes[1].set(xlabel='Elapsed sample time (s)',ylabel='Speed (m/s)',title='Actual speed');axes[1].legend(fontsize=8)
    if all('clearance_m'in p for p in samples):axes[2].plot(t,[p['clearance_m']for p in samples],label='oriented whole-boat bound')
    axes[2].axhline(.25,color='#b33',linestyle='--',label='required 0.25 m')
    axes[2].set(xlabel='Elapsed sample time (s)',ylabel='Footprint clearance (m)',title='Buoy clearance');axes[2].legend(fontsize=8)
    for axis in axes:axis.grid(alpha=.2)
    fig.suptitle(f"{result['outcome'].upper()} · {result['elapsed_s']:.2f} s · minimum clearance {result['minimum_clearance_m']:.3f} m")
    fig.savefig(output,dpi=150);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evaluation',type=Path);parser.add_argument('object_map',type=Path)
    parser.add_argument('--commanded-speed',type=float,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    plot(json.loads(args.evaluation.read_text()),json.loads(args.object_map.read_text()),args.commanded_speed,args.output)
