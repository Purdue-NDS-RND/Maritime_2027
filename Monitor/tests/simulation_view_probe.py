"""Live semantic check; run while the simulation view and gate scenario are active."""
import time

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo
from tf2_msgs.msg import TFMessage
from tf2_ros import Buffer
from visualization_msgs.msg import MarkerArray

rclpy.init()
node = Node('simulation_view_probe')
transforms, static, markers, truth = {}, {}, {}, {}
buffer = Buffer()


def on_tf(message, is_static=False):
    target = static if is_static else transforms
    for transform in message.transforms:
        target[transform.child_frame_id] = transform
        if is_static:
            buffer.set_transform_static(transform, "monitor_probe")
        else:
            buffer.set_transform(transform, "monitor_probe")


node.create_subscription(TFMessage, '/monitor/simulation/tf',
                         on_tf, 10)
node.create_subscription(TFMessage, '/monitor/simulation/tf_static',
                         lambda msg: on_tf(msg, is_static=True),
                         QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
node.create_subscription(MarkerArray, '/monitor/simulation/markers',
                         lambda msg: markers.update({(m.ns, m.id): m for m in msg.markers}), 10)
calibration = {}
node.create_subscription(CameraInfo, '/sensors/camera_0/color/camera_info',
                         lambda msg: calibration.update(camera=msg), qos_profile_sensor_data)
node.create_subscription(Odometry, '/blueboat/ground_truth/odometry',
                         lambda msg: truth.update(boat=msg), 10)
for name in ('buoy_1', 'buoy_2'):
    node.create_subscription(Odometry, f'/blueboat/ground_truth/{name}/odometry',
                             lambda msg, name=name: truth.update({name: msg}), 10)
deadline = time.monotonic() + 35
while time.monotonic() < deadline:
    rclpy.spin_once(node, timeout_sec=.1)
    if (all(frame in transforms for frame in ('base_link', 'buoy/buoy_1', 'buoy/buoy_2')) and
            len(static) == 2 and ('camera/image_plane', 0) in markers and len(truth) == 3 and calibration and
            any(endpoint.node_name in ('rviz', 'rviz2') for endpoint in
                node.get_subscriptions_info_by_topic('/sensors/camera_0/color/camera_info'))):
        break
assert len(truth) == 3, f'Missing source truth: {truth.keys()}'
for name, frame in [('boat', 'base_link'), ('buoy_1', 'buoy/buoy_1'), ('buoy_2', 'buoy/buoy_2')]:
    tf = transforms[frame]
    assert tf.header.frame_id == 'world'
    # The gate boat is stationary; buoy yaw is dynamic, position remains fixed.
    a, b = tf.transform.translation, truth[name].pose.pose.position
    assert max(abs(a.x-b.x), abs(a.y-b.y), abs(a.z-b.z)) < .05, (name, a, b)
    a, b = tf.transform.rotation, truth[name].pose.pose.orientation
    assert abs(a.x*b.x + a.y*b.y + a.z*b.z + a.w*b.w) > .99, name
assert set(static) == {'camera_0_link', 'camera_0_optical_frame'}, static.keys()
assert buffer.can_transform('world', 'camera_0_optical_frame', rclpy.time.Time()), 'Disconnected camera tree'
assert static['camera_0_link'].header.frame_id == 'base_link'
assert static['camera_0_optical_frame'].header.frame_id == 'camera_0_link'
plane = markers['camera/image_plane', 0]
assert plane.header.frame_id == 'camera_0_optical_frame'
assert len(plane.points) == len(plane.colors) == 80 * 45 * 6
assert all(abs(p.z - 1.5) < 1e-6 for p in plane.points)
info = calibration['camera']
assert abs(min(p.x for p in plane.points) + 1.5 * info.k[2] / info.k[0]) < 1e-5
assert abs(max(p.y for p in plane.points) - 1.5 * (info.height - info.k[5]) / info.k[4]) < 1e-5
assert plane.frame_locked
assert len({(round(c.r, 2), round(c.g, 2), round(c.b, 2)) for c in plane.colors}) > 10
assert len(markers['camera/frustum', 0].points) == 16
assert any(endpoint.node_name in ('rviz', 'rviz2') for endpoint in
           node.get_subscriptions_info_by_topic('/sensors/camera_0/color/camera_info')), \
    'RViz native CameraInfo display is not subscribed'
# A clock reset clears RViz's TF cache without recreating its subscriptions.
# Existing subscribers must receive the static mount again and reconnect.
static.clear()
buffer.clear()
deadline = time.monotonic() + 5
while time.monotonic() < deadline:
    rclpy.spin_once(node, timeout_sec=.1)
    if len(static) == 2 and buffer.can_transform('world', 'camera_0_optical_frame', rclpy.time.Time()):
        break
assert len(static) == 2, 'Static mount was not repeated after cache reset'
assert buffer.can_transform('world', 'camera_0_optical_frame', rclpy.time.Time()), 'Camera TF did not recover'
for topic in ('/tf', '/tf_static'):
    assert all(p.node_name != 'monitor_simulation_view' for p in node.get_publishers_info_by_topic(topic)), f'Monitor published public TF on {topic}'
print('PASS: world boat/buoy live poses, private camera chain, calibrated RGB plane and frustum; Monitor TF stays private')
node.destroy_node()
rclpy.shutdown()
