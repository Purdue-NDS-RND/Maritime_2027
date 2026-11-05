"""ROS 2 node that receives MAVROS IMU messages.

Its only jobs: subscribe to the topic, and pass each message through
    formatter (imu_formatter.py)  ->  output (imu_output.py)
It does NOT decide how data is cleaned or where it goes.

Run from the root of the repo (the folder that CONTAINS log/):

    python3 -m log.imu_listener
    python3 -m log.imu_listener --ros-args -p csv_path:=imu_log.csv

MAVROS must already be running (./mavros_boot.sh sim  or  device).
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu

from log.imu_formatter import from_imu_msg
from log.imu_output import ImuOutput


class ImuListener(Node):
    def __init__(self):
        super().__init__("imu_listener")

        # Parameters (settable from the command line with --ros-args -p name:=value)
        self.declare_parameter("topic", "/mavros/imu/data")
        self.declare_parameter("csv_path", "")         # empty = don't save to a file
        self.declare_parameter("print_period_s", 1.0)  # how often to print to the terminal

        topic = self.get_parameter("topic").value

        # The output module decides where data goes; we just configure it.
        self.output = ImuOutput(
            csv_path=self.get_parameter("csv_path").value,
            print_period_s=self.get_parameter("print_period_s").value,
            log=self.get_logger().info,
        )

        # Best-effort QoS so we actually receive MAVROS sensor data
        self.create_subscription(Imu, topic, self._on_imu, qos_profile_sensor_data)
        self.get_logger().info(f"Listening on {topic}")

    def _on_imu(self, msg):
        # raw ROS message -> clean sample -> wherever the output module sends it
        self.output.handle(from_imu_msg(msg))

    def close(self):
        self.output.close()


def main():
    rclpy.init()
    node = ImuListener()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
