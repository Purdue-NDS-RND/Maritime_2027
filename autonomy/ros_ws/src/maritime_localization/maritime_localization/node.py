"""ROS input/output wrapper. Algorithms consume ordinary Python observations."""

import math
import sys

from cv_bridge import CvBridge
from maritime_interfaces.msg import BuoyEstimate, BuoyEstimateArray
from nav_msgs.msg import Odometry
import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import CameraInfo, Image
from tf2_ros import Buffer, TransformException, TransformListener
from vision_msgs.msg import Detection2DArray

from maritime_localization.depth import DepthLocalizer
from maritime_localization.interfaces import Observation
from maritime_localization.triangulation import TriangulationLocalizer
from maritime_perception.aruco import BoundingBox


def rigid_transform(position, quaternion):
    """Homogeneous transform from a ROS position/translation and quaternion."""
    xyz = np.array([position.x, position.y, position.z], dtype=float)
    q = np.array([quaternion.x, quaternion.y, quaternion.z, quaternion.w], dtype=float)
    norm = np.linalg.norm(q)
    if not np.isfinite(xyz).all() or not np.isfinite(q).all() or norm < 1e-12:
        raise ValueError("Pose must have finite coordinates and a nonzero quaternion")
    x, y, z, w = q / norm
    matrix = np.eye(4)
    matrix[:3, :3] = [
        [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
        [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
        [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)],
    ]
    matrix[:3, 3] = xyz
    return matrix


class BuoyLocalizerNode(Node):
    def __init__(self):
        super().__init__("buoy_localizer")
        self.method_name = self.declare_parameter("method", "depth").value
        methods = {"depth": DepthLocalizer, "triangulation": TriangulationLocalizer}
        if self.method_name not in methods:
            raise ValueError("method must be depth or triangulation")
        self.method = methods[self.method_name]()
        self.method.reset()
        self.reference_frame = self.declare_parameter("reference_frame", "map").value
        self.body_frame = self.declare_parameter("body_frame", "base_link").value
        self.pose = self.calibration = self.depth = None
        self.received = self.ready = self.errors = 0
        self.bridge = CvBridge()
        self.transforms = Buffer()
        self.listener = TransformListener(self.transforms, self)
        self.publisher = self.create_publisher(BuoyEstimateArray, "buoys", qos_profile_sensor_data)
        self.subscriptions_owned = [
            self.create_subscription(Odometry, "vessel/odometry", self.receive_pose, qos_profile_sensor_data),
            self.create_subscription(CameraInfo, "camera_info", self.receive_calibration, qos_profile_sensor_data),
            self.create_subscription(Detection2DArray, "detections", self.receive, qos_profile_sensor_data),
        ]
        if self.method_name == "depth":
            self.subscriptions_owned.append(self.create_subscription(
                Image, "depth", self.receive_depth, qos_profile_sensor_data))
        self.get_logger().info(f"method={self.method_name}; latest received inputs, no timestamp synchronization; "
                               f"output frame={self.reference_frame}; algorithm implemented={self.method.implemented}")

    def receive_pose(self, message):
        self.pose = message

    def receive_calibration(self, message):
        self.calibration = message

    def receive_depth(self, message):
        self.depth = message

    def observation(self, message):
        if self.pose is None or self.calibration is None:
            raise ValueError("Waiting for vessel odometry and camera calibration")
        if self.pose.header.frame_id != self.reference_frame or self.pose.child_frame_id != self.body_frame:
            raise ValueError("Vessel pose frame/child must match reference_frame/body_frame")
        if self.calibration.header.frame_id != message.header.frame_id:
            raise ValueError("Camera calibration and detections must use the same optical frame")
        matrix = np.asarray(self.calibration.k).reshape(3, 3)
        if not np.isfinite(matrix).all() or matrix[0, 0] <= 0 or matrix[1, 1] <= 0:
            raise ValueError("Camera intrinsics must be finite with positive focal lengths")
        mounting = self.transforms.lookup_transform(self.body_frame, message.header.frame_id, Time()).transform
        pose = self.pose.pose.pose
        camera_to_map = rigid_transform(pose.position, pose.orientation) @ rigid_transform(
            mounting.translation, mounting.rotation)
        depth = None
        if self.method_name == "depth":
            if self.depth is None:
                raise ValueError("Waiting for registered depth")
            if (self.depth.encoding != "32FC1" or self.depth.header.frame_id != message.header.frame_id
                    or (self.depth.width, self.depth.height) != (self.calibration.width, self.calibration.height)):
                raise ValueError("Depth must be registered 32FC1 metres in the calibrated optical frame")
            depth = self.bridge.imgmsg_to_cv2(self.depth, desired_encoding="passthrough")
        boxes = tuple(BoundingBox(-1, detection.results[0].hypothesis.class_id,
                                  detection.bbox.center.position.x, detection.bbox.center.position.y,
                                  detection.bbox.size_x, detection.bbox.size_y)
                      for detection in message.detections if detection.results)
        stamp = message.header.stamp.sec * 1_000_000_000 + message.header.stamp.nanosec
        return Observation(stamp, message.header.frame_id, boxes, matrix,
                           tuple(self.calibration.d), depth, camera_to_map,
                           self.reference_frame, self.calibration.distortion_model)

    def receive(self, message):
        self.received += 1
        output = BuoyEstimateArray(method=self.method_name)
        output.header.stamp = message.header.stamp
        output.header.frame_id = self.reference_frame
        if self.pose is not None:
            output.vessel_pose_stamp = self.pose.header.stamp
        if self.depth is not None:
            output.depth_stamp = self.depth.header.stamp
        try:
            observation = self.observation(message)
            output.inputs_ready = True
            self.ready += 1
        except (ValueError, TransformException) as error:
            output.status = "waiting_for_inputs" if self.method.implemented else "not_implemented"
            output.detail = str(error)
        except Exception as error:
            self.errors += 1
            output.status, output.detail = "error", str(error)
        else:
            try:
                estimates = self.method.process(observation)
                for estimate in estimates:
                    if (estimate.frame_id != self.reference_frame or estimate.timestamp_ns != observation.timestamp_ns
                            or len(estimate.position_m) != 2 or not all(map(math.isfinite, estimate.position_m))):
                        raise ValueError("Estimates must be finite XY points in the output frame at observation time")
                    output.estimates.append(BuoyEstimate(category=estimate.category,
                        track_id=estimate.track_id or "", x=float(estimate.position_m[0]), y=float(estimate.position_m[1])))
                output.status = "ok"
            except NotImplementedError as error:
                output.status, output.detail = "not_implemented", str(error)
            except Exception as error:
                self.errors += 1
                output.estimates.clear()
                output.status, output.detail = "error", str(error)
        self.publisher.publish(output)

    def destroy_node(self):
        summary = f"detections_received={self.received} inputs_ready={self.ready} algorithm_errors={self.errors}"
        if self.context.ok():
            self.get_logger().info(summary)
        else:
            print(summary, file=sys.stderr, flush=True)
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = BuoyLocalizerNode()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
