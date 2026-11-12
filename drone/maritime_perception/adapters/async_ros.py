"""ROS test endpoints for the existing source-neutral event envelope."""
import json
import time

from ..async_test import AsyncRunner, Results, arrival_schedule
from ..replay import line, write_json
from ..validation import Unavailable, load_json


def run(args, ros_args, faults):
    try:
        import rclpy
        from rclpy.node import Node
        from rclpy.qos import QoSProfile, ReliabilityPolicy
        from std_msgs.msg import String
    except ImportError as exc:
        raise SystemExit("ROS asynchronous test unavailable: source a compatible ROS 2 environment") from exc
    if args.duration_s <= 0:
        raise Unavailable("positive_test_duration_required")
    if args.ros_publish and not args.session:
        raise Unavailable("publish_requires_explicit_session")
    if args.ros_live and (not args.config or not args.output):
        raise Unavailable("listen_requires_config_and_new_output")

    class TestNode(Node):
        def __init__(self):
            super().__init__("perception_async_test")
            self.output = None
            self.failure, self.done, self.sent = None, False, 0
            try:
                self.started = time.monotonic_ns()
                self.runner = None
                qos = QoSProfile(depth=32, reliability=ReliabilityPolicy.BEST_EFFORT)
                if args.ros_publish:
                    self.settings, self.schedule = arrival_schedule(args.session, **faults)
                    self.publisher = self.create_publisher(String, "/drone/perception/input", qos)
                    self.next = 0
                    # Allow subscriptions to discover before the small fixture begins.
                    self.started += 2_000_000_000
                else:
                    self.settings = load_json(args.config)
                    self.runner = AsyncRunner(self.settings, wait_s=args.wait_s, reorder_s=args.reorder_s, max_pending=args.max_pending)
                    self.output = Results(args.output)
                    write_json(self.output.path/"config.json", self.settings)
                    self.publisher = self.create_publisher(String, "/drone/perception/report", qos)
                    self.subscription = self.create_subscription(String, "/drone/perception/input", self.on_event, qos)
                self.timer = self.create_timer(.01, self.tick)
            except Exception:
                self.close()
                self.destroy_node()
                raise

        def on_event(self, message):
            if self.failure is not None:
                return
            try:
                event = json.loads(message.data)
                arrival = time.monotonic_ns()
                self.output.arrivals.write(line(dict(arrival_ns=arrival, event=event)))
                self.runner.submit(event, arrival)
            except (ValueError, TypeError) as exc:
                self.runner.reject("invalid_ros_event:"+str(exc))
            except Exception as exc:
                self.failure = exc

        def tick(self):
            try:
                now = time.monotonic_ns()
                if args.ros_publish:
                    elapsed = now-self.started
                    while self.next < len(self.schedule) and self.schedule[self.next][0] <= elapsed:
                        self.publisher.publish(String(data=line(self.schedule[self.next][2]).strip()))
                        self.next += 1
                        self.sent += 1
                    self.done = self.next == len(self.schedule)
                else:
                    results = self.runner.tick(now, published_ns=time.time_ns())
                    self.output.write(results)
                    for report, _ in results:
                        self.publisher.publish(String(data=line(report).strip()))
                if now-self.started >= round(args.duration_s*1e9):
                    self.done = True
            except Exception as exc:
                self.failure = exc
                self.timer.cancel()

        def close(self):
            if self.output is not None:
                try:
                    self.output.finish(self.runner)
                finally:
                    self.output.close()

    rclpy.init(args=ros_args)
    node = None
    try:
        node = TestNode()
        while rclpy.ok() and not node.done and node.failure is None:
            rclpy.spin_once(node)
        if node.failure is not None:
            raise node.failure
        return dict(published_input_events=node.sent, physical_accuracy_validated=False) if args.ros_publish else node.runner.summary()
    except KeyboardInterrupt:
        return dict(interrupted=True, physical_accuracy_validated=False) if node is None or node.runner is None else node.runner.summary()
    finally:
        try:
            if node is not None:
                try:
                    node.close()
                finally:
                    node.destroy_node()
        finally:
            if rclpy.ok():
                rclpy.shutdown()
