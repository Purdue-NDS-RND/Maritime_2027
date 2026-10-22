#!/usr/bin/env python3
"""Read-only navigation rate/latency acceptance probe; never commands the boat."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import time

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.parameter import parameter_value_to_python
from rclpy.parameter_client import AsyncParameterClient
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from geometry_msgs.msg import TwistStamped
from maritime_interfaces.msg import BuoyMap
from nav_msgs.msg import OccupancyGrid, Odometry
from std_msgs.msg import String
from vision_msgs.msg import Detection2DArray


EXPECTED = {
    '/localization/buoy_mapper': {'map_publish_hz': 5.},
    '/map_navigator': {'planning_grid_hz': 5.},
    '/controller_server': {'controller_frequency': 10.},
    '/global_costmap/global_costmap': {'update_frequency': 2., 'publish_frequency': 1.},
    '/local_costmap/local_costmap': {'update_frequency': 10., 'publish_frequency': 1.},
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=float, default=45.)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if not 10 <= args.duration <= 120:
        parser.error('duration must be 10..120 seconds')
    rclpy.init()
    node = Node('navigation_rate_probe')
    arrivals = defaultdict(list)
    statuses = []
    latest_status = {}
    parameters, pending = {}, {}
    clients = {name: AsyncParameterClient(node, name) for name in EXPECTED}
    measuring = False

    def receive(topic):
        def callback(message):
            if topic == '/navigation/status':
                latest_status.update(json.loads(message.data))
            if measuring:
                arrivals[topic].append(time.monotonic())
                if topic == '/navigation/status':
                    statuses.append(json.loads(message.data))
        return callback

    durable = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
    topics = [('/mapping/buoys', BuoyMap, durable),
              ('/mapping/occupancy_grid', OccupancyGrid, durable),
              ('/navigation/planning_grid', OccupancyGrid, durable),
              ('/global_costmap/costmap', OccupancyGrid, durable),
              ('/local_costmap/costmap', OccupancyGrid, durable),
              ('/navigation/velocity', TwistStamped, 10),
              ('/navigation/status', String, 10),
              ('/navigation/odometry', Odometry, qos_profile_sensor_data),
              ('/perception/camera_0/detections', Detection2DArray, qos_profile_sensor_data),
              ('/perception/camera_1/detections', Detection2DArray, qos_profile_sensor_data)]
    for topic, message_type, qos in topics:
        node.create_subscription(message_type, topic, receive(topic), qos)

    try:
        deadline = time.monotonic()+20
        while len(parameters) != len(EXPECTED) and time.monotonic() < deadline:
            for name, client in clients.items():
                if name not in pending and client.services_are_ready():
                    pending[name] = client.get_parameters(list(EXPECTED[name]))
                if name in pending and pending[name].done():
                    parameters[name] = dict(zip(EXPECTED[name],
                        [parameter_value_to_python(v) for v in pending[name].result().values]))
            rclpy.spin_once(node, timeout_sec=.05)
        deadline = time.monotonic()+60
        while not latest_status.get('ready') and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.05)
        measuring = True
        started = time.monotonic()
        while time.monotonic()-started < args.duration:
            rclpy.spin_once(node, timeout_sec=.05)
        finished = time.monotonic()
        rates = {topic: dict(messages=len(times),
                            hz=(len(times)-1)/(times[-1]-times[0]) if len(times) > 1 else 0.,
                            maximum_gap_s=max(float(max(np.diff(times), default=0.)), finished-times[-1]))
                 for topic, times in arrivals.items()}
        checks = {'parameters_match': parameters == EXPECTED}
        for topic, low, high in [('/mapping/buoys', 4., 6.), ('/mapping/occupancy_grid', 4., 6.),
                                  ('/global_costmap/costmap', .7, 1.3), ('/local_costmap/costmap', .7, 1.3),
                                  ('/navigation/velocity', 8., 12.), ('/navigation/status', 8., 12.)]:
            checks[topic] = low <= rates.get(topic, {}).get('hz', 0.) <= high
        builds = [s['planning_grid_builds'] for s in statuses]
        build_rate = (builds[-1]-builds[0])/(arrivals['/navigation/status'][-1]-arrivals['/navigation/status'][0]) if len(builds) > 1 else 0.
        checks['planning_build_cap'] = bool(builds) and builds[-1] > 0 and 0 <= build_rate <= 5.2
        checks['movement_observed'] = any(s['ready'] for s in statuses)
        checks['no_terminal_fault'] = all(s['stage'] != 'fault' for s in statuses)
        checks['no_scheduler_stops'] = all(s['reason'] != 'waiting_for_planning_grid' for s in statuses)
        checks['command_delivery_gap'] = (len(arrivals['/navigation/velocity']) > 1 and
            rates['/navigation/velocity']['maximum_gap_s'] < .3)
        timings = {}
        for field in ('tick_ms', 'planning_grid_build_ms', 'pose_age_s', 'map_progress_age_s'):
            values = [s[field] for s in statuses if s.get(field) is not None]
            timings[field] = dict(zip(('p50', 'p95', 'p99', 'max'),
                                     map(float, np.percentile(values, [50, 95, 99, 100])))) if values else {}
        result = dict(passed=all(checks.values()), checks=checks, wall_seconds=time.monotonic()-started,
                      parameters=parameters, rates=rates, planning_build_hz=build_rate,
                      timing=timings, reasons=dict(Counter(s['reason'] for s in statuses)),
                      hardware_note='Simulation host measurements; not a Jetson benchmark')
        Path(args.output).write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(result, indent=2), flush=True)
        return 0 if result['passed'] else 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
