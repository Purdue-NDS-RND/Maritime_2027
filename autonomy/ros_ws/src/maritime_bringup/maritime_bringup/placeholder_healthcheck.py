"""Check that the explicit bootstrap is alive without treating it as a mission."""

import os
import time

import rclpy
from diagnostic_msgs.msg import DiagnosticArray
from rclpy.node import Node

from maritime_bringup.bootstrap_policy import validate_environment
from maritime_bringup.placeholder import DIAGNOSTIC_NAME, DIAGNOSTIC_REASON


class PlaceholderHealthcheck(Node):
    def __init__(self):
        super().__init__("maritime_preimplementation_placeholder_healthcheck")
        self.healthy = False
        self.create_subscription(DiagnosticArray, "/diagnostics", self.on_diagnostics, 10)

    def on_diagnostics(self, message):
        for status in message.status:
            values = {item.key: item.value for item in status.values}
            if (
                status.name == DIAGNOSTIC_NAME
                and status.message == DIAGNOSTIC_REASON
                and values.get("placeholder_active") == "true"
                and values.get("mission_ready") == "false"
                and values.get("vehicle_commands_permitted") == "false"
            ):
                self.healthy = True


def main():
    rejection = validate_environment(
        os.environ.get("ADAPTER_ENVIRONMENT"),
        os.environ.get("MARITIME_PREIMPLEMENTATION_PLACEHOLDER"),
    )
    if rejection is not None:
        raise SystemExit(rejection)

    rclpy.init()
    node = PlaceholderHealthcheck()
    deadline = time.monotonic() + 8.0
    try:
        while time.monotonic() < deadline and not node.healthy:
            rclpy.spin_once(node, timeout_sec=0.25)
        if not node.healthy:
            raise SystemExit("preimplementation_placeholder_unavailable")
    finally:
        node.destroy_node()
        rclpy.shutdown()
