"""Read-only flight-controller connectivity check, independent of simulation."""

import time

import rclpy
from mavros_msgs.msg import State
from rclpy.node import Node


class Health(Node):
    def __init__(self):
        super().__init__("maritime_vehicle_healthcheck")
        self.connected = False
        self.create_subscription(State, "/mavros/state", self.on_state, 10)

    def on_state(self, message):
        self.connected = message.connected


def main():
    rclpy.init()
    node = Health()
    deadline = time.monotonic() + 8.0
    try:
        while time.monotonic() < deadline and not node.connected:
            rclpy.spin_once(node, timeout_sec=0.25)
        if not node.connected:
            raise SystemExit(1)
    finally:
        node.destroy_node()
        rclpy.shutdown()
