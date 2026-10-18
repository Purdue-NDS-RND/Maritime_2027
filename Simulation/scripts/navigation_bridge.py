#!/usr/bin/env python3
"""Explicit simulation-only command session with an independent deadman timer."""
import json
import math
import os
import signal
import time

import rclpy
from geometry_msgs.msg import TwistStamped
from mavros_msgs.msg import PositionTarget, State
from mavros_msgs.srv import CommandBool, MessageInterval, SetMode
from rclpy.node import Node
from std_msgs.msg import String

TELEMETRY_RATES = ((32, 20.), (31, 20.), (2, 5.))


class Bridge(Node):
    def __init__(self):
        super().__init__('simulation_navigation_bridge')
        self.state = None
        self.state_time = 0.
        self.latest = None
        self.received = 0.
        self.ready = False
        self.terminal = False
        self.stage = None
        self.started = False
        self.create_subscription(State, '/mavros/state', self.on_state, 10)
        self.create_subscription(TwistStamped, '/navigation/velocity', self.on_velocity, 10)
        self.create_subscription(String, '/navigation/status', self.on_status, 10)
        self.publisher = self.create_publisher(PositionTarget, '/mavros/setpoint_raw/local', 10)
        self.arm = self.create_client(CommandBool, '/mavros/cmd/arming')
        self.mode = self.create_client(SetMode, '/mavros/set_mode')
        self.interval = self.create_client(MessageInterval, '/mavros/set_message_interval')
        self.create_timer(.05, self.tick)

    def on_state(self, msg):
        self.state, self.state_time = msg, time.monotonic()

    def on_status(self, msg):
        status = json.loads(msg.data)
        self.ready = bool(status.get('ready', False))
        self.terminal = status['stage'] in ('complete', 'fault')
        if status['stage'] != self.stage:
            print(msg.data, flush=True)
        self.stage = status['stage']

    def on_velocity(self, msg):
        values = (msg.twist.linear.x, msg.twist.linear.y, msg.twist.angular.z,
                  msg.twist.linear.z, msg.twist.angular.x, msg.twist.angular.y)
        if (msg.header.frame_id == 'base_link' and all(map(math.isfinite, values))
                and 0 <= values[0] <= .5 and abs(values[2]) <= .5
                and all(abs(v) < 1e-6 for v in (values[1], *values[3:]))):
            self.latest, self.received = msg, time.monotonic()
        else:
            self.latest, self.received = None, 0.

    def tick(self):
        msg = PositionTarget()
        msg.coordinate_frame = PositionTarget.FRAME_BODY_NED
        # MAVROS converts ROS FLU velocity/yaw rate to aircraft FRD for BODY_NED.
        # Rover determines forward/reverse from packet.vx when yaw rate is active;
        # body-forward vx remains positive at every compass heading. Preserve
        # Nav2's angular command instead of discarding it.
        msg.type_mask = (PositionTarget.IGNORE_PX | PositionTarget.IGNORE_PY | PositionTarget.IGNORE_PZ
                         | PositionTarget.IGNORE_AFX | PositionTarget.IGNORE_AFY | PositionTarget.IGNORE_AFZ
                         | PositionTarget.IGNORE_YAW)
        if (self.started and self.state and self.state.connected and self.state.armed
                and self.state.mode == 'GUIDED' and time.monotonic()-self.state_time < 2
                and time.monotonic()-self.received < .5 and not self.terminal):
            msg.velocity = self.latest.twist.linear
            msg.yaw_rate = self.latest.twist.angular.z
        msg.header.stamp = self.get_clock().now().to_msg()
        self.publisher.publish(msg)

    def until(self, predicate, timeout):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=.05)
            if predicate():
                return
        raise RuntimeError('Navigation session timed out')

    def call(self, client, request):
        if not client.wait_for_service(timeout_sec=5):
            raise RuntimeError('Vehicle service unavailable')
        future = client.call_async(request)
        self.until(future.done, 10)
        return future.result()


def main():
    if os.environ.get('SIMULATION_NAVIGATION') != '1' or os.environ.get('ADAPTER_ENVIRONMENT') != 'simulation':
        raise SystemExit('Requires SIMULATION_NAVIGATION=1 and ADAPTER_ENVIRONMENT=simulation')
    mission_timeout = float(os.environ.get('NAVIGATION_MISSION_TIMEOUT_S', '600'))
    if not math.isfinite(mission_timeout) or not 60 <= mission_timeout <= 3600:
        raise SystemExit('Mission timeout must be 60..3600 seconds')
    rclpy.init()
    node = Bridge()
    owned = False
    rates_requested = False
    def interrupt(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    try:
        node.until(lambda: node.state and node.state.connected, 20)
        if node.state.armed:
            raise RuntimeError('Refusing an already armed vessel')
        rates_requested = True
        # Position/attitude keep the live control watchdog supplied. Frequent
        # SYSTEM_TIME references also bound the mapper's clock-bracket wait when
        # rendering makes simulation run slower than wall time.
        for identity, rate in TELEMETRY_RATES:
            if not node.call(node.interval, MessageInterval.Request(message_id=identity, message_rate=rate)).success:
                raise RuntimeError(f'Navigation telemetry request rejected: {identity} at {rate} Hz')
        print('Requested position/attitude at 20 Hz and time references at 5 Hz', flush=True)
        node.until(lambda: node.ready, 90)
        if not node.state or not node.state.connected or node.state.armed:
            raise RuntimeError('Vehicle state changed before navigation ownership')
        # Own any subsequent mode/arm transition, including a request whose
        # response is interrupted. Initial state was explicitly unarmed.
        owned = True
        if not node.call(node.mode, SetMode.Request(custom_mode='GUIDED')).mode_sent:
            raise RuntimeError('GUIDED rejected')
        node.until(lambda: node.state.mode == 'GUIDED', 10)
        deadline = time.monotonic()+60
        while True:
            if node.call(node.arm, CommandBool.Request(value=True)).success:
                owned = True
                break
            if time.monotonic() > deadline:
                raise RuntimeError('Arming rejected')
            end = time.monotonic()+2
            node.until(lambda: time.monotonic() >= end, 3)
        node.until(lambda: node.state.armed, 10)
        print('Navigation armed in GUIDED', flush=True)
        node.started = True
        node.until(lambda: node.terminal or node.state.mode != 'GUIDED' or not node.state.armed, mission_timeout)
        if node.stage != 'complete':
            raise RuntimeError('Mission did not complete: '+str(node.stage))
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        node.started = False
        cleanup_errors = []
        if owned:
            # Attempt disarming even when HOLD acknowledgement is lost.
            try:
                end = time.monotonic()+2
                node.until(lambda: time.monotonic() >= end, 3)
                if not node.call(node.mode, SetMode.Request(custom_mode='HOLD')).mode_sent:
                    raise RuntimeError('Cleanup HOLD rejected')
                node.until(lambda: node.state.mode == 'HOLD', 10)
            except Exception as error:
                cleanup_errors.append(str(error))
            try:
                if not node.call(node.arm, CommandBool.Request(value=False)).success:
                    raise RuntimeError('Cleanup disarm rejected')
                node.until(lambda: not node.state.armed, 10)
                if node.state.mode == 'HOLD':
                    print('Navigation stop verified: HOLD and disarmed', flush=True)
            except Exception as error:
                cleanup_errors.append(str(error))
        if rates_requested:
            for identity, _ in TELEMETRY_RATES:
                try:
                    if not node.call(node.interval, MessageInterval.Request(message_id=identity, message_rate=0.)).success:
                        raise RuntimeError(f'Could not restore default telemetry interval: {identity}')
                except Exception as error:
                    cleanup_errors.append(str(error))
        node.destroy_node()
        rclpy.shutdown()
        if cleanup_errors:
            raise RuntimeError('Navigation cleanup: '+'; '.join(cleanup_errors))


if __name__ == '__main__':
    main()
