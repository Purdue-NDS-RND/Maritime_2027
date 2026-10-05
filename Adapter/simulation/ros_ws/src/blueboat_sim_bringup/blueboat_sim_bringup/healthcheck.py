"""Fresh semantic Adapter health; mission readiness is intentionally excluded."""

import os
import time

import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
from rclpy.node import Node


class Health(Node):
    def __init__(self):
        super().__init__("blueboat_sim_healthcheck")
        self.samples = {}
        self.required_diagnostics = {"mavros_adapter/source_readiness", "mavros_adapter/fcu_readiness"}
        if os.environ.get("CAMERA_ENABLED", "1") == "1":
            self.required_diagnostics.add("camera_adapter/camera_0/source_readiness")
        self.create_subscription(DiagnosticArray, "/diagnostics", self.callback, 10)

    def callback(self, message):
        for item in message.status:
            if item.name in self.required_diagnostics:
                self.samples[item.name] = (time.monotonic(), item)

    def live(self):
        names = {f"{namespace.rstrip('/')}/{name}" for name, namespace in self.get_node_names_and_namespaces()}
        required = {"/mavros", "/camera_0_boundary", "/mavlink_v2_monitor", "/simulation_adapter_diagnostics", "/mavros_configuration", "/mavros_node", "/mavros_router"}
        return required.issubset(names)

    def failures(self):
        failures = []
        if not self.live():
            failures.append("process_liveness: required Adapter node missing")
        for name in sorted(self.required_diagnostics):
            sample = self.samples.get(name)
            if sample is None or time.monotonic() - sample[0] > 2.0:
                failures.append(f"{name}: diagnostic unobserved or stale")
                continue
            item = sample[1]
            ready = next((value.value for value in item.values if value.key == "source_ready"), "false")
            if item.level != DiagnosticStatus.OK or ready != "true":
                failures.append(f"{name}: {item.message}")
        return failures


def main():
    rclpy.init()
    node = Health()
    deadline = time.monotonic() + 8.0
    try:
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.25)
            if not node.failures():
                return
        raise SystemExit("Adapter semantic readiness false: " + "; ".join(node.failures()))
    finally:
        node.destroy_node()
        rclpy.shutdown()
