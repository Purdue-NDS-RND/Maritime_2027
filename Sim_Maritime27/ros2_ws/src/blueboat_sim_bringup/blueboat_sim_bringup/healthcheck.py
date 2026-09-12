import os
import time

import rclpy
from mavros_msgs.msg import State
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import Image


class Health(Node):
    def __init__(self):
        super().__init__("blueboat_sim_healthcheck")
        self.clock = False
        self.camera = os.environ.get("CAMERA_ENABLED", "1") not in {"1", "true", "yes"}
        self.connected = False
        self.create_subscription(Clock, "/clock", self.on_clock, qos_profile_sensor_data)
        self.create_subscription(State, "/mavros/state", self.on_state, 10)
        self.create_subscription(Image, "/blueboat/camera/rgb/image_raw", self.on_image, qos_profile_sensor_data)

    def on_clock(self, message):
        self.clock = message.clock.sec > 0 or message.clock.nanosec > 0

    def on_state(self, message):
        self.connected = message.connected

    def on_image(self, _message):
        self.camera = True


def main():
    rclpy.init()
    node = Health()
    deadline = time.monotonic() + 8.0
    try:
        while time.monotonic() < deadline and not (node.clock and node.camera and node.connected):
            rclpy.spin_once(node, timeout_sec=0.25)
        if not (node.clock and node.camera and node.connected):
            raise SystemExit(1)
    finally:
        node.destroy_node()
        rclpy.shutdown()
