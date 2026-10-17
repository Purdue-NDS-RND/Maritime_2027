#!/usr/bin/env python3
"""Independent live trajectory judge; truth is never sent to navigation."""
import json
import math
from pathlib import Path
import time

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from std_msgs.msg import String
from rclpy.qos import qos_profile_sensor_data


class Judge(Node):
    def __init__(self):
        super().__init__('navigation_trajectory_judge')
        self.status = None
        self.samples = []
        self.buoys = {}
        manifest = json.loads(Path('/scenario/active.manifest.json').read_text())
        self.names = {b['name']: b['category'] for b in manifest['buoys']}
        self.create_subscription(Odometry, '/blueboat/ground_truth/odometry', self.on_pose, qos_profile_sensor_data)
        self.create_subscription(String, '/navigation/status', lambda m: setattr(self, 'status', json.loads(m.data)), 10)
        for b in manifest['buoys']:
            self.create_subscription(Odometry, b['truth_topic'],
                                     lambda m, name=b['name']: self.buoys.update({name: m.pose.pose.position}), qos_profile_sensor_data)

    def on_pose(self, m):
        p, q = m.pose.pose.position, m.pose.pose.orientation
        yaw = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
        self.samples.append((p.x, p.y, yaw))

    def result(self):
        checks = {}
        for name, buoy in self.buoys.items():
            # Conservative rectangle enclosing both hulls plus buoy/panel disc.
            # Closest rectangle-to-centre distance must exceed asset radius.
            distances = []
            crossings = []
            for x, y, yaw in self.samples:
                dx, dy = buoy.x-x, buoy.y-y
                longitudinal = dx*math.cos(yaw)+dy*math.sin(yaw)
                lateral = -dx*math.sin(yaw)+dy*math.cos(yaw)
                distances.append(math.hypot(max(abs(longitudinal)-1.1, 0), max(abs(lateral)-.6, 0))-.6)
            for previous, current in zip(self.samples, self.samples[1:]):
                if previous[0] <= buoy.x < current[0]:
                    fraction = (buoy.x-previous[0])/(current[0]-previous[0])
                    crossing_y = previous[1]+fraction*(current[1]-previous[1])
                    crossings.append(crossing_y-buoy.y if self.names[name] == 'red' else buoy.y-crossing_y)
            checks[name] = dict(position=[buoy.x, buoy.y], min_clearance_m=min(distances, default=-1), side_clearance_m=crossings,
                               passed=bool(crossings) and min(crossings) > .6 and min(distances) > 0)
        expected = ['gate_a', 'turn_1', 'turn_2', 'turn_3', 'turn_4', 'gate_b'] if len(self.names) > 2 else ['gate_a']
        status = self.status or {}
        exit_clearance = -1.
        if self.samples and self.buoys:
            x, _, yaw = self.samples[-1]
            rear_extent = 1.1*abs(math.cos(yaw))+.6*abs(math.sin(yaw))
            exit_clearance = x-rear_extent-max(b.x for b in self.buoys.values())
        return dict(passed=(status.get('stage') == 'complete' and status.get('events') == expected
                            and len(checks) == len(self.names) and all(c['passed'] for c in checks.values())
                            and all(v > 0 for v in status.get('observations', {}).values())
                            and exit_clearance > 0),
                    full_exit_clearance_m=exit_clearance, checks=checks, status=status, samples=self.samples)


def main():
    rclpy.init()
    node = Judge()
    deadline = time.monotonic()+330
    try:
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.1)
            if node.status and node.status['stage'] in ('complete', 'fault'):
                break
        result = node.result()
        Path('/results/result.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps({k: v for k, v in result.items() if k != 'samples'}), flush=True)
        if not result['passed']:
            raise SystemExit(1)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
