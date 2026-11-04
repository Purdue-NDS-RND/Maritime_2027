"""Optional ROS 2 recorded-event adapter; no flight, camera or synthetic fallback."""
import json
from pathlib import Path

from ..pipeline import PerceptionPipeline
from ..replay import line
from ..validation import Unavailable, load_json


def main():
    try:
        import rclpy
        from rclpy.node import Node
        from rclpy.qos import QoSProfile, DurabilityPolicy
        from std_msgs.msg import String
    except ImportError as exc:
        raise SystemExit("ROS adapter unavailable: install/source ROS 2; use the non-ROS replay CLI otherwise") from exc

    class RecordedPerceptionNode(Node):
        def __init__(self):
            super().__init__("perception_replay")
            for name in ("adapter", "session", "output"):
                self.declare_parameter(name, "")
            if self.get_parameter("adapter").value != "recorded":
                raise Unavailable("recorded_adapter_must_be_explicit")
            session = Path(self.get_parameter("session").value)
            output = Path(self.get_parameter("output").value)
            if not self.get_parameter("session").value or not self.get_parameter("output").value:
                raise Unavailable("session_and_output_required")
            if output.exists() and any(output.iterdir()):
                raise Unavailable("output_directory_must_be_empty")
            output.mkdir(parents=True, exist_ok=True)
            self.report_stream = (output/"reports.jsonl").open("w")
            self.events = (session/"measurements.jsonl").open()
            self.pipeline = PerceptionPipeline(load_json(session/"config.json"))
            qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
            self.publisher = self.create_publisher(String, "/drone/perception/report", qos)
            self.completed = False
            self.timer = self.create_timer(.01, self.tick)

        def tick(self):
            raw = self.events.readline()
            if not raw:
                self.events.close()
                self.report_stream.close()
                self.timer.cancel()
                self.completed = True
                return
            event = json.loads(raw)
            if event["kind"] == "vehicle_state":
                self.pipeline.add_state(event["data"])
            elif event["kind"] == "frame":
                report, _ = self.pipeline.process_frame(event["data"])
                encoded = line(report)
                self.report_stream.write(encoded)
                self.report_stream.flush()
                self.publisher.publish(String(data=encoded.strip()))
            else:
                raise Unavailable("unknown_event_kind")

    rclpy.init()
    node = None
    try:
        node = RecordedPerceptionNode()
        while rclpy.ok() and not node.completed:
            rclpy.spin_once(node)
    finally:
        if node is not None:
            node.events.close()
            node.report_stream.close()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
