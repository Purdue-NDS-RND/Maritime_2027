"""Fresh semantic Adapter health; mission readiness is intentionally excluded."""

import os
import time

import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
from rclpy.node import Node

from .manifest import load_manifest


class Health(Node):
    def __init__(self):
        super().__init__("blueboat_sim_healthcheck")
        self.samples = {}
        manifest = load_manifest(os.environ.get('SCENARIO_MANIFEST', '/scenario/active.manifest.json'))
        self.cameras = ['camera_0', 'camera_1'] if manifest.get('boat_model', 'single') == 'dual' else ['camera_0']
        self.required_diagnostics = {"mavros_adapter/source_readiness", "mavros_adapter/fcu_readiness"}
        if os.environ.get("CAMERA_ENABLED", "1") == "1":
            self.required_diagnostics.update(f"camera_adapter/{camera}/source_readiness" for camera in self.cameras)
        self.create_subscription(DiagnosticArray, "/diagnostics", self.callback, 10)

    def callback(self, message):
        for item in message.status:
            if item.name in self.required_diagnostics:
                self.samples[item.name] = (time.monotonic(), item)

    def live(self):
        names = {f"{namespace.rstrip('/')}/{name}" for name, namespace in self.get_node_names_and_namespaces()}
        required = {"/camera_roster", "/mavros", "/camera_0_boundary", "/mavlink_v2_monitor", "/simulation_adapter_diagnostics", "/mavros_configuration", "/mavros_node", "/mavros_router"}
        required.update(f"/{camera}_boundary" for camera in self.cameras)
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
