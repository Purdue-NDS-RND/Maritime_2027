"""Apply canonical settings to MAVROS 2.15.1's dynamic plugin nodes.

The pinned plugin constructor disables global ROS arguments, including params
files. Configure declared plugin parameters through their own service; independent
Adapter diagnostics verify each effective setting before downstream startup.
Initialize baseline telemetry once, leaving per-message intervals to sessions.
"""

import os
from pathlib import Path
import time

import rclpy
from mavros_msgs.msg import State
from mavros_msgs.srv import StreamRate
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.parameter_client import AsyncParameterClient
import yaml


class ConfigureMavros(Node):
    def __init__(self, *, parameter_overrides=None):
        super().__init__("mavros_configuration", parameter_overrides=parameter_overrides)
        filename = self.declare_parameter("configuration_file", "").value
        settings = yaml.safe_load(Path(filename).read_text(encoding="utf-8"))
        self.groups = {
            owner: values["ros__parameters"]
            for owner, values in settings.items() if owner.startswith("/mavros/")
        }
        if not self.groups:
            raise ValueError("canonical MAVROS plugin configuration is empty")
        timeout = float(os.environ.get("STACK_STARTUP_TIMEOUT", "180"))
        if timeout <= 0:
            raise ValueError("STACK_STARTUP_TIMEOUT must be positive")
        self.deadline = time.monotonic() + timeout
        self.parameter_clients = {owner: AsyncParameterClient(self, owner) for owner in self.groups}
        self.futures = {}
        self.completed = set()
        self.connected = False
        self.stream_future = None
        self.stream_client = self.create_client(StreamRate, "/mavros/set_stream_rate")
        self.create_subscription(State, "/mavros/state", self.on_state, 10)
        self.timer = self.create_timer(0.25, self.configure)

    def on_state(self, message):
        self.connected = message.connected

    def configure(self):
        if time.monotonic() >= self.deadline:
            pending = "; ".join(
                f"{owner}: {', '.join(self.groups[owner])}"
                for owner in sorted(set(self.groups) - self.completed)
            )
            raise RuntimeError(f"MAVROS canonical configuration timed out: {pending}; baseline telemetry connected={self.connected}")
        for owner, settings in self.groups.items():
            if owner in self.completed:
                continue
            future = self.futures.get(owner)
            if future is None:
                if self.parameter_clients[owner].services_are_ready():
                    parameters = [Parameter(name, value=value) for name, value in settings.items()]
                    self.futures[owner] = self.parameter_clients[owner].set_parameters(parameters)
                continue
            if not future.done():
                continue
            response = future.result()
            results = response.results
            if len(results) != len(settings) or any(not result.successful for result in results):
                errors = "; ".join(
                    f"{name}: {result.reason}" for name, result in zip(settings, results)
                    if not result.successful
                )
                raise RuntimeError(f"MAVROS canonical configuration rejected by {owner}: {errors}")
            self.completed.add(owner)
            self.get_logger().info(f"Applied canonical plugin settings to {owner}")
        if self.completed == set(self.groups):
            # Match the former MAVProxy 4 Hz baseline, once per startup. Repeated
            # REQUEST_DATA_STREAM_ALL resets individual SET_MESSAGE_INTERVAL
            # requests, starving navigation when rendering slows simulation.
            if self.stream_future is None:
                if self.connected and self.stream_client.service_is_ready():
                    self.stream_future = self.stream_client.call_async(
                        StreamRate.Request(stream_id=0, message_rate=4, on_off=True))
                return
            if not self.stream_future.done():
                return
            self.stream_future.result()  # Propagate transport errors.
            self.timer.cancel()
            self.get_logger().info("Initialized baseline telemetry at 4 Hz; per-message intervals remain session owned")
            self.get_logger().info("Canonical plugin configuration applied; diagnostics independently verify readiness")


def main():
    rclpy.init()
    node = ConfigureMavros()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
