"""Read-only live mapping evidence for a dual-camera run during boat motion."""
import json
import time

import rclpy
from diagnostic_msgs.msg import DiagnosticArray
from maritime_interfaces.msg import BuoyMap, BuoyEstimateArray
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from vision_msgs.msg import Detection2DArray

rclpy.init()
node = Node('dual_mapping_probe')
counts = {'camera_0': 0, 'camera_1': 0}
ready = []
latest = {}


def detection(camera, msg):
    counts[camera] += len(msg.detections)


def mapping(msg):
    latest.update(session=msg.session_id, paused=msg.paused, unresolved=msg.unresolved_count,
        tracks=[dict(id=t.world_id, lifecycle=t.lifecycle, x=t.x, y=t.y, cameras=list(t.source_cameras)) for t in msg.tracks])


for camera in counts:
    node.create_subscription(Detection2DArray, f'/perception/{camera}/detections',
        lambda msg, camera=camera: detection(camera, msg), qos_profile_sensor_data)
node.create_subscription(BuoyEstimateArray, '/localization/buoys',
    lambda msg: ready.append(msg.inputs_ready), qos_profile_sensor_data)
node.create_subscription(BuoyMap, '/mapping/buoys', mapping,
    QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
try:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=.1)
    subscriptions = node.get_subscriber_names_and_types_by_node('buoy_mapper', '/localization')
    topics = [topic for topic, _ in subscriptions]
    assert all(f'/perception/{camera}/detections' in topics for camera in counts), topics
    assert not any('depth' in topic or 'ground_truth' in topic for topic in topics), topics
    assert sum(ready) > 0, 'No acquisition-time assembled mapping frames'
    assert latest and not latest['paused'], latest
    nodes = node.get_node_names_and_namespaces()
    assert nodes.count(('buoy_mapper', '/localization')) == 1, nodes
    print(json.dumps(dict(ready_arrays=sum(ready), detections=counts, mapper_inputs=topics, final_map=latest), indent=2))
finally:
    node.destroy_node()
    rclpy.shutdown()
