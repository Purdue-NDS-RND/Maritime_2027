"""RGB-D evaluator with lightweight acquisition callbacks and deferred OpenCV."""

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

from .guard import require_explicit_simulation


def stamp_ns(message):
    return message.header.stamp.sec * 1_000_000_000 + message.header.stamp.nanosec


def load_manifest():
    path = os.environ.get("SCENARIO_MANIFEST", "/scenario/active.manifest.json")
    with open(path, encoding="utf-8") as stream:
        manifest = json.load(stream)
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("buoys"), list):
        raise SystemExit("unsupported or malformed scenario manifest")
    seen = set()
    for buoy in manifest["buoys"]:
        key = buoy.get("evaluation_key")
        expected_topic = f"/blueboat/ground_truth/{key}/odometry"
        if not isinstance(key, str) or key in seen or buoy.get("name") != key or buoy.get("truth_topic") != expected_topic:
            raise SystemExit("manifest entity/evaluation identity contract violation")
        seen.add(key)
    return manifest


def inverse_rotation(q):
    x, y, z, w = q.x, q.y, q.z, q.w
    return np.array([
        [1 - 2 * (y*y + z*z), 2 * (x*y - z*w), 2 * (x*z + y*w)],
        [2 * (x*y + z*w), 1 - 2 * (x*x + z*z), 2 * (y*z - x*w)],
        [2 * (x*z - y*w), 2 * (y*z + x*w), 1 - 2 * (x*x + y*y)],
    ]).T


class SensorSmoke(Node):
    def __init__(self, manifest):
        super().__init__("blueboat_sensor_smoke")
        self.manifest = manifest
        self.cv_bridge = CvBridge()
        self.rgb, self.depth, self.info = {}, {}, {}
        self.pairs, self.inspection_pairs = [], []
        self.boat_odom, self.entity_truth = None, {}
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        self.create_subscription(Image, "/sensors/camera_0/color/image_raw", self.on_rgb, qos_profile_sensor_data)
        self.create_subscription(Image, "/sensors/camera_0/depth/image_rect_raw", self.on_depth, qos_profile_sensor_data)
        self.create_subscription(CameraInfo, "/sensors/camera_0/color/camera_info", self.on_info, qos_profile_sensor_data)
        self.create_subscription(Odometry, "/blueboat/ground_truth/odometry", lambda msg: setattr(self, "boat_odom", msg), 20)
        for buoy in manifest["buoys"]:
            self.create_subscription(
                Odometry, buoy["truth_topic"],
                lambda msg, key=buoy["evaluation_key"]: self.entity_truth.__setitem__(key, msg), 10,
            )

    def on_rgb(self, message):
        self.rgb[stamp_ns(message)] = message
        self.try_pair(stamp_ns(message))

    def on_depth(self, message):
        self.depth[stamp_ns(message)] = message
        self.try_pair(stamp_ns(message))

    def on_info(self, message):
        self.info[stamp_ns(message)] = message
        self.try_pair(stamp_ns(message))

    def try_pair(self, key):
        if key not in self.rgb or key not in self.depth or key not in self.info or len(self.pairs) >= 100:
            return
        triple = (self.rgb.pop(key), self.depth.pop(key), self.info.pop(key))
        self.pairs.append(key)
        if len(self.pairs) % 10 == 0:
            self.inspection_pairs.append(triple)
        cutoff = key - 2_000_000_000
        for queue in (self.rgb, self.depth, self.info):
            for stamp in tuple(queue):
                if stamp < cutoff:
                    del queue[stamp]

    def expected_depth(self, buoy):
        pose = self.boat_odom.pose.pose
        rotation = inverse_rotation(pose.orientation).T
        camera = np.array([pose.position.x, pose.position.y, pose.position.z]) + rotation @ np.array([0.35, 0.0, 0.4])
        buoy_pose = self.entity_truth[buoy["evaluation_key"]].pose.pose
        point = np.array([buoy_pose.position.x, buoy_pose.position.y, buoy_pose.position.z])
        point += inverse_rotation(buoy_pose.orientation).T @ np.array([0.311, 0.0, 0.75])
        delta = point - camera
        return float((inverse_rotation(pose.orientation) @ delta)[0])

    def inspect(self, triple):
        rgb_msg, depth_msg, info = triple
        assert stamp_ns(rgb_msg) == stamp_ns(depth_msg) == stamp_ns(info)
        assert rgb_msg.header.frame_id == depth_msg.header.frame_id == info.header.frame_id == "camera_0_optical_frame"
        assert rgb_msg.encoding in ("rgb8", "bgr8") and depth_msg.encoding == "32FC1"
        assert rgb_msg.width == depth_msg.width == info.width and rgb_msg.height == depth_msg.height == info.height
        assert info.k[0] > 0 and info.k[4] > 0 and info.k[8] == 1 and info.p[0] > 0 and info.p[5] > 0 and info.p[10] == 1
        rgb = self.cv_bridge.imgmsg_to_cv2(rgb_msg, desired_encoding="rgb8")
        depth = self.cv_bridge.imgmsg_to_cv2(depth_msg, desired_encoding="passthrough")
        finite_invalid = np.isfinite(depth) & (depth <= 0.0)
        assert not np.any(finite_invalid) and not np.any(np.isinf(depth)), "depth invalids were not normalized to NaN"
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        corners, ids, _ = cv2.aruco.detectMarkers(gray, self.dictionary)
        observations = []
        if ids is not None:
            for points, marker_id in zip(corners, ids.flatten()):
                points = points.reshape(4, 2)
                width = float(np.mean((np.linalg.norm(points[0]-points[1]), np.linalg.norm(points[2]-points[3]))))
                center = np.mean(points, axis=0)
                half = max(2, int(width * 0.18))
                x0, x1 = max(0, int(center[0])-half), min(depth.shape[1], int(center[0])+half+1)
                y0, y1 = max(0, int(center[1])-half), min(depth.shape[0], int(center[1])+half+1)
                values = depth[y0:y1, x0:x1]
                values = values[np.isfinite(values) & (values > 0)]
                observations.append({"marker_id": int(marker_id), "width": width, "depth": float(np.median(values)) if values.size else math.nan})
        return observations

    def assert_results(self):
        assert len(self.pairs) == 100, f"only received {len(self.pairs)} exact RGB/depth/CameraInfo triples"
        assert self.boat_odom is not None
        assert set(self.entity_truth) == {item["evaluation_key"] for item in self.manifest["buoys"]}
        rate = 99e9 / (self.pairs[-1] - self.pairs[0])
        minimum_rate = float(os.environ.get("RGBD_MIN_PAIR_RATE_HZ", "8.0"))
        assert minimum_rate <= rate <= 33.0, f"effective synchronized RGB-D pair rate was {rate:.2f} Hz (minimum {minimum_rate:.2f} Hz)"
        per_entity = {item["evaluation_key"]: [] for item in self.manifest["buoys"]}
        for triple in self.inspection_pairs:
            observations = self.inspect(triple)
            # Entity identity is preserved by associating same-category observations
            # to distinct truth-backed expected depths; marker_id is never a key.
            for marker_id in range(4):
                entities = [item for item in self.manifest["buoys"] if item["marker_id"] == marker_id]
                candidates = [item for item in observations if item["marker_id"] == marker_id and math.isfinite(item["depth"])]
                unmatched = list(candidates)
                for entity in sorted(entities, key=self.expected_depth):
                    if unmatched:
                        expected = self.expected_depth(entity)
                        chosen = min(unmatched, key=lambda item: abs(item["depth"] - expected))
                        unmatched.remove(chosen)
                        per_entity[entity["evaluation_key"]].append(chosen)
        for entity in self.manifest["buoys"]:
            detections = per_entity[entity["evaluation_key"]]
            assert len(detections) >= 9, f"entity {entity['evaluation_key']} appeared in {len(detections)}/10 samples"
            assert min(item["width"] for item in detections) >= 24.0
            errors = [abs(item["depth"] - self.expected_depth(entity)) for item in detections]
            assert float(np.median(errors)) <= 0.05, (entity["evaluation_key"], errors)
            odom = self.entity_truth[entity["evaluation_key"]]
            assert odom.header.frame_id == "world"
            expected = entity["model_pose"]
            actual = odom.pose.pose.position
            assert math.dist((actual.x, actual.y, actual.z), (expected["x"], expected["y"], expected["z"])) <= 0.01
            boat = self.boat_odom.pose.pose.position
            bearing = np.array([boat.x - actual.x, boat.y - actual.y, 0.0])
            if np.linalg.norm(bearing) > 1e-6:
                normal = inverse_rotation(odom.pose.pose.orientation).T @ np.array([1.0, 0.0, 0.0])
                assert float(normal @ (bearing / np.linalg.norm(bearing))) >= math.cos(math.radians(1.0)), f"buoy {entity['evaluation_key']} marker is not facing the boat"
        for parent, child in (("base_link", "camera_0_link"), ("camera_0_link", "camera_0_optical_frame")):
            assert self.tf_buffer.can_transform(parent, child, rclpy.time.Time(), timeout=rclpy.duration.Duration(seconds=2.0)), f"missing public TF {parent}->{child}"
        print(f"RGB-D PASS: 100 exact triples at {rate:.2f} Hz; deferred ArUco, canonical depth, entity-keyed truth, and public TF verified")


def main():
    require_explicit_simulation()
    manifest = load_manifest()
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
