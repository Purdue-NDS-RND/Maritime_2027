"""Simulation Adapter diagnostics with deliberately separate readiness states."""

from __future__ import annotations

import time

import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from mavros_msgs.msg import State
from mavros_msgs.srv import CommandBool, SetMode
from nav_msgs.msg import Odometry
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image, Imu, NavSatFix

from .camera_contract import (
    MAX_ACQUISITION_AGE_NS,
    MAX_ARRIVAL_SILENCE_NS,
    MATCH_TOLERANCE_NS,
    freshness,
    stamp_ns,
    validate_camera_info,
    validate_image,
)


def status(name, level, reason, ready, extra=()):
    message = DiagnosticStatus()
    message.name = name
    message.hardware_id = "simulation_adapter"
    message.level = level
    message.message = reason
    values = [
        ("contract_version", "1.0.0"),
        ("source_ready", str(ready).lower()),
        ("reason", reason),
    ]
    values.extend(extra)
    message.values = [KeyValue(key=key, value=str(value)) for key, value in values]
    return message


class AdapterDiagnostics(Node):
    def __init__(self):
        super().__init__("simulation_adapter_diagnostics")
        self.publisher = self.create_publisher(DiagnosticArray, "/diagnostics", 10)
        self.camera = {"color": None, "depth": None, "info": None}
        self.camera_error = None
        self.last_triple_stamp = None
        self.state = None
        self.telemetry = {"imu": None, "local": None, "global": None}
        self.arm = self.create_client(CommandBool, "/mavros/cmd/arming")
        self.mode = self.create_client(SetMode, "/mavros/set_mode")
        self.create_subscription(Image, "/sensors/camera_0/color/image_raw", lambda msg: self.on_image("color", msg), qos_profile_sensor_data)
        self.create_subscription(Image, "/sensors/camera_0/depth/image_rect_raw", lambda msg: self.on_image("depth", msg), qos_profile_sensor_data)
        self.create_subscription(CameraInfo, "/sensors/camera_0/color/camera_info", self.on_info, qos_profile_sensor_data)
        self.create_subscription(State, "/mavros/state", self.on_state, 10)
        self.create_subscription(Imu, "/mavros/imu/data", lambda msg: self.on_telemetry("imu", msg), qos_profile_sensor_data)
        self.create_subscription(Odometry, "/mavros/local_position/odom", lambda msg: self.on_telemetry("local", msg), qos_profile_sensor_data)
        self.create_subscription(NavSatFix, "/mavros/global_position/global", lambda msg: self.on_telemetry("global", msg), qos_profile_sensor_data)
        self.create_timer(0.5, self.publish_status, clock=Clock(clock_type=ClockType.STEADY_TIME))

    def record(self, key, message, error):
        current_stamp = stamp_ns(message)
        if current_stamp <= 0:
            self.camera_error = "invalid_header_stamp"
            return
        previous = self.camera[key]
        if previous is not None and current_stamp <= previous[0]:
            self.camera_error = "nonmonotonic_header_stamp"
            return
        if error:
            self.camera_error = error
            return
        self.camera[key] = (current_stamp, time.monotonic_ns(), message)
        self.try_triple()

    def on_image(self, key, message):
        self.record(key, message, validate_image(message, depth=key == "depth"))

    def on_info(self, message):
        self.record("info", message, validate_camera_info(message))

    def try_triple(self):
        if any(value is None for value in self.camera.values()):
            return
        color, depth, info = (self.camera[key] for key in ("color", "depth", "info"))
        if color[0] != depth[0] or color[0] != info[0]:
            # Streams arrive through separate DDS callbacks. Keep the previous
            # valid triple during this ordinary partial update; expiry below
            # turns a persistent mismatch into an ERROR.
            return
        if not (
            color[2].width == depth[2].width == info[2].width
            and color[2].height == depth[2].height == info[2].height
        ):
            self.camera_error = "invalid_dimensions"
            return
        self.camera_error = None
        self.last_triple_stamp = color[0]

    def on_state(self, message):
        self.state = (time.monotonic_ns(), message)

    def on_telemetry(self, key, message):
        self.telemetry[key] = time.monotonic_ns()

    def camera_state(self):
        if self.camera_error:
            return DiagnosticStatus.ERROR, self.camera_error, False
        if self.last_triple_stamp is None:
            return DiagnosticStatus.STALE, "unobserved", False
        ros_now = self.get_clock().now().nanoseconds
        steady_now = time.monotonic_ns()
        results = [freshness(item[0], item[1], ros_now, steady_now) for item in self.camera.values()]
        errors = [reason for state, reason in results if state == "ERROR"]
        stale = [reason for state, reason in results if state == "STALE"]
        if errors:
            return DiagnosticStatus.ERROR, errors[0], False
        if stale:
            return DiagnosticStatus.STALE, stale[0], False
        if ros_now - self.last_triple_stamp > MAX_ACQUISITION_AGE_NS:
            return DiagnosticStatus.ERROR, "timestamp_mismatch", False
        return DiagnosticStatus.OK, "ready", True

    def mavros_source_state(self):
        topics = ("/mavros/state", "/mavros/imu/data", "/mavros/local_position/odom", "/mavros/global_position/global")
        publishers = all(self.get_publishers_info_by_topic(topic) for topic in topics)
        services = self.arm.service_is_ready() and self.mode.service_is_ready()
        ready = publishers and services
        return (DiagnosticStatus.OK, "ready", True) if ready else (DiagnosticStatus.STALE, "interfaces_unavailable", False)

    def fcu_state(self):
        now = time.monotonic_ns()
        if self.state is None:
            return DiagnosticStatus.STALE, "state_unobserved", False
        if now - self.state[0] > 2_000_000_000:
            return DiagnosticStatus.STALE, "state_stale", False
        if not self.state[1].connected:
            return DiagnosticStatus.ERROR, "fcu_disconnected", False
        if any(value is None or now - value > 2_000_000_000 for value in self.telemetry.values()):
            return DiagnosticStatus.STALE, "telemetry_stale", False
        return DiagnosticStatus.OK, "ready", True

    def publish_status(self):
        camera_level, camera_reason, camera_ready = self.camera_state()
        source_level, source_reason, source_ready = self.mavros_source_state()
        fcu_level, fcu_reason, fcu_ready = self.fcu_state()
        timing = (
            ("camera_id", "camera_0"),
            ("rgb_depth_match_tolerance_ns", MATCH_TOLERANCE_NS),
            ("max_acquisition_age_ns", MAX_ACQUISITION_AGE_NS),
            ("max_arrival_silence_ns", MAX_ARRIVAL_SILENCE_NS),
        )
        array = DiagnosticArray()
        array.header.stamp = self.get_clock().now().to_msg()
        camera_names = (
            "color", "depth", "registration", "calibration", "synchronization", "frames", "source_readiness",
        )
        array.status = [status("adapter/process_liveness", DiagnosticStatus.OK, "alive", True)]
        array.status.append(status("camera_adapter/configuration", DiagnosticStatus.OK, "valid", True, timing))
        array.status.extend(
            status(f"camera_adapter/camera_0/{name}", camera_level, camera_reason, camera_ready, timing)
            for name in camera_names
        )
        array.status.append(status("mavros_adapter/source_readiness", source_level, source_reason, source_ready))
        array.status.append(status("mavros_adapter/fcu_readiness", fcu_level, fcu_reason, fcu_ready))
        array.status.append(status("adapter/mission_readiness", DiagnosticStatus.WARN, "mission_policy_unavailable", False))
        self.publisher.publish(array)


def main():
    rclpy.init()
    node = AdapterDiagnostics()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
