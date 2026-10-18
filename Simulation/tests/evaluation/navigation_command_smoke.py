#!/usr/bin/env python3
"""Measured speed/turn-rate transport test. Explicit simulation only.

No truth input. Uses the public FCU odometry to verify forward motion at east
and south headings, both yaw-rate signs, stopping and HOLD/disarm cleanup.
"""
import math
import os
import signal
from pathlib import Path
import json
import sys
import time
sys.path.insert(0, '/navigation-scripts')

import rclpy
from geometry_msgs.msg import TwistStamped
from mavros_msgs.srv import CommandBool, MessageInterval, SetMode
from nav_msgs.msg import Odometry
from rosgraph_msgs.msg import Clock
from rclpy.qos import qos_profile_sensor_data
from navigation_bridge import Bridge


def wrap(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


def main():
    if os.environ.get('SIMULATION_NAVIGATION') != '1' or os.environ.get('ADAPTER_ENVIRONMENT') != 'simulation':
        raise SystemExit('Explicit simulation flags required')
    rclpy.init()
    node = Bridge()
    pose = [None]
    sim_time = [None]
    def receive(message):
        p, q = message.pose.pose.position, message.pose.pose.orientation
        pose[0] = (p.x, p.y, math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z)))
    node.create_subscription(Odometry, '/mavros/local_position/odom', receive, qos_profile_sensor_data)
    node.create_subscription(Clock, '/clock', lambda m: sim_time.__setitem__(0, m.clock.sec+m.clock.nanosec/1e9), qos_profile_sensor_data)
    owned = False
    results = []
    def interrupt(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGINT, interrupt)
    signal.signal(signal.SIGTERM, interrupt)
    try:
        node.until(lambda: node.state and node.state.connected and pose[0] and sim_time[0] is not None, 15)
        if node.state.armed:
            raise RuntimeError('Refusing already armed vessel')
        owned = True
        for identity in (32, 31):
            assert node.call(node.interval, MessageInterval.Request(message_id=identity, message_rate=20.)).success
        assert node.call(node.mode, SetMode.Request(custom_mode='GUIDED')).mode_sent
        node.until(lambda: node.state.mode == 'GUIDED', 10)
        deadline = time.monotonic()+60
        armed = False
        while not armed:
            armed = node.call(node.arm, CommandBool.Request(value=True)).success
            if time.monotonic() > deadline:
                raise RuntimeError('Arming timed out')
        node.until(lambda: node.state.armed, 10)
        node.started = True
        def command(speed, rate, duration):
            end = sim_time[0]+duration
            deadline = time.monotonic()+duration*10+10
            while sim_time[0] < end:
                if time.monotonic() > deadline:
                    raise RuntimeError('Simulation clock stopped or ran below 0.1x')
                message = TwistStamped()
                message.header.frame_id = 'base_link'
                message.twist.linear.x, message.twist.angular.z = float(speed), float(rate)
                node.on_velocity(message)
                rclpy.spin_once(node, timeout_sec=.03)
        for heading in [0., -math.pi/2]:
            deadline = time.monotonic()+50
            while abs(wrap(heading-pose[0][2])) > .12:
                if time.monotonic() > deadline:
                    raise AssertionError('Yaw-rate tracking did not reach heading')
                command(0., max(-.3, min(.3, wrap(heading-pose[0][2]))), .1)
            command(0., 0., 2.)
            before = pose[0]
            wall_start = time.monotonic()
            command(.3, 0., 5.)
            wall_duration = time.monotonic()-wall_start
            after = pose[0]
            forward = (after[0]-before[0])*math.cos(before[2])+(after[1]-before[1])*math.sin(before[2])
            assert forward > .4, (heading, before, after)
            command(0., 0., 3.)
            stopped = pose[0]
            drift = math.hypot(stopped[0]-after[0], stopped[1]-after[1])
            results.append(dict(heading=heading, forward_m=forward, stop_travel_m=drift,
                                simulated_seconds=5., wall_seconds=wall_duration))
            print(json.dumps(results[-1]), flush=True)
        before = pose[0][2]
        command(0., .25, 6.)
        positive = wrap(pose[0][2]-before)
        command(0., 0., 2.)
        before = pose[0][2]
        command(0., -.25, 6.)
        negative = wrap(pose[0][2]-before)
        assert positive > .1 and negative < -.1, (positive, negative)
        results.append(dict(positive_yaw_rad=positive, negative_yaw_rad=negative))
        # No call to on_velocity: the bridge must independently expire commands.
        node.until(lambda: time.monotonic()-node.received > .8, 2)
        print(json.dumps(dict(passed=True, checks=results)), flush=True)
        if Path('/results').exists():
            Path('/results/command-smoke.json').write_text(json.dumps(results, indent=2)+'\n')
    finally:
        node.started = False
        if owned:
            node.until(lambda: time.monotonic()-node.received > .8, 2)
            assert node.call(node.mode, SetMode.Request(custom_mode='HOLD')).mode_sent
            node.until(lambda: node.state.mode == 'HOLD', 10)
            assert node.call(node.arm, CommandBool.Request(value=False)).success
            node.until(lambda: not node.state.armed, 10)
            print('Verified HOLD and disarmed', flush=True)
            for identity in (32, 31):
                assert node.call(node.interval, MessageInterval.Request(message_id=identity, message_rate=0.)).success
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
