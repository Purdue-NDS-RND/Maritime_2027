"""ROS 2 services around the boat-only mission executor."""

from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import signal
import time
import threading

from pymavlink import mavutil
import rclpy
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.signals import SignalHandlerOptions
from std_msgs.msg import String
from std_srvs.srv import Trigger

from .control import Control
from .http_api import serve
from .executor import Executor
from .mission import Mission


class BoatNode(Node):
    def __init__(self):
        super().__init__("boat_mission")
        self.declare_parameter("connection", "udpin:127.0.0.1:14551")
        self.declare_parameter("mission_file", "/mission/mission.json")
        self.declare_parameter("log_dir", "/logs")
        self.declare_parameter("http_port", 8091)
        self.record_lock = threading.Lock()
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
        self.control = Control(self.controller, self.log_dir)
        self.http = serve(self.control, self.get_parameter("http_port").value)
        self.command_group = ReentrantCallbackGroup()
        self.command_services = [self.create_service(Trigger, f"~/{name}", self.handler(name), callback_group=self.command_group)
                                 for name in ("upload", "start", "stop", "disarm")]
        self.create_timer(0.5, self.publish_status)
        self.get_logger().info(f"Waiting for boat on {connection}; evidence: {self.run_dir}")

    def record(self, event):
        with self.record_lock:
            self.events.write(json.dumps({"time_utc": datetime.now(timezone.utc).isoformat(),
                                      "monotonic_s": time.monotonic(), **event}, allow_nan=False) + "\n")

    def publish_status(self):
        status = self.control.status()
        self.publisher.publish(String(data=json.dumps(status, allow_nan=False)))
        self.record({"event": "status", **status})

    def handler(self, name):
        def handle(request, response):
            del request
            try:
                if name == "upload":
                    mission = Mission.load(self.get_parameter("mission_file").value)
                    envelope = {"approval_id": "local-file-" + mission.sha256,
                                "revision_sha256": mission.sha256,
                                "navigation_profile_id": "local-file-unvalidated",
                                "mission": mission.as_dict()}
                    operation = self.control.submit(name, envelope, mission.mission_id)
                else:
                    operation = self.control.submit(name, mission_id=self.control.status().get("mission_id"))
                deadline = time.monotonic() + 180
                while operation["state"] in ("pending", "running") and time.monotonic() < deadline:
                    time.sleep(0.02)
                    operation = self.control.operation(operation["operation_id"])
                response.success = operation["state"] == "succeeded"
                response.message = json.dumps(operation)
            except Exception as error:
                response.success, response.message = False, str(error)
                self.get_logger().error(f"{name}: {error}")
            self.record({"event": "service", "command": name,
                         "success": response.success, "message": response.message})
            self.publish_status()
            return response
        return handle

    def close(self):
        self.http.shutdown()
        self.http.server_close()
        self.control.close()
        self.events.close()
        self.owner_lock.close()


def main():
    # Keep ROS and the MAVLink connection alive for bounded shutdown cleanup.
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = BoatNode()
    executor = MultiThreadedExecutor(num_threads=6)
    executor.add_node(node)
    stopping = False
    def stop_signal(signum, frame):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGINT, stop_signal)
    signal.signal(signal.SIGTERM, stop_signal)
    try:
        while rclpy.ok() and not stopping:
            executor.spin_once(timeout_sec=0.1)
    finally:
        node.control.close()
        executor.shutdown()
        node.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
