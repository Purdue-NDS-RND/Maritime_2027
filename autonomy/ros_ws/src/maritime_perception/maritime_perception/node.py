"""ROS wrapper: one active image and at most one replaceable pending image."""

import threading
import sys
import cv2

from cv_bridge import CvBridge
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2DArray

from maritime_perception.aruco import ArucoBoxDetector, annotate
from maritime_perception.messages import detection_array


class ArucoDetectorNode(Node):
    def __init__(self):
        super().__init__("aruco_detector")
        dictionary = self.declare_parameter("aruco_dictionary", "DICT_4X4_50").value
        marker_ids = self.declare_parameter("marker_ids", [0, 1, 2, 3]).value
        categories = self.declare_parameter("marker_categories", ["white", "red", "green", "blue"]).value
        self.debug = self.declare_parameter("publish_debug_image", False).value
        threads = self.declare_parameter("opencv_threads", 1).value
        if not isinstance(threads, int) or not 1 <= threads <= 64:
            raise ValueError('opencv_threads must be 1..64')
        cv2.setNumThreads(threads)
        self.detector = ArucoBoxDetector(dictionary, marker_ids, categories)
        self.bridge = CvBridge()
        qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=1,
                         reliability=ReliabilityPolicy.BEST_EFFORT,
                         durability=DurabilityPolicy.VOLATILE)
        self.box_publisher = self.create_publisher(Detection2DArray, "detections", qos)
        self.debug_publisher = self.create_publisher(Image, "debug/image", qos) if self.debug else None
        self.condition = threading.Condition()
        self.pending = None
        self.stopping = False
        self.received = self.processed = self.replaced = self.failed = 0
        self.subscription = self.create_subscription(Image, "image", self.receive, qos)
        self.worker = threading.Thread(target=self.work, name="aruco-worker", daemon=True)
        self.worker.start()
        self.get_logger().info(f"2D marker boxes only; OpenCV threads={threads}; configuration changes require a restart")

    def receive(self, message):
        with self.condition:
            self.received += 1
            self.replaced += int(self.pending is not None)
            self.pending = message
            self.condition.notify()

    def work(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.stopping or self.pending is not None)
                if self.stopping:
                    return
                message, self.pending = self.pending, None
            try:
                image = self.bridge.imgmsg_to_cv2(message, desired_encoding="bgr8")
                boxes = self.detector.detect(image)
                self.box_publisher.publish(detection_array(message.header, boxes))
                self.processed += 1
                if self.debug_publisher is not None:
                    debug = self.bridge.cv2_to_imgmsg(annotate(image, boxes), encoding="bgr8")
                    debug.header = message.header
                    self.debug_publisher.publish(debug)
            except Exception as error:
                if not self.context.ok():
                    return
                self.failed += 1
                self.get_logger().error(f"Image processing failed; no empty result substituted: {error}")

    def destroy_node(self):
        with self.condition:
            self.stopping = True
            self.condition.notify()
        self.worker.join()
        summary = (f"received={self.received} processed={self.processed} "
                   f"replaced_pending={self.replaced} failures={self.failed}")
        if self.context.ok():
            self.get_logger().info(summary)
        else:
            print(summary, file=sys.stderr, flush=True)
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = ArucoDetectorNode()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
