#!/usr/bin/env python3
"""Measure advancing simulation time against a fixed wall-time observation."""
import argparse
from collections import Counter
import json
import time


def main():
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from rosgraph_msgs.msg import Clock

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=float, default=20.)
    parser.add_argument('--min-rtf', type=float, default=0.)
    parser.add_argument('--navigation', action='store_true', help='Also report navigation stages and stop reasons')
    args = parser.parse_args()
    if not 1 <= args.duration <= 120 or not 0 <= args.min_rtf <= 2:
        parser.error('duration must be 1..120 seconds and min-rtf must be 0..2')
    rclpy.init()
    node = Node('simulation_performance_probe')
    latest = None
    last_arrival = None
    previous = None
    rewound = False
    received = 0
    max_gap = 0.
    stages, reasons = Counter(), Counter()
    ready_samples = 0

    def receive(message):
        nonlocal latest, last_arrival, previous, rewound, received, max_gap
        now = time.monotonic()
        stamp = message.clock.sec+message.clock.nanosec*1e-9
        if previous is not None and stamp < previous:
            rewound = True
        if last_arrival is not None:
            max_gap = max(max_gap, now-last_arrival)
        latest, previous, last_arrival = stamp, stamp, now
        received += 1

    node.create_subscription(Clock, '/clock', receive, qos_profile_sensor_data)
    if args.navigation:
        from std_msgs.msg import String

        def navigation(message):
            nonlocal ready_samples
            status = json.loads(message.data)
            stages[status['stage']] += 1
            reasons[status['reason']] += 1
            ready_samples += bool(status['ready'])

        node.create_subscription(String, '/navigation/status', navigation, 10)
    try:
        deadline = time.monotonic()+10
        while latest is None and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.1)
        if latest is None:
            raise RuntimeError('No /clock received; start the Simulation Adapter first')
        # Measure the entire fixed window, including pauses or delivery stalls.
        start, initial = time.monotonic(), latest
        while time.monotonic()-start < args.duration:
            rclpy.spin_once(node, timeout_sec=.05)
        elapsed = time.monotonic()-start
        factor = (latest-initial)/elapsed
        silence = time.monotonic()-last_arrival
        passed = (not rewound and silence < 2 and factor >= args.min_rtf
                  and (not args.navigation or ready_samples > 0))
        print(json.dumps(dict(passed=passed, wall_seconds=elapsed,
            simulation_seconds=latest-initial, real_time_factor=factor,
            clock_messages=received, maximum_clock_gap_s=max(max_gap, silence),
            clock_rewound=rewound, minimum_required_rtf=args.min_rtf,
            navigation_stages=dict(stages), navigation_reasons=dict(reasons),
            navigation_ready_samples=ready_samples), indent=2), flush=True)
        return 0 if passed else 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
