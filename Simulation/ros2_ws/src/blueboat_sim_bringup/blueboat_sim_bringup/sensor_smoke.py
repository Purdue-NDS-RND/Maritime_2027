"""Evaluation-only RGB-D, ArUco, synchronization, truth, and TF checks."""

from __future__ import annotations

import json
import math
import os
import time

import cv2
from cv_bridge import CvBridge
import numpy as np
import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image
from tf2_ros import Buffer, TransformListener


EXPECTED_K = np.array([448.1328244542, 0.0, 640.0, 0.0, 514.1332824272, 360.0, 0.0, 0.0, 1.0])
EXPECTED_P = np.array([448.1328244542, 0.0, 640.0, 0.0, 0.0, 514.1332824272, 360.0, 0.0, 0.0, 0.0, 1.0, 0.0])


def stamp_ns(message) -> int:
    return message.header.stamp.sec * 1_000_000_000 + message.header.stamp.nanosec


def rotate_inverse(q, vector):
    # Rotation matrix transpose for unit quaternion (x, y, z, w).
    x, y, z, w = q.x, q.y, q.z, q.w
    rotation = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )
    return rotation.T @ vector, rotation


class SensorSmoke(Node):
    def __init__(self, manifest):
        super().__init__("blueboat_sensor_smoke")
        self.manifest = manifest
        self.bridge = CvBridge()
        self.rgb = {}
        self.depth = {}
        self.pairs = []
        self.info = None
        self.boat_odom = None
        self.buoy_odom = {}
        self.samples = []
        self.rgb_metadata = None
        self.depth_metadata = None
        self.rgb_stamps = []
        self.invalid_depth_seen = False
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        self.create_subscription(Image, "/blueboat/camera/rgb/image_raw", self.on_rgb, qos_profile_sensor_data)
        self.create_subscription(Image, "/blueboat/camera/depth/image_rect_raw", self.on_depth, qos_profile_sensor_data)
        self.create_subscription(CameraInfo, "/blueboat/camera/camera_info", self.on_info, qos_profile_sensor_data)
        self.create_subscription(Odometry, "/blueboat/ground_truth/odometry", self.on_boat, 20)
        for buoy in manifest["buoys"]:
            self.create_subscription(
                Odometry,
                f"/blueboat/ground_truth/{buoy['name']}/odometry",
                lambda message, name=buoy["name"]: self.buoy_odom.__setitem__(name, message),
                10,
            )

    def on_info(self, message):
        self.info = message

    def on_boat(self, message):
        self.boat_odom = message

    def on_rgb(self, message):
        key = stamp_ns(message)
        self.rgb[key] = message
        self.rgb_stamps.append(key)
        self.try_pair(key)

    def on_depth(self, message):
        key = stamp_ns(message)
        self.depth[key] = message
        self.try_pair(key)

    def try_pair(self, key):
        if key not in self.rgb or key not in self.depth or len(self.pairs) >= 100:
            return
        rgb = self.rgb.pop(key)
        depth = self.depth.pop(key)
        self.rgb_metadata = self.rgb_metadata or (rgb.encoding, rgb.width, rgb.height, rgb.header.frame_id)
        self.depth_metadata = self.depth_metadata or (depth.encoding, depth.width, depth.height, depth.header.frame_id)
        self.pairs.append(key)
        if len(self.pairs) % 10 == 0:
            self.inspect_sample(rgb, depth)
        cutoff = key - 2_000_000_000
        self.rgb = {stamp: msg for stamp, msg in self.rgb.items() if stamp >= cutoff}
        self.depth = {stamp: msg for stamp, msg in self.depth.items() if stamp >= cutoff}

    def inspect_sample(self, rgb_message, depth_message):
        rgb = self.bridge.imgmsg_to_cv2(rgb_message, desired_encoding="rgb8")
        depth = self.bridge.imgmsg_to_cv2(depth_message, desired_encoding="passthrough")
        self.invalid_depth_seen |= bool(np.any(~np.isfinite(depth)) or np.any(depth <= 0.0))
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        corners, ids, _ = cv2.aruco.detectMarkers(gray, self.dictionary)
        detected = {}
        if ids is not None:
            for marker_corners, marker_id in zip(corners, ids.flatten()):
                points = marker_corners.reshape(4, 2)
                width = float(np.mean([np.linalg.norm(points[0] - points[1]), np.linalg.norm(points[2] - points[3])]))
                center = np.mean(points, axis=0)
                half = max(2, int(width * 0.18))
                x0, x1 = max(0, int(center[0]) - half), min(depth.shape[1], int(center[0]) + half + 1)
                y0, y1 = max(0, int(center[1]) - half), min(depth.shape[0], int(center[1]) + half + 1)
                values = depth[y0:y1, x0:x1]
                values = values[np.isfinite(values) & (values > 0.0)]
                detected[int(marker_id)] = {"width": width, "depth": float(np.median(values)) if values.size else math.nan}
        self.samples.append(detected)

    def expected_depth(self, marker):
        pose = self.boat_odom.pose.pose
        boat = np.array([pose.position.x, pose.position.y, pose.position.z])
        _, rotation = rotate_inverse(pose.orientation, np.zeros(3))
        camera = boat + rotation @ np.array([0.35, 0.0, 0.40])
        point = marker["marker_plane_center"]
        delta = np.array([point["x"], point["y"], point["z"]]) - camera
        body_delta, _ = rotate_inverse(pose.orientation, delta)
        return float(body_delta[0])

    def assert_results(self):
        assert len(self.pairs) == 100, f"only received {len(self.pairs)} exact RGB/depth timestamp pairs"
        assert self.info is not None and self.boat_odom is not None
        assert self.info.width == 1280 and self.info.height == 720
        assert self.info.header.frame_id == "zed2i_left_camera_optical_frame"
        assert np.allclose(np.array(self.info.k), EXPECTED_K, atol=1e-3), self.info.k
        assert np.allclose(np.array(self.info.p), EXPECTED_P, atol=1e-3), self.info.p
        assert all(abs(value) < 1e-9 for value in self.info.d)
        assert self.rgb_metadata == ("rgb8", 1280, 720, "zed2i_left_camera_optical_frame")
        assert self.depth_metadata == ("32FC1", 1280, 720, "zed2i_left_camera_optical_frame")
        first, last = self.pairs[0], self.pairs[-1]
        rate = (len(self.pairs) - 1) * 1e9 / (last - first)
        # This is the effective rate seen by a Python subscriber while it also
        # decodes full-resolution RGB, depth, and ArUco samples. The Gazebo
        # source-rate check is separate so evaluator load is not mistaken for
        # the sensor's publication cadence.
        minimum_pair_rate = float(os.environ.get("RGBD_MIN_PAIR_RATE_HZ", "8.0"))
        assert minimum_pair_rate <= rate <= 33.0, (
            f"effective synchronized RGB-D pair rate was {rate:.2f} Hz "
            f"(minimum {minimum_pair_rate:.2f} Hz)"
        )
        assert len(self.samples) == 10
        for marker in self.manifest["buoys"]:
            marker_id = marker["marker_id"]
            detections = [sample[marker_id] for sample in self.samples if marker_id in sample]
            assert len(detections) >= 9, f"marker {marker_id} appeared in {len(detections)}/10 samples"
            assert min(item["width"] for item in detections) >= 24.0
            expected = self.expected_depth(marker)
            errors = [abs(item["depth"] - expected) for item in detections if math.isfinite(item["depth"])]
            assert errors and float(np.median(errors)) <= 0.05, (marker_id, expected, errors)
        expected_buoys = {item["name"]: item for item in self.manifest["buoys"]}
        assert set(self.buoy_odom) == set(expected_buoys)
        for name, odom in self.buoy_odom.items():
            assert odom.header.frame_id == "world"
            actual = odom.pose.pose
            expected = expected_buoys[name]["model_pose"]
            position_error = math.sqrt(
                (actual.position.x - expected["x"]) ** 2
                + (actual.position.y - expected["y"]) ** 2
                + (actual.position.z - expected["z"]) ** 2
            )
            assert position_error <= 0.01, (name, position_error)
            yaw = math.atan2(
                2.0 * (actual.orientation.w * actual.orientation.z + actual.orientation.x * actual.orientation.y),
                1.0 - 2.0 * (actual.orientation.y**2 + actual.orientation.z**2),
            )
            yaw_error = abs(math.atan2(math.sin(yaw - expected["yaw_rad"]), math.cos(yaw - expected["yaw_rad"])))
            assert yaw_error <= math.radians(0.5), (name, math.degrees(yaw_error))
        assert self.invalid_depth_seen, "no invalid pixels observed beyond the configured depth range"
        for parent, child in [
            ("world", "odom"),
            ("odom", "base_link"),
            ("base_link", "zed2i_camera_link"),
            ("zed2i_camera_link", "zed2i_left_camera_optical_frame"),
        ]:
            assert self.tf_buffer.can_transform(parent, child, rclpy.time.Time(), timeout=rclpy.duration.Duration(seconds=2.0)), f"missing TF {parent}->{child}"
        world_odom = self.tf_buffer.lookup_transform("world", "odom", rclpy.time.Time()).transform
        base_camera = self.tf_buffer.lookup_transform("base_link", "zed2i_camera_link", rclpy.time.Time()).transform
        camera_optical = self.tf_buffer.lookup_transform(
            "zed2i_camera_link", "zed2i_left_camera_optical_frame", rclpy.time.Time()
        ).transform
        assert np.allclose(
            [world_odom.translation.x, world_odom.translation.y, world_odom.translation.z], [0.0, 0.0, 0.0], atol=1e-6
        )
        assert np.allclose(rotate_inverse(world_odom.rotation, np.zeros(3))[1], np.eye(3), atol=1e-6)
        assert np.allclose(
            [base_camera.translation.x, base_camera.translation.y, base_camera.translation.z], [0.35, 0.0, 0.40], atol=1e-6
        )
        assert np.allclose(rotate_inverse(base_camera.rotation, np.zeros(3))[1], np.eye(3), atol=1e-6)
        optical_rotation = rotate_inverse(camera_optical.rotation, np.zeros(3))[1]
        expected_optical_rotation = np.array([[0.0, 0.0, 1.0], [-1.0, 0.0, 0.0], [0.0, -1.0, 0.0]])
        assert np.allclose(optical_rotation, expected_optical_rotation, atol=1e-6)
        assert np.allclose(optical_rotation @ np.array([0.0, 0.0, 1.0]), [1.0, 0.0, 0.0], atol=1e-6)
        print(
            f"RGB-D PASS: 100 exact ROS pairs at {rate:.2f} Hz effective evaluator rate; "
            "markers, depth, truth, and TF verified"
        )


def main():
    manifest_path = os.environ.get("SCENARIO_MANIFEST", "/scenario/active.manifest.json")
    with open(manifest_path, encoding="utf-8") as stream:
        manifest = json.load(stream)
    rclpy.init()
    node = SensorSmoke(manifest)
    deadline = time.monotonic() + 45.0
    try:
        while time.monotonic() < deadline and len(node.pairs) < 100:
            rclpy.spin_once(node, timeout_sec=0.1)
        for _ in range(20):
            rclpy.spin_once(node, timeout_sec=0.05)
        node.assert_results()
    finally:
        node.destroy_node()
        rclpy.shutdown()
