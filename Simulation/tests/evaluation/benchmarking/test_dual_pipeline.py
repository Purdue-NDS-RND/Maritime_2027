"""Two rendered RGB views of one physical buoy feed one persistent map."""
import json
from pathlib import Path
import tempfile
import unittest

import cv2
from cv_bridge import CvBridge
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
import numpy as np
from rclpy.serialization import serialize_message
import rosbag2_py
from scipy.spatial.transform import Rotation
from sensor_msgs.msg import CameraInfo
from tf2_msgs.msg import TFMessage
import yaml

import pipeline


def fixture(dataset):
    dataset.mkdir()
    (dataset / 'dataset.json').write_text(json.dumps(dict(name='dual-fixture', status='complete', capture_domain=0)))
    (dataset / 'scenario.manifest.json').write_text(json.dumps(dict(boat_model='dual')))
    (dataset / 'quality.json').write_text(json.dumps(dict(passed=True)))
    (dataset / 'qos.yaml').write_text(yaml.safe_dump({'/tf_static': dict(
        reliability='reliable', durability='transient_local', history='keep_last', depth=100)}))
    writer = rosbag2_py.SequentialWriter()
    writer.open(rosbag2_py.StorageOptions(uri=str(dataset / 'bag'), storage_id='mcap'),
                rosbag2_py.ConverterOptions('cdr', 'cdr'))
    types = {pipeline.POSE: 'nav_msgs/msg/Odometry', '/tf_static': 'tf2_msgs/msg/TFMessage'}
    for i in range(2):
        types[f'/sensors/camera_{i}/color/image_raw'] = 'sensor_msgs/msg/Image'
        types[f'/sensors/camera_{i}/color/camera_info'] = 'sensor_msgs/msg/CameraInfo'
    for i, (topic, message_type) in enumerate(types.items()):
        writer.create_topic(rosbag2_py.TopicMetadata(id=i, name=topic, type=message_type, serialization_format='cdr'))
    rotations, origins, transforms = [], [], []
    for i, yaw in enumerate((-np.pi/4, np.pi/4)):
        r = Rotation.from_euler('z', yaw) * Rotation.from_quat([-.5, .5, -.5, .5])
        origin = np.array([.35, -.1 if i == 0 else .1, .4])
        transform = TransformStamped()
        transform.header.frame_id, transform.child_frame_id = 'base_link', f'camera_{i}_optical_frame'
        t, q = transform.transform.translation, transform.transform.rotation
        t.x, t.y, t.z = map(float, origin)
        q.x, q.y, q.z, q.w = map(float, r.as_quat())
        transforms.append(transform)
        rotations.append(r.as_matrix())
        origins.append(origin)
    writer.write('/tf_static', serialize_message(TFMessage(transforms=transforms)), 10_000_000_000)
    marker = cv2.aruco.drawMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), 1, 24)
    bridge = CvBridge()
    for index in range(140):
        stamp = 10_000_000_000 + index * 100_000_000
        boat = np.array([0., -.8 + .02 * index, 0.])
        pose = Odometry()
        pose.header.frame_id, pose.child_frame_id = 'map', 'base_link'
        pose.header.stamp.sec, pose.header.stamp.nanosec = divmod(stamp, 1_000_000_000)
        pose.pose.pose.position.y = float(boat[1])
        pose.pose.pose.orientation.w = 1.
        writer.write(pipeline.POSE, serialize_message(pose), stamp)
        for i in range(2):
            local = rotations[i].T @ (np.array([7., 0., .75]) - boat - origins[i])
            u, v = np.rint([210 + 100*local[0]/local[2], 90 + 100*local[1]/local[2]]).astype(int)
            pixels = np.full((180, 420, 3), 255, dtype=np.uint8)
            pixels[v-12:v+12, u-12:u+12] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
            image = bridge.cv2_to_imgmsg(pixels, encoding='bgr8')
            image.header.frame_id = f'camera_{i}_optical_frame'
            image.header.stamp = pose.header.stamp
            info = CameraInfo(width=420, height=180)
            info.header = image.header
            info.k = [100., 0., 210., 0., 100., 90., 0., 0., 1.]
            for suffix, message in [('image_raw', image), ('camera_info', info)]:
                writer.write(f'/sensors/camera_{i}/color/{suffix}', serialize_message(message), stamp)
    del writer


class DualPipeline(unittest.TestCase):
    def test_both_camera_bearings_reach_one_confirmed_track(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture(root / 'dataset')
            result = root / 'result'
            try:
                report = pipeline.run(root / 'dataset', result, 'bearing_ekf', 1.)
            except Exception:
                for log in result.glob('*.log'):
                    print(log.name, log.read_text())
                raise
            self.assertEqual(report['status'], 'complete')
            self.assertEqual(report['cameras'], ['camera_0', 'camera_1'])
            self.assertFalse(any('depth' in topic or 'ground_truth' in topic for topic in report['input_topics']))
            final = json.loads((result / 'final_map.json').read_text())
            track, = final['tracks']
            self.assertEqual(track['lifecycle'], 'confirmed')
            self.assertEqual(track['source_cameras'], ['camera_0', 'camera_1'])
            self.assertAlmostEqual(track['x_m'], 7., delta=.5)
            self.assertAlmostEqual(track['y_m'], 0., delta=.2)
            self.assertTrue((result / 'scatter.png').exists())


if __name__ == '__main__':
    unittest.main()
