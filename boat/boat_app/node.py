"""ROS 2 services around the boat-only mission executor."""

from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import signal
import time

from pymavlink import mavutil
import rclpy
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions
from std_msgs.msg import String
from std_srvs.srv import Trigger

from .executor import Executor
from .mission import Mission


class BoatNode(Node):
    def __init__(self):
        super().__init__("boat_mission")
        self.declare_parameter("connection", "udpin:127.0.0.1:14551")
        self.declare_parameter("mission_file", "/mission/mission.json")
        self.declare_parameter("log_dir", "/logs")
        self.log_dir = Path(self.get_parameter("log_dir").value)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.owner_lock = (self.log_dir / ".boat-owner.lock").open("a")
        fcntl.flock(self.owner_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + f"-{time.time_ns()}"
        self.run_dir = self.log_dir / run_id
        self.run_dir.mkdir()
        self.events = (self.run_dir / "events.jsonl").open("x", buffering=1)
        self.publisher = self.create_publisher(String, "~/status", 10)
        connection = self.get_parameter("connection").value
        link = mavutil.mavlink_connection(connection, source_system=245, source_component=191)
        self.controller = Executor(link, self.record)
        self.record({"event": "session", "connection": connection, "run_id": run_id})
        self.command_services = [self.create_service(Trigger, f"~/{name}", self.handler(name))
                                 for name in ("upload", "start", "stop", "disarm")]
        self.create_timer(0.1, self.controller.tick)
        self.create_timer(0.5, self.publish_status)
        self.get_logger().info(f"Waiting for boat on {connection}; evidence: {self.run_dir}")

    def record(self, event):
        self.events.write(json.dumps({"time_utc": datetime.now(timezone.utc).isoformat(),
                                      "monotonic_s": time.monotonic(), **event}, allow_nan=False) + "\n")

    def publish_status(self):
        status = self.controller.status()
        self.publisher.publish(String(data=json.dumps(status, allow_nan=False)))
        self.record({"event": "status", **status})

    def handler(self, name):
        def handle(request, response):
            del request
            try:
                if name == "upload":
                    if self.controller.state in ("executing", "stopping", "starting"):
                        raise ValueError("stop the current mission before replacing it")
                    # Invalidate local start authorization even if replacement parsing fails.
                    if self.controller.state == "uploaded":
                        self.controller.transition("ready", "replacement requested; previous start authorization revoked")
                    mission = Mission.load(self.get_parameter("mission_file").value)
                    snapshot = self.run_dir / f"mission-{mission.sha256}.json"
                    snapshot.write_text(json.dumps(mission.as_dict(), indent=2) + "\n")
                    self.controller.upload(mission)
                else:
                    getattr(self.controller, name)()
                response.success, response.message = True, self.controller.detail
            except Exception as error:
                response.success, response.message = False, str(error)
                self.get_logger().error(f"{name}: {error}")
            self.record({"event": "service", "command": name,
                         "success": response.success, "message": response.message})
            self.publish_status()
            return response
        return handle

    def close(self):
        if self.controller.state in ("executing", "stopping", "starting"):
            self.controller.fail("boat application shutting down; HOLD attempted only while owning AUTO")
        self.controller.link.close()
        self.events.close()
        self.owner_lock.close()


def main():
    # Keep ROS and the MAVLink connection alive for bounded shutdown cleanup.
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = BoatNode()
    stopping = False
    def stop_signal(signum, frame):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGINT, stop_signal)
    signal.signal(signal.SIGTERM, stop_signal)
    try:
        while rclpy.ok() and not stopping:
            rclpy.spin_once(node, timeout_sec=0.1)
    finally:
        node.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
