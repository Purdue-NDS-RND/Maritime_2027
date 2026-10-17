#!/usr/bin/env python3
"""Live dual gate check: each RGB-D stream, mount TF, and visible ArUco IDs."""
import argparse
import json
import math
import time

import cv2
from cv_bridge import CvBridge
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image
from tf2_msgs.msg import TFMessage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--camera-only', action='store_true', help='Skip gate marker visibility checks in worlds without buoys')
    args = parser.parse_args()
    rclpy.init(args=[])
    node = Node('dual_camera_smoke')
    stamps = {camera: [set(), set(), set()] for camera in ('camera_0', 'camera_1')}
    frames, transforms, markers = {}, {}, {camera: set() for camera in stamps}
    bridge = CvBridge()
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    errors = []

    def receive(camera, kind, message):
        stamp = message.header.stamp.sec * 1_000_000_000 + message.header.stamp.nanosec
        stamps[camera][kind].add(stamp)
        frames[camera, kind] = message.header.frame_id
        if message.header.frame_id != f'{camera}_optical_frame':
            errors.append(f'{camera}: wrong frame {message.header.frame_id}')
        if message.width != 1280 or message.height != 720:
            errors.append(f'{camera}: wrong dimensions')
        if kind == 0 and len(stamps[camera][0]) % 5 == 0:
            image = bridge.imgmsg_to_cv2(message, desired_encoding='bgr8')
            _, ids, _ = cv2.aruco.detectMarkers(image, dictionary)
            if ids is not None:
                markers[camera].update(map(int, ids.flatten()))
        if kind == 1 and message.encoding != '32FC1':
            errors.append(f'{camera}: wrong depth encoding')
        if kind == 2 and not (message.k[0] > 0 and message.k[4] > 0):
            errors.append(f'{camera}: invalid intrinsics')

    for camera in stamps:
        for kind, (message_type, suffix) in enumerate(((Image, 'color/image_raw'),
                (Image, 'depth/image_rect_raw'), (CameraInfo, 'color/camera_info'))):
            node.create_subscription(message_type, f'/sensors/{camera}/{suffix}',
                lambda msg, camera=camera, kind=kind: receive(camera, kind, msg), qos_profile_sensor_data)
    node.create_subscription(TFMessage, '/tf_static',
        lambda msg: transforms.update({tf.child_frame_id: tf for tf in msg.transforms}),
        QoSProfile(depth=100, durability=DurabilityPolicy.TRANSIENT_LOCAL))
    try:
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.05)
        result = {}
        for camera, streams in stamps.items():
            common = set.intersection(*streams)
            duration = (max(common)-min(common))/1e9 if common else 0.
            hz = (len(common)-1)/duration if duration else 0.
            assert hz >= 8., (camera, hz, [len(s) for s in streams])
            assert len(common) >= 50, (camera, len(common))
            mount = transforms[f'{camera}_link']
            optical = transforms[f'{camera}_optical_frame']
            assert mount.header.frame_id == 'base_link'
            assert optical.header.frame_id == f'{camera}_link'
            sign = -1 if camera == 'camera_0' else 1
            t, q = mount.transform.translation, mount.transform.rotation
            assert abs(t.x-.35) < 1e-6 and abs(t.y-sign*.1) < 1e-6 and abs(t.z-.4) < 1e-6
            yaw = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
            assert abs(yaw-sign*math.pi/4) < 1e-6, (camera, yaw)
            expected_marker = 1 if camera == 'camera_0' else 2
            if not args.camera_only:
                assert expected_marker in markers[camera], (camera, markers[camera])
            result[camera] = dict(exact_triples=len(common), rate_hz=hz, visible_ids=sorted(markers[camera]), yaw_rad=yaw)
        assert not errors, errors[:10]
        print(json.dumps(dict(passed=True, cameras=result), indent=2))
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
