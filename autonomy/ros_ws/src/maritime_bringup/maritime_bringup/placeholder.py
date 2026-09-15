"""Explicitly limited process used while no autonomy application exists."""

import os

import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from rclpy.node import Node

from maritime_bringup.bootstrap_policy import validate_environment


DIAGNOSTIC_NAME = "maritime/preimplementation_placeholder"
DIAGNOSTIC_REASON = "preimplementation_placeholder"


class PreimplementationPlaceholder(Node):
    """Publish an honest non-mission diagnostic and intentionally do nothing else."""

    def __init__(self):
        super().__init__("maritime_preimplementation_placeholder")
        self._publisher = self.create_publisher(DiagnosticArray, "/diagnostics", 10)
        self._timer = self.create_timer(1.0, self.publish_status)
        self.publish_status()

    def publish_status(self):
        status = DiagnosticStatus()
        status.level = DiagnosticStatus.WARN
        status.name = DIAGNOSTIC_NAME
        status.hardware_id = "simulation"
        status.message = DIAGNOSTIC_REASON
        status.values = [
            KeyValue(key="adapter_environment", value="simulation"),
            KeyValue(key="placeholder_active", value="true"),
            KeyValue(key="mission_ready", value="false"),
            KeyValue(key="vehicle_commands_permitted", value="false"),
        ]
        message = DiagnosticArray()
        message.status = [status]
        self._publisher.publish(message)


def main():
    rejection = validate_environment(
        os.environ.get("ADAPTER_ENVIRONMENT"),
        os.environ.get("MARITIME_PREIMPLEMENTATION_PLACEHOLDER"),
    )
    if rejection is not None:
        raise SystemExit(rejection)

    rclpy.init()
    node = PreimplementationPlaceholder()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
