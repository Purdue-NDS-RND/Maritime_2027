#!/usr/bin/env python3
"""Summarize actual tracking, speed, stopping and GPS error separately."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from shared.geometry import to_local,segment_distance


def summarize(path,reference):
    data=json.loads(Path(path).read_text())
    start=next(p['pose'][:2]for p in data['start_physics']['poses']if p['name']=='blueboat/base_link')
    route=[start]+[to_local(p,reference)for p in data['mission']['waypoints']]
    tracking,gps,speeds,truth_speeds=[],[],[],[]
    previous=None;stop_start=None;max_stop_distance=0;finish_error=0
    for sample in data['samples']:
        pose=next(p['pose']for p in sample['physics']['poses']if p['name']=='blueboat/base_link')
        t=sample['physics']['time_s']
        # Finite segments cover turns. Extend only the final leg beyond its end:
        # terminal along-track overshoot belongs to the explicitly checked finish
        # area. Keep the lateral error in the common route tracking allowance.
        distances=[segment_distance(pose,a,b) for a,b in zip(route,route[1:])]
        a,b=route[-2:];u=(b[0]-a[0],b[1]-a[1]);length=math.hypot(*u)
        projection=((pose[0]-b[0])*u[0]+(pose[1]-b[1])*u[1])/length if length else 0
        if projection>0:
            distances[-1]=abs((pose[0]-a[0])*u[1]-(pose[1]-a[1])*u[0])/length
        tracking.append(min(distances))
        gps.append(math.dist(to_local(sample['status']['position'],reference),pose[:2]))
        speeds.append(sample['status']['speed_m_s'])
        if previous and t>previous[0]:truth_speeds.append(math.dist(pose[:2],previous[1])/(t-previous[0]))
        previous=(t,pose[:2])
        if sample['status']['state']=='stopping':
            if stop_start is None:stop_start=pose[:2]
            max_stop_distance=max(max_stop_distance,math.dist(pose[:2],stop_start))
        finish_error=math.dist(pose[:2],route[-1])
    legs=[math.dist(a,b)for a,b in zip(route,route[1:])]
    angles=[]
    for a,b,c in zip(route,route[1:],route[2:]):
        u,v=(b[0]-a[0],b[1]-a[1]),(c[0]-b[0],c[1]-b[1])
        angles.append(math.degrees(math.acos(max(-1,min(1,(u[0]*v[0]+u[1]*v[1])/(math.hypot(*u)*math.hypot(*v)))))))
    return {'source_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            'mission_id':data['mission']['mission_id'],'commanded_speed_m_s':data['mission']['speed_m_s'],
            'maximum_cross_track_m':max(tracking),'maximum_gps_truth_error_m':max(gps),
            'empirical_position_tracking_bound_m':max(tracking)+max(gps),
            'maximum_stop_travel_m':max_stop_distance,'finish_truth_error_m':finish_error,
            'elapsed_sim_s':data['end_physics']['time_s']-data['start_physics']['time_s'],
            'actual_mean_speed_m_s':sum(truth_speeds)/len(truth_speeds)if truth_speeds else None,
            'actual_peak_speed_m_s':max(truth_speeds,default=0),'minimum_leg_m':min(legs),
            'maximum_leg_m':max(legs),'maximum_turn_deg':max(angles,default=0),
            'boat_reported_outcome':data['boat_outcome']['state'],'applied_parameters':data['applied'],
            'parameter_restoration_verified':all(abs(v-data['original'][k])<1e-4 for k,v in data['restored'].items()) and not data.get('restoration_error')}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.write_text(json.dumps(summarize(args.recording,{'latitude':51.566151,'longitude':-4.034345}),indent=2)+'\n')
