#!/usr/bin/env python3
"""Exercise delivery of CLI-friendly text, full-size RGB/depth, and TF."""

import sys
import time

import rclpy
from geometry_msgs.msg import TransformStamped
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from std_msgs.msg import String
from tf2_ros import TransformBroadcaster, TransformListener, Buffer


def main():
    rclpy.init()
    node = rclpy.create_node("monitor_probe_" + sys.argv[1])
    seen = set()
    buffer = Buffer()
    listener = TransformListener(buffer, node)
    broadcaster = TransformBroadcaster(node)
    publishers = []
    subscriptions = []
    messages = []

    def receive(message, label):
        if label == "text":
            assert message.data == "monitor delivery verified"
        else:
            assert (message.width, message.height) == (1280, 720)
            assert len(message.data) == message.step * message.height
            expected = (
                bytes((42, 128, 220)) * (1280 * 720)
                if label == "rgb" else bytes([42]) * (message.step * message.height)
            )
            assert bytes(message.data) == expected
        seen.add(label)

    for label, msg_type, encoding, stride in (
        ("text", String, None, 0),
        ("rgb", Image, "rgb8", 3),
        ("depth", Image, "32FC1", 4),
    ):
        topic = "/monitor_smoke/" + label
        if sys.argv[1] == "publish":
            message = msg_type()
            if label == "text":
                message.data = "monitor delivery verified"
            else:
                message.width, message.height = 1280, 720
                message.encoding = encoding
                message.step = 1280 * stride
                message.header.frame_id = "probe_camera"
                message.data = (
                    bytes((42, 128, 220)) * (1280 * 720)
                    if label == "rgb" else bytes([42]) * (message.step * message.height)
                )
            messages.append(message)
            publishers.append(node.create_publisher(msg_type, topic, qos_profile_sensor_data))
        else:
            subscriptions.append(node.create_subscription(
                msg_type, topic,
                lambda message, label=label: receive(message, label),
                qos_profile_sensor_data,
            ))

    deadline = time.monotonic() + 35
    next_publish = 0
    try:
        while time.monotonic() < deadline:
            if publishers and time.monotonic() >= next_publish:
                for publisher, message in zip(publishers, messages):
                    publisher.publish(message)
                transform = TransformStamped()
                transform.header.stamp = node.get_clock().now().to_msg()
                transform.header.frame_id = "probe_base"
                transform.child_frame_id = "probe_camera"
                transform.transform.rotation.w = 1.0
                broadcaster.sendTransform(transform)
                next_publish = time.monotonic() + 0.2
            rclpy.spin_once(node, timeout_sec=0.05)
            if not publishers and seen == {"text", "rgb", "depth"}:
                if buffer.can_transform("probe_base", "probe_camera", rclpy.time.Time()):
                    print("PASS: cross-container text, 1280x720 RGB/depth payloads, and TF", flush=True)
                    return
        if not publishers:
            raise RuntimeError(f"Delivery timed out; received: {sorted(seen)}")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
