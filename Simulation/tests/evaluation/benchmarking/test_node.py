"""Real ROS transport and the latest-pending-image worker policy."""

import threading
import time
import unittest

from cv_bridge import CvBridge
import numpy as np
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2DArray

from maritime_perception.node import ArucoDetectorNode
from test_perception import scene


class NodeTests(unittest.TestCase):
    def setUp(self):
        rclpy.init(args=["--ros-args", "-r", "__ns:=/perception/test", "-p", "publish_debug_image:=true"])
        self.detector = ArucoDetectorNode()
        self.probe = Node("probe")
        self.executor = SingleThreadedExecutor()
        self.executor.add_node(self.detector)
        self.executor.add_node(self.probe)
        self.results, self.debug = [], []
        self.subscription = self.probe.create_subscription(
            Detection2DArray, "/perception/test/detections", self.results.append, qos_profile_sensor_data)
        self.debug_subscription = self.probe.create_subscription(
            Image, "/perception/test/debug/image", self.debug.append, qos_profile_sensor_data)
        self.publisher = self.probe.create_publisher(Image, "/perception/test/image", qos_profile_sensor_data)
        self.wait_for(lambda: self.publisher.get_subscription_count() == 1
                      and self.detector.box_publisher.get_subscription_count() == 1
                      and self.detector.debug_publisher.get_subscription_count() == 1)

    def tearDown(self):
        self.detector.destroy_node()
        self.probe.destroy_node()
        self.executor.shutdown()
        rclpy.shutdown()

    def wait_for(self, condition, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not condition():
            self.executor.spin_once(timeout_sec=0.02)
        self.assertTrue(condition(), "Timed out waiting for ROS/worker result")

    def image(self, stamp, blank=False):
        image = np.full((180, 420, 3), 255, np.uint8) if blank else scene()
        message = CvBridge().cv2_to_imgmsg(image, encoding="bgr8")
        message.header.frame_id = "fixture_optical"
        message.header.stamp.sec, message.header.stamp.nanosec = stamp, 678
        return message

    def test_real_ros_boxes_empty_observations_headers_and_conversion_failure(self):
        for stamp, blank in ((1, False), (2, True)):
            message = self.image(stamp, blank)
            self.publisher.publish(message)
            self.wait_for(lambda: len(self.results) == stamp and len(self.debug) == stamp)
            self.assertEqual(self.results[-1].header, message.header)
            self.assertEqual(self.debug[-1].header, message.header)
        self.assertEqual(len(self.results[0].detections), 1)
        self.assertEqual(self.results[1].detections, [])
        invalid = self.image(3)
        invalid.encoding = "invalid_encoding"
        self.publisher.publish(invalid)
        self.wait_for(lambda: self.detector.failed == 1)
        self.assertEqual(len(self.results), 2)

    def test_only_latest_pending_image_is_processed(self):
        entered, release = threading.Event(), threading.Event()
        original = self.detector.detector.detect

        def block_first(image):
            if not entered.is_set():
                entered.set()
                if not release.wait(5):
                    raise TimeoutError("Worker test not released")
            return original(image)

        self.detector.detector.detect = block_first
        try:
            self.detector.receive(self.image(10))
            self.wait_for(entered.is_set)
            self.detector.receive(self.image(11))
            self.detector.receive(self.image(12))
            release.set()
            self.wait_for(lambda: self.detector.processed == 2)
            self.wait_for(lambda: len(self.results) >= 1)
            # Inspect ROS results too, allowing for best-effort delivery semantics.
            self.assertTrue(all(item.header.stamp.sec in (10, 12) for item in self.results))
            self.assertEqual(self.detector.replaced, 1)
            self.assertEqual(self.detector.received, 3)
            self.assertEqual(self.detector.failed, 0)
        finally:
            release.set()


if __name__ == "__main__":
    unittest.main()
