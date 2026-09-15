"""Simulation Adapter diagnostics with separate, evidence-backed readiness."""

import math
import time

import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from mavros_msgs.msg import State, TimesyncStatus
from mavros_msgs.srv import CommandBool, CommandInt, CommandLong, SetMode
from nav_msgs.msg import Odometry
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from rclpy.parameter_client import AsyncParameterClient
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu, NavSatFix, TimeReference
from std_msgs.msg import Bool
from tf2_msgs.msg import TFMessage

from .mavros_readiness import (
    PLUGIN_ALLOWLIST, PLUGIN_DENYLIST, PUBLIC_SERVICES, PUBLIC_TOPICS,
    parameter_mismatches, validate_fix, validate_graph, validate_imu, validate_odom,
)


LEVEL = {"OK": DiagnosticStatus.OK, "STALE": DiagnosticStatus.STALE, "ERROR": DiagnosticStatus.ERROR}
MAVROS_PARAMETERS = {
    "fcu_url": "udp://:14552@", "gcs_url": "", "uas_url": "/uas1",
    "fcu_protocol": "v2.0", "system_id": 255, "component_id": 191,
    "target_system_id": 1, "target_component_id": 1,
    "plugin_allowlist": PLUGIN_ALLOWLIST, "plugin_denylist": PLUGIN_DENYLIST,
}
PARAMETER_GROUPS = {
    "/mavros": MAVROS_PARAMETERS,
    "/mavros/sys": {
        "heartbeat_rate": 1.0, "heartbeat_mav_type": "ONBOARD_CONTROLLER",
        "conn_timeout": 10.0, "disable_diag": False,
    },
    "/mavros/time": {
        "time_ref_source": "fcu", "timesync_mode": "MAVLINK",
        "timesync_avg_alpha": 0.6, "timesync_rate": 10.0, "system_time_rate": 1.0,
    },
    "/mavros/local_position": {
        "frame_id": "map", "tf.send": False, "tf.frame_id": "map",
        "tf.child_frame_id": "base_link", "tf.send_fcu": False,
    },
    "/mavros/global_position": {
        "frame_id": "map", "child_frame_id": "base_link", "tf.send": False,
        "tf.frame_id": "map", "tf.global_frame_id": "earth",
        "tf.child_frame_id": "base_link",
    },
    "/mavros/imu": {"frame_id": "base_link"},
}


def status(name, level, reason, ready, extra=()):
    message = DiagnosticStatus(name=name, hardware_id="simulation_adapter", level=level, message=reason)
    values = [("contract_version", "1.0.0"), ("source_ready", str(ready).lower()), ("reason", reason), *extra]
    message.values = [KeyValue(key=key, value=str(value)) for key, value in values]
    return message


class AdapterDiagnostics(Node):
    def __init__(self):
        super().__init__("simulation_adapter_diagnostics")
        self.publisher = self.create_publisher(DiagnosticArray, "/diagnostics", 10)
        self.state = None
        self.telemetry = {"imu": None, "local": None, "global": None}
        self.time_reference_arrival = None
        self.timesync = None
        self.mavros_diagnostics = {}
        self.prohibited_tf = None
        self.wire_v2 = False
        self.parameter_values = {}
        self.parameter_errors = {node: "parameters_unobserved" for node in PARAMETER_GROUPS}
        self.parameter_clients = {node: AsyncParameterClient(self, node) for node in PARAMETER_GROUPS}
        self.parameter_futures = {node: None for node in PARAMETER_GROUPS}
        self.command_clients = {
            "/mavros/cmd/arming": self.create_client(CommandBool, "/mavros/cmd/arming"),
            "/mavros/set_mode": self.create_client(SetMode, "/mavros/set_mode"),
            "/mavros/cmd/command": self.create_client(CommandLong, "/mavros/cmd/command"),
            "/mavros/cmd/command_int": self.create_client(CommandInt, "/mavros/cmd/command_int"),
        }
        self.create_subscription(Bool, "/adapter/private/mavlink_v2_observed", lambda msg: setattr(self, "wire_v2", self.wire_v2 or msg.data), 10)
        self.create_subscription(State, "/mavros/state", lambda msg: setattr(self, "state", (time.monotonic_ns(), msg)), 10)
        self.create_subscription(Imu, "/mavros/imu/data", lambda msg: self.on_telemetry("imu", msg, validate_imu), qos_profile_sensor_data)
        self.create_subscription(Odometry, "/mavros/local_position/odom", lambda msg: self.on_telemetry("local", msg, validate_odom), qos_profile_sensor_data)
        self.create_subscription(NavSatFix, "/mavros/global_position/global", lambda msg: self.on_telemetry("global", msg, validate_fix), qos_profile_sensor_data)
        self.create_subscription(TimeReference, "/mavros/time_reference", lambda _: setattr(self, "time_reference_arrival", time.monotonic_ns()), qos_profile_sensor_data)
        self.create_subscription(TimesyncStatus, "/mavros/timesync_status", self.on_timesync, qos_profile_sensor_data)
        self.create_subscription(DiagnosticArray, "/diagnostics", self.on_diagnostics, 10)
        self.create_subscription(TFMessage, "/tf", self.on_tf, 10)
        self.create_timer(0.5, self.publish_status, clock=Clock(clock_type=ClockType.STEADY_TIME))

    def on_telemetry(self, key, message, validator):
        self.telemetry[key] = (time.monotonic_ns(), validator(message))

    def on_timesync(self, message):
        values = (message.observed_offset_ns, message.estimated_offset_ns, message.round_trip_time_ms)
        self.timesync = (time.monotonic_ns(), all(math.isfinite(float(value)) for value in values))

    def on_tf(self, message):
        for transform in message.transforms:
            if transform.header.frame_id in ("map", "odom") and transform.child_frame_id == "base_link":
                self.prohibited_tf = f"{transform.header.frame_id}->base_link"

    def on_diagnostics(self, message):
        for item in message.status:
            if item.name.startswith(("adapter/", "camera_adapter/", "mavros_adapter/")):
                continue
            lowered = f"{item.name} {item.message} " + " ".join(f"{value.key}={value.value}" for value in item.values)
            lowered = lowered.lower()
            if "mavros" in lowered:
                self.mavros_diagnostics[item.name] = (item.level, item.message)

    def poll_parameters(self):
        for node, expected_values in PARAMETER_GROUPS.items():
            future = self.parameter_futures[node]
            client = self.parameter_clients[node]
            if future is None:
                if client.services_are_ready():
                    self.parameter_futures[node] = client.get_parameters(list(expected_values))
                continue
            if not future.done():
                continue
            try:
                parameters = future.result()
                observed = {name: value.value for name, value in zip(expected_values, parameters)}
                self.parameter_values[node] = observed
                mismatches = parameter_mismatches(expected_values, observed)
                self.parameter_errors[node] = f"parameter_mismatch:{','.join(mismatches)}" if mismatches else None
            except Exception as error:
                self.parameter_errors[node] = f"parameter_query_failed:{error}"
            self.parameter_futures[node] = None

    def graph_state(self):
        topic_names = dict(self.get_topic_names_and_types())
        service_names = dict(self.get_service_names_and_types())
        graph_valid, graph_reason = validate_graph(topic_names, service_names)
        if not graph_valid:
            return DiagnosticStatus.ERROR, graph_reason, False
        errors = [f"{node}:{reason}" for node, reason in self.parameter_errors.items() if reason]
        if errors:
            return DiagnosticStatus.ERROR, errors[0], False
        return DiagnosticStatus.OK, "ready", True

    def fcu_state(self, source_ready):
        now = time.monotonic_ns()
        if not source_ready:
            return DiagnosticStatus.ERROR, "source_unready", False
        if self.state is None or now - self.state[0] > 2_000_000_000:
            return DiagnosticStatus.STALE, "state_stale", False
        if not self.state[1].connected:
            return DiagnosticStatus.ERROR, "fcu_disconnected", False
        for key, sample in self.telemetry.items():
            if sample is None or now - sample[0] > 2_000_000_000:
                return DiagnosticStatus.STALE, f"telemetry_stale:{key}", False
            if not sample[1]:
                return DiagnosticStatus.ERROR, f"telemetry_invalid:{key}", False
        if self.time_reference_arrival is None or now - self.time_reference_arrival > 2_000_000_000:
            return DiagnosticStatus.STALE, "time_reference_stale", False
        if self.timesync is None or now - self.timesync[0] > 2_000_000_000:
            return DiagnosticStatus.STALE, "timesync_stale", False
        if not self.timesync[1]:
            return DiagnosticStatus.ERROR, "timesync_invalid", False
        diagnostic_errors = [
            message or name for name, (level, message) in self.mavros_diagnostics.items()
            if level >= DiagnosticStatus.ERROR
        ]
        if diagnostic_errors:
            return DiagnosticStatus.ERROR, f"mavros_diagnostic_error:{diagnostic_errors[0]}", False
        if self.prohibited_tf:
            return DiagnosticStatus.ERROR, f"prohibited_mavros_tf:{self.prohibited_tf}", False
        if not self.wire_v2:
            return DiagnosticStatus.ERROR, "mavlink_v2_wire_unverified", False
        return DiagnosticStatus.OK, "ready", True

    def publish_status(self):
        self.poll_parameters()
        source_level, source_reason, source_ready = self.graph_state()
        fcu_level, fcu_reason, fcu_ready = self.fcu_state(source_ready)
        array = DiagnosticArray()
        array.header.stamp = self.get_clock().now().to_msg()
        array.status = [status("adapter/process_liveness", DiagnosticStatus.OK, "alive", True)]
        parameter_evidence = tuple(
            (f"{node}.{name}", value)
            for node, values in self.parameter_values.items() for name, value in values.items()
        )
        array.status.append(status("mavros_adapter/source_readiness", source_level, source_reason, source_ready, parameter_evidence))
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
