"""Read-only MAVROS IMU subscriber; optional ROS imports occur only at startup."""
from .imu_formatter import from_imu_msg
from .imu_output import ImuOutput
from ..validation import Unavailable


def main():
    try:
        import rclpy
        from rclpy.node import Node
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import Imu
    except ImportError as exc:
        raise SystemExit("IMU listener unavailable: source a compatible ROS 2 environment with sensor_msgs and rclpy") from exc

    class ImuListener(Node):
        def __init__(self):
            super().__init__("imu_listener")
            self.output = None
            try:
                for name, default in (("topic", "/mavros/imu/data"), ("csv_path", ""),
                                      ("jsonl_path", ""), ("print_period_s", 1.)):
                    self.declare_parameter(name, default)
                topic = self.get_parameter("topic").value
                if not isinstance(topic, str) or not topic:
                    raise Unavailable("imu_topic_required")
                self.output = ImuOutput(csv_path=self.get_parameter("csv_path").value,
                                        jsonl_path=self.get_parameter("jsonl_path").value,
                                        print_period_s=self.get_parameter("print_period_s").value,
                                        log=self.get_logger().info)
                self.subscription = self.create_subscription(Imu, topic, self.on_imu, qos_profile_sensor_data)
                self.get_logger().info(f"Listening on {topic}; IMU alone does not provide position or validated heading")
            except Exception:
                self.close()
                self.destroy_node()
                raise

        def on_imu(self, msg):
            try:
                sample = from_imu_msg(msg)
            except (Unavailable, AttributeError, TypeError, ValueError) as exc:
                self.get_logger().warning(f"Rejected IMU sample: {exc}", throttle_duration_sec=5.)
                return
            # I/O failures propagate: recording must not silently pretend to succeed.
            self.output.handle(sample)

        def close(self):
            if self.output is not None:
                self.output.close()

    rclpy.init()
    node = None
    try:
        node = ImuListener()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.close()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
