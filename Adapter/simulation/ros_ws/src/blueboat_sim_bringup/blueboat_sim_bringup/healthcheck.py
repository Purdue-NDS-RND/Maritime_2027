import time

import rclpy
from rclpy.node import Node


class Health(Node):
    def __init__(self):
        super().__init__("blueboat_sim_healthcheck")

    def live(self):
        names = {f"{namespace.rstrip('/')}/{name}" for name, namespace in self.get_node_names_and_namespaces()}
        required = {"/mavros", "/camera_0_boundary", "/simulation_adapter_diagnostics"}
        return required.issubset(names)


def main():
    rclpy.init()
    node = Health()
    deadline = time.monotonic() + 8.0
    try:
        while time.monotonic() < deadline and not node.live():
            rclpy.spin_once(node, timeout_sec=0.25)
        if not node.live():
            raise SystemExit(1)
    finally:
        node.destroy_node()
        rclpy.shutdown()
