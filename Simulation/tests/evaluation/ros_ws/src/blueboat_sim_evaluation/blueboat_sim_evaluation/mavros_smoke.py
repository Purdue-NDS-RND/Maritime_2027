"""Velocity-setpoint semantic test guarded against non-simulation execution."""

import math
import time

import rclpy
from geometry_msgs.msg import TwistStamped
from mavros_msgs.msg import State
from mavros_msgs.srv import CommandBool, SetMode
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu, NavSatFix

from .guard import require_explicit_simulation
from .safety import guided_mode_observed


class MavrosSmoke(Node):
    def __init__(self):
        super().__init__("blueboat_mavros_smoke")
        self.state = None
        self.truth = None
        self.have_imu = self.have_global = self.have_local = False
        self.create_subscription(State, "/mavros/state", lambda msg: setattr(self, "state", msg), 10)
        self.create_subscription(Imu, "/mavros/imu/data", lambda _: setattr(self, "have_imu", True), qos_profile_sensor_data)
        self.create_subscription(NavSatFix, "/mavros/global_position/global", lambda _: setattr(self, "have_global", True), qos_profile_sensor_data)
        self.create_subscription(Odometry, "/mavros/local_position/odom", lambda _: setattr(self, "have_local", True), qos_profile_sensor_data)
        self.create_subscription(Odometry, "/blueboat/ground_truth/odometry", lambda msg: setattr(self, "truth", msg), 20)
        self.arm_client = self.create_client(CommandBool, "/mavros/cmd/arming")
        self.mode_client = self.create_client(SetMode, "/mavros/set_mode")
        self.velocity_setpoint = self.create_publisher(
            TwistStamped, "/mavros/setpoint_velocity/cmd_vel", 10
        )

    def spin_until(self, predicate, timeout, description):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            if predicate():
                return
        raise RuntimeError(f"timed out waiting for {description}")

    def call(self, client, request, timeout=10.0):
        if not client.wait_for_service(timeout_sec=timeout):
            raise RuntimeError(f"service unavailable: {client.srv_name}")
        future = client.call_async(request)
        self.spin_until(future.done, timeout, client.srv_name)
        return future.result()

    def velocity(self, forward_m_s):
        message = TwistStamped()
        message.header.stamp = self.get_clock().now().to_msg()
        # MAVROS converts this ROS ENU velocity setpoint for the FCU.  Keeping
        # yaw rate zero makes this a bounded translation-only command.
        message.twist.linear.x = forward_m_s
        message.twist.angular.z = 0.0
        self.velocity_setpoint.publish(message)

    def publish_velocity_for(self, forward_m_s, duration_s):
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline:
            self.velocity(forward_m_s)
            rclpy.spin_once(self, timeout_sec=0.05)

    def arm_when_ready(self, timeout_s=60.0):
        deadline = time.monotonic() + timeout_s
        last_result = None
        while time.monotonic() < deadline:
            arm = self.call(self.arm_client, CommandBool.Request(value=True), timeout=5.0)
            if arm.success:
                return
            last_result = arm.result
            retry_deadline = min(time.monotonic() + 2.0, deadline)
            while time.monotonic() < retry_deadline:
                self.velocity(0.0)
                rclpy.spin_once(self, timeout_sec=0.05)
        raise RuntimeError(f"ArduPilot did not become armable within {timeout_s:.0f}s; last result: {last_result}")

    def position(self):
        point = self.truth.pose.pose.position
        return point.x, point.y

    def speed(self):
        velocity = self.truth.twist.twist.linear
        return math.hypot(velocity.x, velocity.y)


def main():
    require_explicit_simulation(command_capable=True)
    rclpy.init()
    node = MavrosSmoke()
    armed_by_test = False
    try:
        node.spin_until(
            lambda: node.state is not None and node.state.connected and node.have_imu and node.have_global and node.have_local and node.truth is not None,
            30.0, "MAVROS state and telemetry",
        )
        if node.state.armed:
            raise RuntimeError("refusing command test because vehicle was already armed")
        mode = node.call(node.mode_client, SetMode.Request(base_mode=0, custom_mode="GUIDED"))
        if not mode.mode_sent:
            raise RuntimeError("ArduPilot rejected GUIDED mode")
        node.spin_until(lambda: guided_mode_observed(node.state), 10.0, "GUIDED mode state")
        # ArduRover requires a recently received Guided target.  A zero-velocity
        # warmup is non-moving and gives both MAVROS and SITL time to establish
        # that setpoint path before the command-capable phase begins.
        node.publish_velocity_for(0.0, 3.0)
        node.arm_when_ready()
        armed_by_test = True
        node.spin_until(lambda: node.state.armed, 10.0, "armed state")
        start = node.position()
        node.publish_velocity_for(0.5, 3.0)
        node.publish_velocity_for(0.0, 1.0)
        node.spin_until(lambda: math.dist(node.position(), start) >= 0.10, 8.0, "0.10 m ground-truth movement")
        node.spin_until(lambda: node.speed() <= 0.10, 20.0, "ground-truth speed to settle")
        hold = node.call(node.mode_client, SetMode.Request(base_mode=0, custom_mode="HOLD"))
        if not hold.mode_sent:
            raise RuntimeError("ArduPilot rejected HOLD mode")
        node.spin_until(lambda: node.state is not None and node.state.mode == "HOLD", 10.0, "HOLD mode state")
        disarm = node.call(node.arm_client, CommandBool.Request(value=False), timeout=5.0)
        if not disarm.success:
            raise RuntimeError(f"ArduPilot rejected disarm command: {disarm.result}")
        node.spin_until(lambda: not node.state.armed, 5.0, "disarmed state")
        armed_by_test = False
        print("MAVROS PASS: connected telemetry, GUIDED velocity command, zero-velocity stop, motion, HOLD, and disarm verified")
    finally:
        # A bounded zero-velocity command is attempted on every exit.
        for _ in range(10):
            node.velocity(0.0)
            rclpy.spin_once(node, timeout_sec=0.03)
        if armed_by_test:
            try:
                node.call(node.arm_client, CommandBool.Request(value=False), timeout=5.0)
                node.spin_until(lambda: node.state is not None and not node.state.armed, 5.0, "cleanup disarm")
            except Exception as error:
                node.get_logger().error(f"CRITICAL disarm cleanup failed: {error}")
        node.destroy_node()
        rclpy.shutdown()
