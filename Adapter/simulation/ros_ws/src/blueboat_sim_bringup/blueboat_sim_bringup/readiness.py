"""Wait for one explicitly selected Adapter readiness boundary."""

import argparse
import time

import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
from rclpy.node import Node


NAMES = {
    "liveness": "adapter/process_liveness",
    "source": "camera_adapter/camera_0/source_readiness",
    "fcu": "mavros_adapter/fcu_readiness",
    "mission": "adapter/mission_readiness",
}


class Watch(Node):
    def __init__(self, name):
        super().__init__("simulation_adapter_readiness_check")
        self.target = name
        self.result = None
        self.create_subscription(DiagnosticArray, "/diagnostics", self.callback, 10)

    def callback(self, message):
        for item in message.status:
            if item.name == self.target:
                self.result = item


def main():
    parser = argparse.ArgumentParser(description="Check one readiness boundary; boundaries are never inferred from each other.")
    parser.add_argument("boundary", choices=tuple(NAMES))
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    rclpy.init()
    node = Watch(NAMES[args.boundary])
    deadline = time.monotonic() + args.timeout
    try:
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.25)
            if node.result is not None:
                if node.result.level == DiagnosticStatus.OK:
                    return
                reason = next((item.value for item in node.result.values if item.key == "reason"), node.result.message)
                raise SystemExit(f"{args.boundary} readiness false: {reason}")
        raise SystemExit(f"timed out waiting for {args.boundary} readiness diagnostic")
    finally:
        node.destroy_node()
        rclpy.shutdown()
