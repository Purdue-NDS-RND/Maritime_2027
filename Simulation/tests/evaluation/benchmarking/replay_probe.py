"""Compare ROS detector outputs with saved offline boxes at source timestamps."""

import argparse
import json
from pathlib import Path
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2DArray


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=40)
    parser.add_argument("--minimum-frames", type=int, default=1)
    args = parser.parse_args()
    expected = {}
    for line in args.reference.read_text().splitlines():
        frame = json.loads(line)
        expected[(frame["timestamp_ns"], frame["frame_id"])] = frame["boxes"]
    received, debug, errors = set(), set(), []

    def key(header):
        return header.stamp.sec * 1_000_000_000 + header.stamp.nanosec, header.frame_id

    def check(message):
        stamp = key(message.header)
        boxes = expected.get(stamp)
        if boxes is None:
            errors.append(f"Unexpected source header: {stamp}")
            return
        if stamp in received:
            errors.append(f"Duplicate output: {stamp}")
        received.add(stamp)
        if len(boxes) != len(message.detections):
            errors.append(f"Different box count: {stamp}")
            return
        for box, detection in zip(boxes, message.detections):
            actual = (detection.bbox.center.position.x, detection.bbox.center.position.y,
                      detection.bbox.size_x, detection.bbox.size_y)
            target = tuple(box[field] for field in ("center_x", "center_y", "width", "height"))
            if actual != target or detection.header != message.header or detection.id:
                errors.append(f"Different box/header/identity: {stamp}")
            if [result.hypothesis.class_id for result in detection.results] != [box["category"]]:
                errors.append(f"Different category: {stamp}")

    rclpy.init()
    node = Node("recorded_detection_probe")
    node.create_subscription(Detection2DArray, "/perception/camera_0/detections", check, qos_profile_sensor_data)
    node.create_subscription(Image, "/perception/camera_0/debug/image",
                             lambda message: debug.add(key(message.header)), qos_profile_sensor_data)
    try:
        deadline = time.monotonic() + args.seconds
        print("Replay probe ready", flush=True)
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        passed = not errors and len(received) >= args.minimum_frames and bool(debug & received)
        report = dict(passed=passed, reference_frames=len(expected), received_frames=len(received),
                      debug_frames=len(debug), errors=errors)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        raise SystemExit(0 if passed else 1)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
