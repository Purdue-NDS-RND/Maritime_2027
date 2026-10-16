"""Exercise the ROS wrapper with synthetic inputs, not positioning algorithms."""

import math
from pathlib import Path
import tempfile
import unittest

from cv_bridge import CvBridge
from geometry_msgs.msg import TransformStamped
from maritime_interfaces.msg import BuoyEstimateArray
from nav_msgs.msg import Odometry
import numpy as np
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.serialization import serialize_message
import rosbag2_py
from sensor_msgs.msg import CameraInfo

from maritime_localization.interfaces import PositionEstimate
from maritime_localization.node import BuoyLocalizerNode
from maritime_perception.aruco import ArucoBoxDetector
from maritime_perception.messages import detection_array
from results import export_results
from test_perception import scene


class LocalizationTests(unittest.TestCase):
    def start(self, method):
        rclpy.init(args=["--ros-args", "-p", f"method:={method}"])
        self.localizer = BuoyLocalizerNode()
        self.probe = Node("localizer_test_probe")
        self.executor = SingleThreadedExecutor()
        self.executor.add_node(self.localizer)
        self.executor.add_node(self.probe)
        self.outputs = []
        self.subscription = self.probe.create_subscription(BuoyEstimateArray, "/buoys", self.outputs.append,
                                                           qos_profile_sensor_data)
        self.addCleanup(self.close)
        pose = Odometry()
        pose.header.frame_id, pose.child_frame_id = "map", "base_link"
        pose.header.stamp.sec = 1_790_000_000  # Deliberately a different clock domain.
        pose.pose.pose.position.x, pose.pose.pose.position.y = 10.0, 20.0
        pose.pose.pose.orientation.w = pose.pose.pose.orientation.z = math.sqrt(0.5)
        calibration = CameraInfo(width=420, height=180)
        calibration.header.frame_id = "camera_optical"
        calibration.k = [200., 0., 210., 0., 200., 90., 0., 0., 1.]
        self.localizer.receive_pose(pose)
        self.localizer.receive_calibration(calibration)
        transform = TransformStamped()
        transform.header.frame_id, transform.child_frame_id = "base_link", "camera_optical"
        transform.transform.translation.x = 1.
        transform.transform.rotation.w = 1.
        self.localizer.transforms.set_transform_static(transform, "fixture")
        depth = CvBridge().cv2_to_imgmsg(np.full((180, 420), 5., np.float32), encoding="32FC1")
        depth.header.frame_id, depth.header.stamp.sec = "camera_optical", 3
        if method == "depth":
            self.localizer.receive_depth(depth)
        self.message = detection_array(depth.header, ArucoBoxDetector().detect(scene()))

    def close(self):
        self.localizer.destroy_node()
        self.probe.destroy_node()
        self.executor.shutdown()
        rclpy.shutdown()

    def test_depth_assembly_uses_latest_pose_and_camera_mount_without_clock_alignment(self):
        self.start("depth")
        observation = self.localizer.observation(self.message)
        self.assertEqual(observation.timestamp_ns, 3_000_000_000)
        np.testing.assert_allclose(observation.camera_to_reference[:3, 3], [10, 21, 0], atol=1e-8)
        self.assertEqual(observation.depth_m.shape, (180, 420))
        self.assertEqual(observation.boxes[0].category, "red")

    def test_triangulation_has_no_depth_subscription_or_depth_input(self):
        self.start("triangulation")
        topics = [subscription.topic_name for subscription in self.localizer.subscriptions_owned]
        self.assertNotIn("/depth", topics)
        self.assertIsNone(self.localizer.observation(self.message).depth_m)

    def test_wrong_pose_frame_is_rejected(self):
        self.start("depth")
        self.localizer.pose.header.frame_id = "different_origin"
        with self.assertRaisesRegex(ValueError, "frame"):
            self.localizer.observation(self.message)

    def test_placeholder_publishes_explicit_status_without_fabricating_points(self):
        self.start("depth")
        # Record the actual message passed to ROS publication without transport timing.
        published = []
        self.localizer.publisher.publish = published.append
        self.localizer.receive(self.message)
        output, = published
        self.assertEqual(output.status, "not_implemented")
        self.assertTrue(output.inputs_ready)
        self.assertEqual(output.estimates, [])
        self.assertEqual(output.header.stamp, self.message.header.stamp)
        self.assertEqual(output.header.frame_id, "map")
        self.assertEqual(output.vessel_pose_stamp.sec, 1_790_000_000)

    def test_invalid_or_three_dimensional_method_results_are_not_published_as_points(self):
        self.start("triangulation")
        published = []
        self.localizer.publisher.publish = published.append
        for frame, position in (("wrong_frame", (1., 2.)), ("map", (float("nan"), 2.)),
                                ("map", (1., 2., 3.))):
            class InvalidMethod:
                def process(self, observation):
                    return [PositionEstimate(observation.timestamp_ns, frame, "red", position)]
            self.localizer.method = InvalidMethod()
            self.localizer.receive(self.message)
            self.assertEqual(published[-1].status, "error")
            self.assertEqual(published[-1].estimates, [])

    def test_estimate_output_and_csv_scatter_round_trip_with_test_double(self):
        self.start("triangulation")
        class TestMethod:
            implemented = True
            def process(self, observation):
                return [PositionEstimate(observation.timestamp_ns, "map", "red", (4.0, 7.0), "track-1")]
        self.localizer.method = TestMethod()
        published = []
        self.localizer.publisher.publish = published.append
        self.localizer.receive(self.message)
        output, = published
        self.assertEqual(output.status, "ok")
        self.assertEqual((output.estimates[0].x, output.estimates[0].y), (4., 7.))
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            writer = rosbag2_py.SequentialWriter()
            writer.open(rosbag2_py.StorageOptions(uri=str(directory / "bag"), storage_id="mcap"),
                        rosbag2_py.ConverterOptions("cdr", "cdr"))
            writer.create_topic(rosbag2_py.TopicMetadata(id=0, name="/localization/buoys",
                type="maritime_interfaces/msg/BuoyEstimateArray", serialization_format="cdr"))
            writer.write("/localization/buoys", serialize_message(output), 3_000_000_000)
            del writer
            summary = export_results(directory)
            self.assertEqual(summary["estimates"], 1)
            self.assertIn("map,triangulation,red,track-1,4.0,7.0", (directory / "estimates.csv").read_text())
            self.assertTrue((directory / "scatter.png").exists())


if __name__ == "__main__":
    unittest.main()
