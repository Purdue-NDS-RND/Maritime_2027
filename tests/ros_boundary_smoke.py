"""Read-only check from the simulation evaluator: public ROS interfaces exist.

Run through `make boundary-smoke` in Simulation/, with a scenario running.
Perfect pose remains outside shared navigation TF and is not used by this probe.
"""

import time

import rclpy
from mavros_msgs.msg import State
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import Image
from tf2_msgs.msg import TFMessage


def main():
    rclpy.init()
    node = Node("container_boundary_smoke")
    received = {"image": False, "connected": False}
    shared_frames = set()
    static_qos = QoSProfile(depth=100, durability=DurabilityPolicy.TRANSIENT_LOCAL)

    def on_shared(message):
        shared_frames.update(
            (item.header.frame_id, item.child_frame_id) for item in message.transforms
        )

    subscriptions = [
        node.create_subscription(Image, "/sensors/camera_0/color/image_raw",
                                 lambda _: received.update(image=True), qos_profile_sensor_data),
        node.create_subscription(State, "/mavros/state",
                                 lambda msg: received.update(connected=msg.connected), 10),
        node.create_subscription(TFMessage, "/tf", on_shared, 100),
        node.create_subscription(TFMessage, "/tf_static", on_shared, static_qos),
    ]
    try:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        assert all(received.values()), f"missing cross-container data: {received}"
        expected = {
            ("base_link", "camera_0_link"),
            ("camera_0_link", "camera_0_optical_frame"),
        }
        # MAVROS publishes fixed ENU/NED and FLU/FRD convention conversions;
        # these are not vessel pose estimates or simulator truth.
        allowed = expected | {
            ("map", "map_ned"), ("odom", "odom_ned"),
            ("base_link", "base_link_frd"),
        }
        assert expected <= shared_frames, f"missing camera extrinsics: {shared_frames}"
        assert shared_frames <= allowed, f"unexpected shared TF: {shared_frames}"
        print("BOUNDARY PASS: public camera and FCU data are present; truth TF is excluded from shared navigation TF")
    finally:
        for subscription in subscriptions:
            node.destroy_subscription(subscription)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
