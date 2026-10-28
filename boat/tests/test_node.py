"""Exercise ROS wiring without a vehicle, including a refused upload."""

from pathlib import Path
import tempfile
import time
import unittest

import rclpy
from pymavlink import mavutil
from std_srvs.srv import Trigger

from boat_app.node import BoatNode


class NodeTests(unittest.TestCase):
    def test_services_and_disconnected_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            mission = Path(__file__).resolve().parents[1] / "examples/mission.json"
            rclpy.init(args=["--ros-args", "-p", f"log_dir:={directory}",
                             "-p", "connection:=udpin:127.0.0.1:0",
                             "-p", f"mission_file:={mission}"])
            node = BoatNode()
            try:
                self.assertEqual(len(node.command_services), 4)
                node.publish_status()
                response = node.handler("upload")(Trigger.Request(), Trigger.Response())
                self.assertFalse(response.success)
                self.assertIn("stale", response.message)
                self.assertEqual(node.controller.state, "disconnected")
                port = node.controller.link.port.getsockname()[1]
                sender = mavutil.mavlink_connection(f"udpout:127.0.0.1:{port}", source_system=1, source_component=1)
                try:
                    sender.mav.heartbeat_send(11, 3, 0, 4, 3)
                    deadline = time.monotonic() + 2
                    while node.controller.state == "disconnected" and time.monotonic() < deadline:
                        rclpy.spin_once(node, timeout_sec=0.1)
                    self.assertEqual(node.controller.state, "ready")
                finally:
                    sender.close()
            finally:
                node.close()
                node.destroy_node()
                rclpy.shutdown()


if __name__ == "__main__":
    unittest.main()
