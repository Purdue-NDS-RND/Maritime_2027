"""Publish the configured camera roster as durable Adapter metadata."""
import json
import re

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import String


class CameraRoster(Node):
    def __init__(self):
        super().__init__('camera_roster')
        cameras = self.declare_parameter('enabled_cameras', ['camera_0']).value
        if (not cameras or len(set(cameras)) != len(cameras)
                or not all(re.fullmatch(r'camera_\d+', camera) for camera in cameras)):
            raise ValueError('enabled_cameras requires distinct camera_N names')
        self.message = String(data=json.dumps({'schema_version': 1, 'enabled_cameras': cameras}))
        self.publisher = self.create_publisher(String, '/sensors/camera_roster',
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.publisher.publish(self.message)
        self.create_timer(1., lambda: self.publisher.publish(self.message))


def main():
    rclpy.init()
    node = CameraRoster()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
