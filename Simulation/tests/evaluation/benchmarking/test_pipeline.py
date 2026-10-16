"""A complete ROS launch/play/record/export pass using a small synthetic bag."""

import json
from pathlib import Path
import tempfile
import unittest

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
        for topic, message in ((pipeline.POSE, pose), (pipeline.INFO, info),
                               (pipeline.DEPTH, depth), (pipeline.IMAGE, image)):
            message.header.stamp.sec = 10 + index // 10
            message.header.stamp.nanosec = (index % 10) * 100_000_000
            writer.write(topic, serialize_message(message), stamp)
    del writer


class PipelineTests(unittest.TestCase):
    def test_placeholder_ros_pipeline_records_statuses_and_empty_csv(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture(root / "dataset")
            result = root / "result"
            try:
                report = pipeline.run(root / "dataset", result, "depth", 1.)
            except Exception:
                for log in sorted(result.glob("*.log")):
                    print(f"{log.name}:\n{log.read_text()}")
                raise
            self.assertEqual(report["status"], "complete")
            self.assertGreater(report["inputs_ready_arrays"], 0)
            self.assertEqual(report["estimates"], 0)
            self.assertEqual(set(report["localization_statuses"]), {"not_implemented"})
            self.assertEqual(len((result / "estimates.csv").read_text().splitlines()), 1)
            self.assertFalse((result / "scatter.png").exists())
            self.assertTrue((result / "bag/metadata.yaml").is_file())


if __name__ == "__main__":
    unittest.main()
