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
from sensor_msgs.msg import CameraInfo, TimeReference
from tf2_msgs.msg import TFMessage
import yaml

import pipeline
from test_perception import scene


def fixture(dataset, recover_clock=False):
    dataset.mkdir()
    (dataset / "dataset.json").write_text(json.dumps(dict(name="fixture", status="complete", capture_domain=0)))
    (dataset / "quality.json").write_text(json.dumps(dict(passed=True)))
    qos = {"/tf_static": dict(reliability="reliable", durability="transient_local", history="keep_last", depth=100)}
    (dataset / "qos.yaml").write_text(yaml.safe_dump(qos))
    bridge = CvBridge()
    image = bridge.cv2_to_imgmsg(scene(), encoding="bgr8")
    info = CameraInfo(width=420, height=180)
    info.k = [200., 0., 210., 0., 200., 90., 0., 0., 1.]
    for message in (image, info):
        message.header.frame_id = "camera_optical"
    pose = Odometry()
    pose.header.frame_id, pose.child_frame_id = "map", "base_link"
    pose.pose.pose.orientation.w = 1.
    transform = TransformStamped()
    transform.header.frame_id, transform.child_frame_id = "base_link", "camera_optical"
    transform.transform.rotation.w = 1.
    # Real optical convention: optical Z -> boat X, optical X -> boat -Y.
    transform.transform.rotation.x, transform.transform.rotation.y = -.5, .5
    transform.transform.rotation.z, transform.transform.rotation.w = -.5, .5
    static = TFMessage(transforms=[transform])
    types = {pipeline.IMAGE: "sensor_msgs/msg/Image",
             pipeline.INFO: "sensor_msgs/msg/CameraInfo", pipeline.POSE: "nav_msgs/msg/Odometry",
             "/tf_static": "tf2_msgs/msg/TFMessage"}
    if recover_clock:
        types["/mavros/time_reference"] = "sensor_msgs/msg/TimeReference"
    writer = rosbag2_py.SequentialWriter()
    writer.open(rosbag2_py.StorageOptions(uri=str(dataset / "bag"), storage_id="mcap"),
                rosbag2_py.ConverterOptions("cdr", "cdr"))
    for index, (topic, message_type) in enumerate(types.items()):
        writer.create_topic(rosbag2_py.TopicMetadata(id=index, name=topic, type=message_type, serialization_format="cdr"))
    writer.write("/tf_static", serialize_message(static), 10_000_000_000)
    writer.create_topic(rosbag2_py.TopicMetadata(id=10, name='/blueboat/ground_truth/buoy',
        type='nav_msgs/msg/Odometry', serialization_format='cdr'))
    false_truth = Odometry()
    false_truth.pose.pose.position.x = 99999.
    writer.write('/blueboat/ground_truth/buoy', serialize_message(false_truth), 10_000_000_000)
    for index in range(60):
        stamp = 10_000_000_000 + index * 100_000_000
        # A fixed target seen from translated cameras, with matching RGB and pose.
        image = bridge.cv2_to_imgmsg(cv2.warpAffine(scene(), np.float32([[1, 0, 4*index], [0, 1, 0]]),
                                                   (420, 180), borderValue=(255, 255, 255)), encoding="bgr8")
        image.header.frame_id = "camera_optical"
        pose.pose.pose.position.y = index * .1
        for topic, message in ((pipeline.POSE, pose), (pipeline.INFO, info),
                               (pipeline.IMAGE, image)):
            if topic not in types:
                continue
            message.header.stamp.sec = 10 + index // 10
            message.header.stamp.nanosec = (index % 10) * 100_000_000
            if recover_clock and topic == pipeline.POSE:
                source_stamp = 1_790_000_000_000_000_000 + round(stamp*1.4)
                message.header.stamp.sec, message.header.stamp.nanosec = divmod(source_stamp, 1_000_000_000)
                reference = TimeReference(source='fcu')
                reference.header.stamp = message.header.stamp
                reference.time_ref.sec, reference.time_ref.nanosec = divmod(
                    1_789_000_000_000_000_000+stamp, 1_000_000_000)
                writer.write('/mavros/time_reference', serialize_message(reference), stamp)
            writer.write(topic, serialize_message(message), stamp)
    del writer


class PipelineTests(unittest.TestCase):
    def test_removed_methods_are_rejected_before_reading_a_recording(self):
        for method in ('depth', 'triangulation', 'rgb_mapping'):
            with self.subTest(method=method), self.assertRaisesRegex(ValueError, 'Only bearing_ekf'):
                pipeline.run(Path('/unused-dataset'), Path('/unused-output'), method, 1.)

    def check_method(self, method, recover_clock=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture(root / "dataset", recover_clock=recover_clock)
            result = root / "result"
            try:
                report = pipeline.run(root / "dataset", result, method, 1.)
            except Exception:
                for log in sorted(result.glob("*.log")):
                    print(f"{log.name}:\n{log.read_text()}")
                raise
            self.assertEqual(report["status"], "complete")
            self.assertEqual(report["method"], "bearing_ekf")
            self.assertGreater(report["inputs_ready_arrays"], 0)
            self.assertGreater(report["estimates"], 0)
            self.assertIn("ok", report["localization_statuses"])
            self.assertNotIn("error", report["localization_statuses"])
            self.assertGreater(len((result / "estimates.csv").read_text().splitlines()), 1)
            self.assertTrue((result / "scatter.png").exists())
            with (result / "estimates.csv").open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual({row["method"] for row in rows}, {"bearing_ekf"})
            # Check the known target in the acquisition-time reference frame.
            expected = (5., 3.2625)
            self.assertAlmostEqual(statistics.median(float(row["x_m"]) for row in rows), expected[0], delta=.25)
            self.assertAlmostEqual(statistics.median(float(row["y_m"]) for row in rows), expected[1], delta=.05)
            if recover_clock:
                self.assertEqual(report['pose_clock']['mode'], 'recorded-reference')
                self.assertGreater(report['clock_aligned_poses'], 0)
                self.assertTrue((result/'clock-alignment.json').exists())
                self.assertTrue((result/'pose-clock.csv').exists())
            self.assertNotIn("/sensors/camera_0/depth/image_rect_raw", report["input_topics"])
            self.assertFalse(any('ground_truth' in topic for topic in report['input_topics']))
            final = json.loads((result / "final_map.json").read_text())
            track, = final["tracks"]
            self.assertEqual(track["lifecycle"], "confirmed")
            covariance = np.array(track['covariance']).reshape(2, 2)
            np.testing.assert_allclose(covariance, covariance.T)
            self.assertGreater(np.linalg.eigvalsh(covariance).min(), 0.)
            self.assertEqual(track['source_cameras'], ['camera_0'])
            self.assertGreater(track['last_update_ns'], track['first_seen_ns'])
            self.assertAlmostEqual(track['x_m'], 5., delta=.25)
            self.assertAlmostEqual(track['y_m'], 3.2625, delta=.05)
            self.assertGreater(track["confirmation_evidence"], 2)
            self.assertEqual(len({row["track_id"] for row in rows}), 1)
            self.assertTrue((result / "map_history.csv").exists())
            self.assertTrue((result / "observations.csv").exists())
            self.assertTrue(all(row["depth_timestamp_ns"] == "0" for row in rows))
            self.assertTrue((result / "bag/metadata.yaml").is_file())

    def test_rgb_map_recovers_different_rate_pose_clock(self):
        self.check_method("bearing_ekf", recover_clock=True)

    def test_rgb_map_from_bag_with_no_depth_topic(self):
        self.check_method("bearing_ekf")



if __name__ == "__main__":
    unittest.main()
