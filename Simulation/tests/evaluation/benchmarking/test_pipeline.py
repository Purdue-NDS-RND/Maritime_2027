"""A complete ROS launch/play/record/export pass using a small synthetic bag."""

import csv
import json
from pathlib import Path
import statistics
import tempfile
import unittest

import cv2
from cv_bridge import CvBridge
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
import numpy as np
from rclpy.serialization import serialize_message
import rosbag2_py
from sensor_msgs.msg import CameraInfo
from tf2_msgs.msg import TFMessage
import yaml

import pipeline
from test_perception import scene


def fixture(dataset):
    dataset.mkdir()
    (dataset / "dataset.json").write_text(json.dumps(dict(name="fixture", status="complete", capture_domain=0)))
    (dataset / "quality.json").write_text(json.dumps(dict(passed=True)))
    qos = {"/tf_static": dict(reliability="reliable", durability="transient_local", history="keep_last", depth=100)}
    (dataset / "qos.yaml").write_text(yaml.safe_dump(qos))
    bridge = CvBridge()
    image = bridge.cv2_to_imgmsg(scene(), encoding="bgr8")
    depth = bridge.cv2_to_imgmsg(np.full((180, 420), 5., np.float32), encoding="32FC1")
    info = CameraInfo(width=420, height=180)
    info.k = [200., 0., 210., 0., 200., 90., 0., 0., 1.]
    for message in (image, depth, info):
        message.header.frame_id = "camera_optical"
    pose = Odometry()
    pose.header.frame_id, pose.child_frame_id = "map", "base_link"
    pose.pose.pose.orientation.w = 1.
    transform = TransformStamped()
    transform.header.frame_id, transform.child_frame_id = "base_link", "camera_optical"
    transform.transform.rotation.w = 1.
    static = TFMessage(transforms=[transform])
    types = {pipeline.IMAGE: "sensor_msgs/msg/Image", pipeline.DEPTH: "sensor_msgs/msg/Image",
             pipeline.INFO: "sensor_msgs/msg/CameraInfo", pipeline.POSE: "nav_msgs/msg/Odometry",
             "/tf_static": "tf2_msgs/msg/TFMessage"}
    writer = rosbag2_py.SequentialWriter()
    writer.open(rosbag2_py.StorageOptions(uri=str(dataset / "bag"), storage_id="mcap"),
                rosbag2_py.ConverterOptions("cdr", "cdr"))
    for index, (topic, message_type) in enumerate(types.items()):
        writer.create_topic(rosbag2_py.TopicMetadata(id=index, name=topic, type=message_type, serialization_format="cdr"))
    writer.write("/tf_static", serialize_message(static), 10_000_000_000)
    for index in range(20):
        stamp = 10_000_000_000 + index * 100_000_000
        # A fixed target seen from translated cameras, with matching RGB/depth/pose.
        image = bridge.cv2_to_imgmsg(cv2.warpAffine(scene(), np.float32([[1, 0, 4*index], [0, 1, 0]]),
                                                   (420, 180), borderValue=(255, 255, 255)), encoding="bgr8")
        image.header.frame_id = "camera_optical"
        pose.pose.pose.position.x = index * -0.1
        for topic, message in ((pipeline.POSE, pose), (pipeline.INFO, info),
                               (pipeline.DEPTH, depth), (pipeline.IMAGE, image)):
            message.header.stamp.sec = 10 + index // 10
            message.header.stamp.nanosec = (index % 10) * 100_000_000
            writer.write(topic, serialize_message(message), stamp)
    del writer


class PipelineTests(unittest.TestCase):
    def check_method(self, method):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture(root / "dataset")
            result = root / "result"
            try:
                report = pipeline.run(root / "dataset", result, method, 1.)
            except Exception:
                for log in sorted(result.glob("*.log")):
                    print(f"{log.name}:\n{log.read_text()}")
                raise
            self.assertEqual(report["status"], "complete")
            self.assertGreater(report["inputs_ready_arrays"], 0)
            self.assertGreater(report["estimates"], 0)
            self.assertIn("ok", report["localization_statuses"])
            self.assertNotIn("error", report["localization_statuses"])
            self.assertGreater(len((result / "estimates.csv").read_text().splitlines()), 1)
            self.assertTrue((result / "scatter.png").exists())
            with (result / "estimates.csv").open() as stream:
                rows = list(csv.DictReader(stream))
            # Latest-pose delivery may shift a sample by one 0.1 m vessel step.
            self.assertAlmostEqual(statistics.median(float(row["x_m"]) for row in rows), -3.2625, delta=.25)
            self.assertAlmostEqual(statistics.median(float(row["y_m"]) for row in rows), -.0125, delta=.05)
            self.assertTrue((result / "bag/metadata.yaml").is_file())

    def test_depth_ros_pipeline_exports_points(self):
        self.check_method("depth")

    def test_rgb_triangulation_ros_pipeline_exports_points(self):
        self.check_method("triangulation")


if __name__ == "__main__":
    unittest.main()
