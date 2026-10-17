"""Explicit dual RGB mission node. No vehicle transport or simulator inputs."""
import json
import math
import time
from collections import deque

import numpy as np
from cv_bridge import CvBridge
from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import Odometry
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import String
from tf2_ros import Buffer, TransformListener, TransformException
from rclpy.time import Time

from maritime_localization.geometry import rigid_transform
from maritime_navigation.mission import Mission, guidance
from maritime_navigation.vision import marker_positions


class Navigator(Node):
    def __init__(self):
        super().__init__('gate_slalom_navigator')
        self.cameras = self.declare_parameter('cameras', ['camera_0', 'camera_1']).value
        self.size = self.declare_parameter('marker_size_m', .5).value
        self.mission = Mission(turns=self.declare_parameter('slalom_turns', 4).value)
        if (not self.cameras or len(set(self.cameras)) != len(self.cameras)
                or not math.isfinite(self.size) or self.size <= 0):
            raise ValueError('Invalid cameras or marker size')
        self.bridge = CvBridge()
        self.tf = Buffer()
        self.listener = TransformListener(self.tf, self)
        self.calibration = {}
        self.pose = None
        self.poses = deque(maxlen=200)
        self.images = {c: 0. for c in self.cameras}
        self.counts = {c: 0 for c in self.cameras}
        self.pending = {}
        self.start = time.monotonic()
        self.pose_time = 0.
        self.vision_time = 0.
        self.command = self.create_publisher(TwistStamped, '/navigation/velocity', 10)
        self.status = self.create_publisher(String, '/navigation/status', 10)
        self.create_subscription(Odometry, 'vessel/odometry', self.on_pose, qos_profile_sensor_data)
        for camera in self.cameras:
            self.create_subscription(CameraInfo, f'/sensors/{camera}/color/camera_info',
                                     lambda m, c=camera: self.calibration.update({c: m}), qos_profile_sensor_data)
            self.create_subscription(Image, f'/sensors/{camera}/color/image_raw',
                                     lambda m, c=camera: self.pending.update({c: (m, time.monotonic())}), qos_profile_sensor_data)
        self.create_timer(.1, self.tick)

    def on_pose(self, msg):
        if msg.header.frame_id != 'map' or msg.child_frame_id != 'base_link':
            return
        p = msg.pose.pose
        try:
            transform = rigid_transform(p.position, p.orientation)
        except ValueError:
            return
        self.pose = transform
        self.pose_time = time.monotonic()
        # Receipt times intentionally pair live inputs; no claim of sensor-time
        # alignment or GPS independence is made by this bootstrap.
        self.poses.append((self.pose_time, transform))

    def process(self, camera, msg, arrival):
        calibration = self.calibration.get(camera)
        if calibration is None or calibration.header.frame_id != msg.header.frame_id or not self.poses:
            return
        pose_time, pose = min(self.poses, key=lambda pair: abs(pair[0]-arrival))
        if abs(pose_time-arrival) > .25 or time.monotonic()-arrival > .5:
            return
        try:
            mount = self.tf.lookup_transform('base_link', msg.header.frame_id, Time()).transform
            transform = pose @ rigid_transform(mount.translation, mount.rotation)
            image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            points = marker_positions(image, np.array(calibration.k).reshape(3, 3), np.array(calibration.d), self.size)
        except (TransformException, ValueError) as error:
            self.get_logger().warning(str(error))
            return
        self.images[camera] = arrival
        for category, point in points:
            world = transform @ np.append(point, 1.)
            self.mission.observe(category, float(world[0]), float(world[1]), arrival)
            self.counts[camera] += 1
            self.vision_time = arrival

    def tick(self):
        for camera, (msg, arrival) in list(self.pending.items()):
            del self.pending[camera]
            self.process(camera, msg, arrival)
        now = time.monotonic()
        healthy = (self.pose is not None and now-self.pose_time < .5
                   and all(now-t < 1.5 for t in self.images.values()))
        target = None
        reason = 'waiting_for_inputs'
        if healthy:
            x, y = self.pose[:2, 3]
            yaw = math.atan2(self.pose[1, 0], self.pose[0, 0])
            if now-self.vision_time < 8 or self.mission.clearing_gate(x, y, yaw):
                target = self.mission.update(float(x), float(y), yaw, now)
                reason = self.mission.stage
            else:
                reason = 'vision_timeout'
        message = TwistStamped()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = 'map'
        if target:
            vx, vy, rate = guidance(x, y, yaw, target)
            message.twist.linear.x, message.twist.linear.y = vx, vy
            message.twist.angular.z = rate
        self.command.publish(message)
        self.status.publish(String(data=json.dumps(dict(stage=self.mission.stage, reason=reason,
            target=target, events=self.mission.events, observations=self.counts,
            landmarks=[vars(b) for b in self.mission.landmarks], elapsed=now-self.start))))


def main(args=None):
    rclpy.init(args=args)
    node = Navigator()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        for _ in range(5 if rclpy.ok() else 0):
            message = TwistStamped()
            message.header.frame_id = 'map'
            node.command.publish(message)
        node.destroy_node()
        rclpy.try_shutdown()
