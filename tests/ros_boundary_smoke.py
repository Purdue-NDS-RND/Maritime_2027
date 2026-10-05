"""Read-only public-interface/readiness probe; also runnable inside autonomy.

Evaluator mode decodes MAVROS State. --autonomy mode uses Adapter FCU
readiness evidence and verifies the State graph type without adding MAVROS
runtime/message packages to autonomy. Neither mode is mission acceptance.
Copy this file and boundary_contract.py together when executing in a container.
"""

import argparse
import time

import rclpy
from diagnostic_msgs.msg import DiagnosticArray
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image
from tf2_msgs.msg import TFMessage

from boundary_contract import MISSION, PLACEHOLDER, REQUIRED_READY, validate_evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--autonomy", action="store_true")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    rclpy.init(args=[])
    node = Node("container_boundary_smoke")
    received = {"connected": args.autonomy, "triples": 0}
    diagnostics, arrivals, streams, shared_frames = {}, {}, {"color": {}, "depth": {}, "info": {}}, set()
    static_qos = QoSProfile(depth=100, durability=DurabilityPolicy.TRANSIENT_LOCAL)

    def on_shared(message):
        shared_frames.update((item.header.frame_id, item.child_frame_id) for item in message.transforms)

    def on_diagnostics(message):
        for item in message.status:
            diagnostics[item.name] = (item.level, item.message, {value.key: value.value for value in item.values})
            arrivals[item.name] = time.monotonic()

    def on_camera(kind, message):
        assert message.header.frame_id == "camera_0_optical_frame", f"wrong public camera frame: {kind}"
        if kind != "info":
            expected = {"rgb8", "bgr8"} if kind == "color" else {"32FC1"}
            assert message.encoding in expected, f"wrong encoding: {kind}/{message.encoding}"
        key = (message.header.stamp.sec, message.header.stamp.nanosec)
        streams[kind][key] = (message.width, message.height)
        common = set(streams["color"]) & set(streams["depth"]) & set(streams["info"])
        for stamp in common:
            dimensions = [streams[component].pop(stamp) for component in streams]
            assert len(set(dimensions)) == 1 and min(dimensions[0]) > 0, "RGB-D not registered to CameraInfo dimensions"
            received["triples"] += 1
        for messages in streams.values():
            while len(messages) > 200:
                del messages[next(iter(messages))]

    subscriptions = [
        node.create_subscription(Image, "/sensors/camera_0/color/image_raw", lambda msg: on_camera("color", msg), qos_profile_sensor_data),
        node.create_subscription(Image, "/sensors/camera_0/depth/image_rect_raw", lambda msg: on_camera("depth", msg), qos_profile_sensor_data),
        node.create_subscription(CameraInfo, "/sensors/camera_0/color/camera_info", lambda msg: on_camera("info", msg), qos_profile_sensor_data),
        node.create_subscription(DiagnosticArray, "/diagnostics", on_diagnostics, 10),
        node.create_subscription(TFMessage, "/tf", on_shared, 100),
        node.create_subscription(TFMessage, "/tf_static", on_shared, static_qos),
    ]
    if not args.autonomy:
        from mavros_msgs.msg import State
        subscriptions.append(node.create_subscription(State, "/mavros/state", lambda msg: received.update(connected=msg.connected), 10))
    try:
        deadline = time.monotonic() + args.timeout
        failure = "no data"
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            try:
                assert received["triples"] >= 10 and received["connected"], f"missing cross-container data: {received}"
                assert dict(node.get_topic_names_and_types()).get("/mavros/state") == ["mavros_msgs/msg/State"], "MAVROS State contract missing"
                for name in REQUIRED_READY | {MISSION, PLACEHOLDER}:
                    assert time.monotonic() - arrivals.get(name, 0) <= 2.0, f"stale diagnostics: {name}"
                publishers = node.get_publisher_names_and_types_by_node("maritime_preimplementation_placeholder", "/")
                subscribers = node.get_subscriber_names_and_types_by_node("maritime_preimplementation_placeholder", "/")
                clients = node.get_client_names_and_types_by_node("maritime_preimplementation_placeholder", "/")
                assert publishers, "placeholder node not discovered"
                validate_evidence(diagnostics, shared_frames, [name for name, _ in publishers],
                                  [name for name, _ in subscribers], [name for name, _ in clients])
            except AssertionError as error:
                failure = str(error)
                continue
            print(f"BOUNDARY PASS: {received['triples']} exact RGB-D triples received; source/FCU readiness observed; shared TF and non-commanding placeholder verified; mission remains unready")
            if args.autonomy:
                print("AUTONOMY PROBE: MAVROS State graph type and FCU diagnostics verified; direct State decoding checked separately by evaluator")
            break
        else:
            raise AssertionError(failure)
    finally:
        for subscription in subscriptions:
            node.destroy_subscription(subscription)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
