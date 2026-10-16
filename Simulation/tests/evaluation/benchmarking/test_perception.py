"""Run in maritime-benchmark:jazzy: actual images, ROS messages, and MCAP files."""

import ast
from dataclasses import fields
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
from cv_bridge import CvBridge
import numpy as np
from rclpy.serialization import serialize_message
import rosbag2_py
from std_msgs.msg import Header

from maritime_localization.depth import DepthLocalizer
from maritime_localization.interfaces import Observation
from maritime_localization.triangulation import TriangulationLocalizer
from maritime_perception.aruco import ArucoBoxDetector, BoundingBox, annotate
from maritime_perception.messages import detection_array

import runner


CONFIG = Path("/opt/autonomy_ws/src/maritime_perception/config/aruco.yaml")


def scene(markers=((1, 40),)):
    image = np.full((180, 420, 3), 255, dtype=np.uint8)
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    for identifier, left in markers:
        marker = cv2.aruco.drawMarker(dictionary, identifier, 80)
        image[50:130, left:left + 80] = marker[:, :, None]
    return image


class DetectorTests(unittest.TestCase):
    def test_detects_box_without_any_pose_api(self):
        with patch.object(cv2, "solvePnP", side_effect=AssertionError("Pose API forbidden")), \
             patch.object(cv2.aruco, "estimatePoseSingleMarkers", side_effect=AssertionError("Pose API forbidden")):
            boxes = ArucoBoxDetector().detect(scene())
        self.assertEqual(len(boxes), 1)
        box = boxes[0]
        self.assertEqual((box.marker_id, box.category), (1, "red"))
        np.testing.assert_allclose([box.center_x, box.center_y, box.width, box.height],
                                   [79.5, 89.5, 79, 79], atol=1)
        self.assertEqual({field.name for field in fields(box)},
                         {"marker_id", "category", "center_x", "center_y", "width", "height"})

    def test_repeated_ids_are_separate_boxes_and_unknown_ids_are_filtered(self):
        boxes = ArucoBoxDetector().detect(scene(((1, 20), (1, 160), (8, 300))))
        self.assertEqual([box.category for box in boxes], ["red", "red"])
        self.assertLess(boxes[0].center_x, boxes[1].center_x)

    def test_blank_and_rotated_marker(self):
        detector = ArucoBoxDetector()
        self.assertEqual(detector.detect(np.full((200, 200, 3), 255, np.uint8)), [])
        self.assertEqual(detector.detect(np.rot90(scene()).copy())[0].category, "red")

    def test_perspective_marker_box_encloses_its_projected_corners(self):
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        marker = cv2.aruco.drawMarker(dictionary, 2, 100)
        corners = np.float32([[60, 45], [180, 60], [170, 175], [50, 155]])
        transform = cv2.getPerspectiveTransform(np.float32([[0, 0], [99, 0], [99, 99], [0, 99]]), corners)
        image = cv2.warpPerspective(marker, transform, (240, 220), borderValue=255)
        box, = ArucoBoxDetector().detect(image)
        np.testing.assert_allclose([box.center_x, box.center_y, box.width, box.height],
                                   [115, 110, 130, 130], atol=2)

    def test_invalid_config_and_image_rejected(self):
        for arguments in ({"dictionary": "invalid"}, {"marker_ids": [1, 1]},
                          {"marker_ids": [99], "marker_categories": ["red"]},
                          {"marker_categories": ["pink"]}):
            with self.assertRaises(ValueError):
                ArucoBoxDetector(**arguments)
        with self.assertRaises(ValueError):
            ArucoBoxDetector().detect(np.zeros((20, 20), np.float32))

    def test_ros_headers_categories_empty_results_and_unused_pose(self):
        header = Header(frame_id="test_optical")
        header.stamp.sec, header.stamp.nanosec = 19, 123456
        output = detection_array(header, ArucoBoxDetector().detect(scene()))
        self.assertEqual(output.header, header)
        detection, = output.detections
        self.assertEqual(detection.header, header)
        self.assertEqual(detection.id, "")
        self.assertEqual(detection.bbox.center.theta, 0.0)
        self.assertEqual(detection.results[0].hypothesis.class_id, "red")
        self.assertEqual(detection.results[0].pose.pose.position.x, 0.0)
        self.assertEqual(detection_array(header, []).detections, [])

    def test_debug_does_not_modify_input(self):
        image = scene()
        before = image.copy()
        debug = annotate(image, ArucoBoxDetector().detect(image))
        np.testing.assert_array_equal(image, before)
        self.assertFalse(np.array_equal(debug, before))

    def test_no_localization_or_truth_access_in_detector_source(self):
        import maritime_perception
        forbidden = {"solvePnP", "solvePnPRansac", "estimatePoseSingleMarkers", "estimatePoseBoard", "triangulatePoints"}
        for path in Path(maritime_perception.__file__).parent.glob("*.py"):
            source = path.read_text()
            self.assertNotIn("ground_truth", source)
            tree = ast.parse(source)
            calls = [node.func.attr for node in ast.walk(tree)
                     if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
            self.assertFalse(forbidden.intersection(calls), path)


class ExtensionTests(unittest.TestCase):
    def test_unimplemented_methods_fail_explicitly_and_triangulation_rejects_depth(self):
        observation = Observation(1, "camera", (), np.eye(3), ())
        for method in (DepthLocalizer(), TriangulationLocalizer()):
            self.assertFalse(method.implemented)
            method.reset()
            with self.assertRaises(NotImplementedError):
                method.process(observation)
        with self.assertRaises(ValueError):
            TriangulationLocalizer().process(Observation(1, "camera", (), np.eye(3), (), np.ones((2, 2))))


class OfflineTests(unittest.TestCase):
    def test_real_bag_every_frame_headers_duplicate_categories_and_preview(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset = root / "dataset"
            dataset.mkdir()
            (dataset / "dataset.json").write_text(json.dumps({"name": "fixture", "status": "complete"}))
            (dataset / "quality.json").write_text(json.dumps({"passed": True}))
            writer = rosbag2_py.SequentialWriter()
            writer.open(rosbag2_py.StorageOptions(uri=str(dataset / "bag"), storage_id="mcap"),
                        rosbag2_py.ConverterOptions("cdr", "cdr"))
            topic = "/sensors/camera_0/color/image_raw"
            writer.create_topic(rosbag2_py.TopicMetadata(id=0, name=topic, type="sensor_msgs/msg/Image", serialization_format="cdr"))
            # Include a deliberately unresolvable truth type: the runner must never deserialize it.
            writer.create_topic(rosbag2_py.TopicMetadata(id=1, name="/blueboat/ground_truth/test", type="missing_msgs/msg/Secret", serialization_format="cdr"))
            writer.write("/blueboat/ground_truth/test", b"not an input", 1)
            for index, image in enumerate((scene(((1, 20), (1, 160))), np.full((180, 420, 3), 255, np.uint8))):
                message = CvBridge().cv2_to_imgmsg(image, encoding="bgr8")
                message.header.frame_id = "fixture_optical"
                message.header.stamp.sec = 10 + index
                writer.write(topic, serialize_message(message), (20 + index) * 1_000_000_000)
            del writer
            output = root / "results"
            report = runner.run(dataset, output, CONFIG, topic, 1)
            self.assertEqual(report["status"], "complete")
            self.assertEqual(report["frames_processed"], 2)
            self.assertEqual(report["frames_with_detections"], 1)
            self.assertEqual(report["detections_by_category"], {"red": 2})
            frames = [json.loads(line) for line in (output / "detections.jsonl").read_text().splitlines()]
            self.assertEqual(frames[0]["timestamp_ns"], 10_000_000_000)
            self.assertEqual(frames[0]["bag_timestamp_ns"], 20_000_000_000)
            self.assertEqual(frames[0]["frame_id"], "fixture_optical")
            self.assertEqual(frames[1]["boxes"], [])
            self.assertEqual(len(list((output / "previews").glob("*.jpg"))), 2)
            with self.assertRaises(FileExistsError):
                runner.run(dataset, output, CONFIG, topic, 0)


if __name__ == "__main__":
    unittest.main()
