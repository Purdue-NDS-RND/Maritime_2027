#!/usr/bin/env python3
"""Assess geographic conversion independently of estimated GPS."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.geometry import to_local
from scene_snapshot import verify


def assess(snapshot, raw):
    identity = verify(snapshot)
    data = json.loads(Path(raw).read_text())
    samples = data['samples']
    positions, headings, errors, heading_errors = [], [], [], []
    for sample in samples:
        truth = next(p['pose'] for p in sample['physics']['poses'] if p['name'] == 'blueboat/imu_link')
        state = sample['sitl']
        local = to_local({'latitude': state['lat']/1e7, 'longitude': state['lng']/1e7}, identity['geographic_reference'])
        errors.append(math.dist(local,truth[:2]))
        heading_errors.append(abs(math.atan2(math.sin(state['yaw']-(math.pi/2-truth[5])), math.cos(state['yaw']-(math.pi/2-truth[5])))))
        positions.append(truth[:2]); headings.append(truth[5])
    areas = [abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))
             for a in positions for b in positions for c in positions]
    two_headings = any(abs(math.sin(a-b)) > 0.5 for a in headings for b in headings)
    enough = len(samples)>=3 and max(areas,default=0)>10 and two_headings
    passed = enough and max(errors)<0.10 and max(heading_errors)<0.01
    return {'schema_version':1, 'scene_id': identity['scene_id'], 'run_id': identity['run_id'],
            'outcome':'passed' if passed else 'failed', 'tolerance_m':0.10,
            'maximum_position_error_m':max(errors), 'sample_position_errors_m':errors,
            'maximum_heading_error_rad':max(heading_errors), 'non_collinear_two_headings':enough,
            'source_sha256':hashlib.sha256(Path(raw).read_bytes()).hexdigest(),
            'method':'disarmed SIMSTATE truth versus adjacent physics IMU poses; not estimated GPS'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot',type=Path)
    parser.add_argument('raw',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.write_text(json.dumps(assess(args.snapshot,args.raw),indent=2)+'\n')
