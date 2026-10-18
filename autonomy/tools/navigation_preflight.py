"""Read-only ROS discovery for the simulation navigation runner."""
import json
import time

import rclpy
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import String


def main():
    rclpy.init()
    node = rclpy.create_node('navigation_preflight')
    rosters = []
    node.create_subscription(String, '/sensors/camera_roster', lambda m: rosters.append(m.data),
                             QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
    try:
        deadline = time.monotonic()+4.
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.1)
        if len(set(rosters)) > 1:
            raise RuntimeError('Conflicting camera rosters on the ROS domain')
        print('PREFLIGHT:'+json.dumps(dict(nodes=node.get_node_names(),
            publishers=len(node.get_publishers_info_by_topic('/mavros/setpoint_raw/local')),
            roster=json.loads(rosters[-1]) if rosters else None)), flush=True)
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
