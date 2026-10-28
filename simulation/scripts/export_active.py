#!/usr/bin/env python3
"""Host wrapper: verify the active simulator and export its snapshot."""
import argparse
import json
import math
import time
from pathlib import Path
import subprocess
from export_map import export
from scene_snapshot import verify


def active_scene(root):
    data=json.loads(subprocess.check_output(['docker','inspect','ardupilot-blueboat-sim']))[0]
    if not data['State']['Running']:
        raise ValueError('simulator is not running')
    env=dict(item.split('=',1) for item in data['Config']['Env'])
    run_id=env['RUN_ID']
    if Path(run_id).name != run_id:
        raise ValueError('invalid run identity')
    directory=root/'logs/runs'/run_id
    identity=verify(directory/'scene')
    # Container-side verification proves the active bind mount is the same input.
    inside=json.loads(subprocess.check_output(['docker','exec','ardupilot-blueboat-sim','python3',
        '/opt/boat_sim/scripts/scene_snapshot.py',f'/sim/runs/{run_id}/scene']))
    if inside!=identity:
        raise ValueError('host/container scene mismatch')
    recorded=json.loads((directory/'image.json').read_text())[0]
    if data['Image']!=recorded['Id']:
        raise ValueError('active image differs from archived image')
    truth=directory/'truth.jsonl'
    if not truth.is_file() or time.time()-truth.stat().st_mtime>3:
        raise ValueError('fresh active-scene physics evidence is unavailable')
    with truth.open('rb') as stream:
        stream.seek(max(0,truth.stat().st_size-65536))
        sample=json.loads(stream.read().split(b'\n')[-2])
    poses={p['name']:p['pose'] for p in sample['poses'] if '/' not in p['name']}
    manifest=json.loads((directory/'scene/manifest.json').read_text())
    expected={'blueboat', *(b['name'] for b in manifest['buoys'])}
    if set(poses)!=expected:
        raise ValueError('active scene has missing or unexpected models')
    for buoy in manifest['buoys']:
        xyz=[buoy['model_pose'][key] for key in ('x','y','z')]
        if math.dist(poses[buoy['name']][:3],xyz)>.01:
            raise ValueError('active buoy moved from immutable snapshot: '+buoy['name'])
    return directory,identity


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--alignment',type=Path)
    args=parser.parse_args()
    directory,identity=active_scene(Path(__file__).resolve().parents[1])
    alignment=json.loads(args.alignment.read_text()) if args.alignment else None
    data=export(directory/'scene',identity['scene_id'],identity['run_id'],alignment)
    args.output.write_text(json.dumps(data,indent=2)+'\n')
