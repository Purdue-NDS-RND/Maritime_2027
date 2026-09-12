"""Bounded MAVROS control-path acceptance test for the simulated boat."""

from __future__ import annotations

import math
import time

import rclpy
from mavros_msgs.msg import OverrideRCIn, State
from mavros_msgs.srv import CommandBool, SetMode
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu, NavSatFix


class MavrosSmoke(Node):
    def __init__(self):
        super().__init__("blueboat_mavros_smoke")
        self.state = None
        self.truth = None
        self.have_imu = False
        self.have_global = False
        self.have_local = False
        self.create_subscription(State, "/mavros/state", lambda msg: setattr(self, "state", msg), 10)
        self.create_subscription(Imu, "/mavros/imu/data", lambda _msg: setattr(self, "have_imu", True), qos_profile_sensor_data)
        self.create_subscription(NavSatFix, "/mavros/global_position/global", lambda _msg: setattr(self, "have_global", True), qos_profile_sensor_data)
        self.create_subscription(Odometry, "/mavros/local_position/odom", lambda _msg: setattr(self, "have_local", True), qos_profile_sensor_data)
        self.create_subscription(Odometry, "/blueboat/ground_truth/odometry", lambda msg: setattr(self, "truth", msg), 20)
        self.arm_client = self.create_client(CommandBool, "/mavros/cmd/arming")
        self.mode_client = self.create_client(SetMode, "/mavros/set_mode")
        self.override = self.create_publisher(OverrideRCIn, "/mavros/rc/override", 10)

    def spin_until(self, predicate, timeout, description):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            if predicate():
                return
        raise RuntimeError(f"timed out waiting for {description}")

    def call(self, client, request, timeout=10.0):
        assert client.wait_for_service(timeout_sec=timeout), f"service unavailable: {client.srv_name}"
        future = client.call_async(request)
        self.spin_until(future.done, timeout, client.srv_name)
        return future.result()

    def rc(self, throttle):
        message = OverrideRCIn()
        message.channels = [OverrideRCIn.CHAN_NOCHANGE] * 18
        message.channels[0] = 1500
        message.channels[2] = throttle
        self.override.publish(message)

    def position(self):
        point = self.truth.pose.pose.position
        return point.x, point.y

    def speed(self):
        velocity = self.truth.twist.twist.linear
        return math.hypot(velocity.x, velocity.y)


def main():
    rclpy.init()
    node = MavrosSmoke()
    armed_by_test = False
    try:
        node.spin_until(
            lambda: node.state is not None and node.state.connected and node.have_imu and node.have_global and node.have_local and node.truth is not None,
            30.0,
            "MAVROS state and telemetry",
        )
        mode = node.call(node.mode_client, SetMode.Request(base_mode=0, custom_mode="MANUAL"))
        assert mode.mode_sent, "ArduPilot rejected MANUAL mode"
        arm = node.call(node.arm_client, CommandBool.Request(value=True))
        assert arm.success, "ArduPilot rejected arm command"
        armed_by_test = True
        node.spin_until(lambda: node.state.armed, 10.0, "armed state")
        start = node.position()
        pulse_end = time.monotonic() + 0.5
        while time.monotonic() < pulse_end:
            node.rc(2000)
            rclpy.spin_once(node, timeout_sec=0.05)
        for _ in range(10):
            node.rc(1500)
            rclpy.spin_once(node, timeout_sec=0.05)
        node.spin_until(lambda: math.hypot(node.position()[0] - start[0], node.position()[1] - start[1]) >= 0.10, 8.0, "0.10 m ground-truth movement")
        node.spin_until(lambda: node.speed() <= 0.10, 20.0, "ground-truth speed to settle")
        disarm = node.call(node.arm_client, CommandBool.Request(value=False), timeout=5.0)
        assert disarm.success, "ArduPilot rejected disarm command"
        node.spin_until(lambda: not node.state.armed, 5.0, "disarmed state")
        armed_by_test = False
        print(
            "MAVROS PASS: connected telemetry, mode/arm services, bounded RC override, "
            "truth motion, settled speed, and disarm verified"
        )
    finally:
        for _ in range(10):
            node.rc(1500)
            rclpy.spin_once(node, timeout_sec=0.03)
        if armed_by_test:
            try:
                node.call(node.arm_client, CommandBool.Request(value=False), timeout=5.0)
            except Exception as exc:
                node.get_logger().error(f"disarm cleanup failed: {exc}")
        node.destroy_node()
        rclpy.shutdown()
