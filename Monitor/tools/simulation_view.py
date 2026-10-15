#!/usr/bin/env python3
"""Monitor-only Gazebo truth visualization. Never publishes public TF."""
import math
import re
import time
from collections import deque
from pathlib import Path

import yaml

import numpy as np
import rclpy
from geometry_msgs.msg import Point, TransformStamped
from nav_msgs.msg import Odometry
from rclpy.clock import Clock, ClockType
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import ColorRGBA
from tf2_msgs.msg import TFMessage
from visualization_msgs.msg import Marker, MarkerArray

ROOT = '/monitor/simulation'
BUOY = re.compile(r'^/blueboat/ground_truth/([a-z][a-z0-9_]*)/odometry$')


def image_geometry(info, width, height, distance=1.5):
    """Pixel edges at a chosen optical depth, using calibrated intrinsics."""
    fx, fy, cx, cy = info.k[0], info.k[4], info.k[2], info.k[5]
    if fx <= 0 or fy <= 0 or not all(math.isfinite(v) for v in (fx, fy, cx, cy)):
        raise ValueError('invalid camera intrinsics')
    x = (np.linspace(0, info.width, width + 1) - cx) * distance / fx
    y = (np.linspace(0, info.height, height + 1) - cy) * distance / fy
    return x, y


class SimulationView(Node):
    def __init__(self):
        super().__init__('monitor_simulation_view', parameter_overrides=[
            rclpy.parameter.Parameter('use_sim_time', value=True)])
        self.tf = self.create_publisher(TFMessage, ROOT + '/tf', 10)
        static_qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.static = self.create_publisher(TFMessage, ROOT + '/tf_static', static_qos)
        self.markers = self.create_publisher(MarkerArray, ROOT + '/markers', 2)
        self.subscriptions_by_topic = {}
        self.info = None
        self.last_image = None
        self.info_arrival = None
        self.image_arrivals = deque(maxlen=120)
        self.image_encoding = "waiting"
        self.publish_camera_mount()
        # RViz clears its TF buffer when simulation time jumps backwards.
        self.create_timer(1.0, lambda: self.static.publish(self.camera_tf))
        self.create_subscription(Odometry, '/blueboat/ground_truth/odometry',
                                 lambda msg: self.on_pose(msg, 'base_link'), 10)
        self.create_subscription(CameraInfo, '/sensors/camera_0/color/camera_info',
                                 self.on_camera_info, qos_profile_sensor_data)
        self.create_subscription(Image, '/sensors/camera_0/color/image_raw',
                                 self.on_image, qos_profile_sensor_data)
        self.create_timer(1.0, self.discover)
        self.create_timer(0.25, self.draw_image)
        # Arrival health must still update when simulation time is paused.
        self.wall_clock = Clock(clock_type=ClockType.STEADY_TIME)
        self.create_timer(0.5, self.draw_camera_status, clock=self.wall_clock)
        self.get_logger().info('Simulation truth view active on private /monitor/simulation topics')

    def on_camera_info(self, msg):
        self.info = msg
        self.info_arrival = time.monotonic()

    def on_image(self, msg):
        self.last_image = msg
        self.image_encoding = msg.encoding
        self.image_arrivals.append(time.monotonic())

    def camera_status(self, now):
        """Summarize live CameraInfo and wall-clock arrivals for the scene label."""
        while self.image_arrivals and now - self.image_arrivals[0] > 2.0:
            self.image_arrivals.popleft()
        image_live = bool(self.image_arrivals)
        info_live = self.info_arrival is not None and now - self.info_arrival <= 2.0
        arrivals = self.image_arrivals
        hz = ((len(arrivals) - 1) / (arrivals[-1] - arrivals[0])
              if len(arrivals) > 1 and arrivals[-1] > arrivals[0] else 0.0)
        state = f'RGB {hz:.1f} Hz' if image_live else 'RGB STALE / waiting'
        state += ' | info receiving' if info_live else ' | info STALE / waiting'
        info = self.info
        if info is None:
            return 'camera_0 | waiting for CameraInfo\n' + state, False
        try:
            image_geometry(info, 1, 1)
            if info.width <= 0 or info.height <= 0 or info.header.frame_id != 'camera_0_optical_frame':
                raise ValueError('invalid dimensions or optical frame')
        except ValueError:
            return 'camera_0 | invalid CameraInfo\n' + state, False
        fx, fy, cx, cy = info.k[0], info.k[4], info.k[2], info.k[5]
        hfov = math.degrees(math.atan2(cx, fx) + math.atan2(info.width - cx, fx))
        vfov = math.degrees(math.atan2(cy, fy) + math.atan2(info.height - cy, fy))
        text = (f'camera_0 | {info.width}x{info.height} {self.image_encoding}\n'
                f'fx {fx:.1f} fy {fy:.1f} | cx {cx:.1f} cy {cy:.1f}\n'
                f'FoV {hfov:.1f} x {vfov:.1f} deg | {info.distortion_model}\n{state}')
        return text, image_live and info_live

    def draw_camera_status(self):
        text, healthy = self.camera_status(time.monotonic())
        label = self.marker('base_link', 'camera/calibration', Marker.TEXT_VIEW_FACING,
                            rclpy.time.Time().to_msg())
        label.text = text
        label.pose.position.x = -1.5
        label.pose.position.y, label.pose.position.z = -2.5, 1.5
        label.scale.z = 0.25
        label.color = (ColorRGBA(r=0.8, g=1.0, b=0.8, a=1.0) if healthy
                       else ColorRGBA(r=1.0, g=0.7, b=0.1, a=1.0))
        self.markers.publish(MarkerArray(markers=[label]))

    def publish_camera_mount(self):
        # Read the Adapter's canonical calibration contract, mounted read-only by
        # rviz-sim. Do not depend on late-joining the public static-TF writers.
        contract = yaml.safe_load(Path('/opt/monitor/simulation-camera.yaml').read_text())
        camera = contract['cameras']['camera_0']
        if contract['environment'] != 'simulation' or camera['mount_parent_frame'] != 'base_link':
            raise ValueError('unexpected simulation camera mount contract')
        mount = TransformStamped()
        mount.header.frame_id, mount.child_frame_id = 'base_link', 'camera_0_link'
        xyz = camera['mount_xyz_m']
        rpy = camera['mount_rpy_rad']
        if len(xyz) != 3 or len(rpy) != 3 or not all(math.isfinite(v) for v in xyz + rpy):
            raise ValueError('invalid camera mount pose')
        mount.transform.translation.x, mount.transform.translation.y, mount.transform.translation.z = map(float, xyz)
        roll, pitch, yaw = (v / 2 for v in rpy)
        cr, sr, cp, sp, cy, sy = math.cos(roll), math.sin(roll), math.cos(pitch), math.sin(pitch), math.cos(yaw), math.sin(yaw)
        q = mount.transform.rotation
        q.x, q.y = sr*cp*cy-cr*sp*sy, cr*sp*cy+sr*cp*sy
        q.z, q.w = cr*cp*sy-sr*sp*cy, cr*cp*cy+sr*sp*sy
        optical = TransformStamped()
        optical.header.frame_id, optical.child_frame_id = 'camera_0_link', 'camera_0_optical_frame'
        q = optical.transform.rotation
        q.x, q.y, q.z, q.w = -.5, .5, -.5, .5
        self.camera_tf = TFMessage(transforms=[mount, optical])
        self.static.publish(self.camera_tf)

    def discover(self):
        for topic, types in self.get_topic_names_and_types():
            match = BUOY.fullmatch(topic)
            if match and 'nav_msgs/msg/Odometry' in types and topic not in self.subscriptions_by_topic:
                frame = 'buoy/' + match[1]
                self.subscriptions_by_topic[topic] = self.create_subscription(
                    Odometry, topic, lambda msg, frame=frame: self.on_pose(msg, frame), 10)
                self.get_logger().info(f'Discovered {frame}')

    def marker(self, frame, name, marker_type, stamp, marker_id=0):
        marker = Marker()
        marker.header.frame_id = frame
        marker.header.stamp = stamp
        marker.ns, marker.id, marker.type = name, marker_id, marker_type
        marker.pose.orientation.w = 1.0
        marker.frame_locked = True
        marker.color = ColorRGBA(r=0.2, g=0.8, b=1.0, a=1.0)
        marker.lifetime.sec = 2
        return marker

    def on_pose(self, msg, frame):
        # Both sources explicitly use world/odom aligned to Gazebo origin.
        if msg.header.frame_id not in ('world', 'odom'):
            self.get_logger().error(f'Unexpected truth frame: {msg.header.frame_id}')
            return
        transform = TransformStamped()
        transform.header = msg.header
        transform.header.frame_id = 'world'
        transform.child_frame_id = frame
        pose = msg.pose.pose
        transform.transform.translation.x = pose.position.x
        transform.transform.translation.y = pose.position.y
        transform.transform.translation.z = pose.position.z
        transform.transform.rotation = pose.orientation
        self.tf.publish(TFMessage(transforms=[transform]))
        boat = frame == 'base_link'
        body = self.marker(frame, 'entities/' + frame, Marker.CUBE if boat else Marker.CYLINDER, msg.header.stamp)
        body.scale.x, body.scale.y, body.scale.z = (1.2, 0.8, 0.25) if boat else (0.48, 0.48, 0.76)
        body.pose.position.z = 0.0 if boat else 0.38
        if not boat:
            name = frame.lower()
            rgb = next((rgb for color, rgb in [('red', (1., .1, .1)), ('green', (.1, 1., .1)),
                                                ('blue', (.1, .3, 1.))] if color in name), (.9, .9, .9))
            body.color = ColorRGBA(r=rgb[0], g=rgb[1], b=rgb[2], a=1.)
        label = self.marker(frame, body.ns, Marker.TEXT_VIEW_FACING, msg.header.stamp, 1)
        label.text = 'Boat' if boat else frame.removeprefix('buoy/')
        label.pose.position.z, label.scale.z = 1.25, 0.25
        label.color = ColorRGBA(r=1., g=1., b=1., a=1.)
        heading = self.marker(frame, body.ns, Marker.ARROW, msg.header.stamp, 2)
        heading.scale.x, heading.scale.y, heading.scale.z = 1., .08, .08
        heading.pose.position.z = .2 if boat else .8
        self.markers.publish(MarkerArray(markers=[body, label, heading]))

    def draw_image(self):
        msg, info = self.last_image, self.info
        if msg is None or info is None:
            return
        self.last_image = None
        if (msg.header.frame_id != 'camera_0_optical_frame' or
                info.header.frame_id != msg.header.frame_id or
                (msg.width, msg.height) != (info.width, info.height) or
                msg.encoding not in ('rgb8', 'bgr8')):
            self.get_logger().warning('Image plane needs matching RGB image and camera calibration')
            return
        width, height = 80, 45
        try:
            x, y = image_geometry(info, width, height)
            rows = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.step)
            pixels = rows[:, :msg.width * 3].reshape(msg.height, msg.width, 3)
            pixels = pixels[np.minimum((np.arange(height) + .5) * msg.height / height, msg.height - 1).astype(int)[:, None],
                            np.minimum((np.arange(width) + .5) * msg.width / width, msg.width - 1).astype(int)]
        except ValueError as error:
            self.get_logger().warning(str(error))
            return
        if msg.encoding == 'bgr8':
            pixels = pixels[:, :, ::-1]
        plane = self.marker(msg.header.frame_id, 'camera/image_plane', Marker.TRIANGLE_LIST, msg.header.stamp)
        plane.scale.x = plane.scale.y = plane.scale.z = 1.
        for row in range(height):
            for col in range(width):
                color = ColorRGBA(r=float(pixels[row, col, 0]) / 255.,
                                  g=float(pixels[row, col, 1]) / 255., b=float(pixels[row, col, 2]) / 255., a=1.)
                for dx, dy in ((0, 0), (1, 0), (1, 1), (0, 0), (1, 1), (0, 1)):
                    plane.points.append(Point(x=float(x[col + dx]), y=float(y[row + dy]), z=1.5))
                    plane.colors.append(color)
        outline = self.marker(msg.header.frame_id, 'camera/frustum', Marker.LINE_LIST, msg.header.stamp)
        outline.scale.x = .015
        corners = [Point(x=float(x[c]), y=float(y[r]), z=1.5) for c, r in ((0, 0), (-1, 0), (-1, -1), (0, -1))]
        for index, corner in enumerate(corners):
            outline.points.extend([Point(), corner, corner, corners[(index + 1) % 4]])
        self.markers.publish(MarkerArray(markers=[plane, outline]))


def main():
    rclpy.init()
    node = SimulationView()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
