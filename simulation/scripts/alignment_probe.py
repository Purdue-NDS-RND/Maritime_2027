#!/usr/bin/env python3
"""Disarmed simulation-only frame probe. Run INSIDE the simulator container.

Moves the Gazebo model, requests true SITL SIMSTATE (not GLOBAL_POSITION_INT),
then restores the original pose. Never run alongside a boat controller.
"""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import time
from pymavlink import mavutil


def pose(x, y, yaw):
    request = f'name: "blueboat", position: {{x: {x}, y: {y}, z: 0}}, orientation: {{z: {math.sin(yaw/2)}, w: {math.cos(yaw/2)}}}'
    result = subprocess.run(['gz', 'service', '-s', '/world/blueboat_rgbd/set_pose',
                             '--reqtype', 'gz.msgs.Pose', '--reptype', 'gz.msgs.Boolean',
                             '--timeout', '3000', '--req', request], capture_output=True, text=True, check=True)
    if 'true' not in result.stdout:
        raise RuntimeError('Gazebo pose change unconfirmed: ' + result.stdout + result.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    link = mavutil.mavlink_connection('udpin:127.0.0.1:14551', source_system=246)
    heartbeat = link.wait_heartbeat(timeout=15)
    if heartbeat is None or heartbeat.base_mode & 128:
        raise RuntimeError('fresh disarmed heartbeat required')
    def latest_truth():
        runs = sorted(Path('/sim/runs').glob('*/truth.jsonl'), key=lambda p: p.stat().st_mtime)
        with runs[-1].open('rb') as stream:
            stream.seek(max(0, runs[-1].stat().st_size - 32768))
            lines = stream.read().split(b'\n')
            return json.loads(lines[-2])
    original = next(p["pose"] for p in latest_truth()["poses"] if p["name"] == "blueboat")
    samples = []
    try:
        probes = [(0,0,0), (10,0,0), (0,10,0), (8,6,math.pi/2)]
        if os.environ.get('SCENARIO') == 'competition':
            # Sample the west-facing spawn and keep later poses clear of docks.
            probes = [(original[0],original[1],original[5]), (0,10,0), (-10,10,0), (-8,6,math.pi/2)]
        for x, y, yaw in probes:
            pose(x, y, yaw)
            time.sleep(2)
            while link.recv_match() is not None:
                pass
            link.mav.command_long_send(link.target_system, link.target_component,
                mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0, 164, 100000, 0, 0, 0, 0, 0)
            sample = link.recv_match(type='SIMSTATE', blocking=True, timeout=10)
            if sample is None:
                raise RuntimeError('SITL SIMSTATE unavailable; alignment inconclusive')
            samples.append({'requested_world_pose': [x,y,yaw], 'sitl': sample.to_dict(), 'physics': latest_truth(), 'wall_time': time.time()})
    finally:
        pose(original[0], original[1], original[5])
        args.output.write_text(json.dumps({'samples': samples, 'reference': 'SIMSTATE truth, not estimated GPS'}, indent=2) + '\n')
        link.close()


if __name__ == '__main__':
    main()
