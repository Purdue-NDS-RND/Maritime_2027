"""Simulation monitor clock adapter. Does not subscribe to simulator truth."""
from collections import deque
import copy
import time

import numpy as np
import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import TimeReference

from live_geometry import ReceiptClock, ns

ALIGNED_POSE = '/monitor/mapping/vessel/odometry'


class LiveClock(Node):
    def __init__(self, pose_topic='/mavros/local_position/odom'):
        super().__init__('monitor_mapping_clock')
        self.bridge = ReceiptClock()
        self.sim = None
        self.sim_arrival = 0.
        self.reference_arrival = 0.
        self.pending = deque(maxlen=500)
        self.converted = 0
        self.dropped = 0
        self.fault = None
        self.last_output = None
        self.output = self.create_publisher(Odometry, ALIGNED_POSE, qos_profile_sensor_data)
        self.diagnostics = self.create_publisher(DiagnosticArray, '/monitor/mapping/clock', 10)
        self.create_subscription(Clock, '/clock', self.on_clock, qos_profile_sensor_data)
        self.create_subscription(TimeReference, '/mavros/time_reference', self.on_reference, qos_profile_sensor_data)
        self.create_subscription(Odometry, pose_topic, self.on_pose, qos_profile_sensor_data)
        # Release bracketed poses gradually: a one-Hz reference can unlock a
        # full second of odometry, which must not overflow keep-last-5 readers.
        self.create_timer(.01, self.drain)
        self.create_timer(1., self.status)
        self.get_logger().warning('EXPERIMENTAL receipt-clock adapter: unmeasured arrival delay; '
                                  '20 ms uncertainty floor is an assumption. No simulator truth input.')

    def on_clock(self, message):
        stamp = ns(message.clock)
        if self.sim is not None and stamp < self.sim:
            self.fault = 'Simulation clock rewound; restart live mapping'
        self.sim, self.sim_arrival = stamp, time.monotonic()

    def on_reference(self, message):
        if self.fault or self.sim is None or time.monotonic()-self.sim_arrival > .3:
            return
        try:
            if message.source != 'fcu':
                raise ValueError('Expected FCU TimeReference source')
            self.bridge.add(ns(message.header.stamp), self.sim)
            self.reference_arrival = time.monotonic()
        except ValueError as error:
            self.fault = str(error)
        self.drain()

    def on_pose(self, message):
        if len(self.pending) == self.pending.maxlen:
            self.dropped += 1
        self.pending.append((time.monotonic(), message))
        self.drain()

    def drain(self):
        if self.fault:
            return
        while self.pending:
            arrival, message = self.pending[0]
            try:
                stamp = self.bridge.convert(ns(message.header.stamp))
            except LookupError:
                if time.monotonic()-arrival > 1.5:
                    self.pending.popleft()
                    self.dropped += 1
                    continue
                break
            except ValueError as error:
                self.fault = str(error)
                return
            self.pending.popleft()
            if self.last_output is not None and stamp <= self.last_output:
                self.dropped += 1
                continue
            output = copy.deepcopy(message)
            output.header.stamp.sec, output.header.stamp.nanosec = divmod(stamp, 1_000_000_000)
            # Same explicit provisional timing floor as replay normalization.
            twist = message.twist.twist
            speed = np.array([twist.linear.x, twist.linear.y, twist.linear.z,
                              twist.angular.x, twist.angular.y, twist.angular.z])
            covariance = np.array(output.pose.covariance).reshape(6, 6)
            # Isotropic blocks avoid assuming twist and pose share a coordinate basis.
            covariance[:3, :3] += np.eye(3)*float(speed[:3] @ speed[:3])*.02**2
            covariance[3:, 3:] += np.eye(3)*float(speed[3:] @ speed[3:])*.02**2
            output.pose.covariance = covariance.reshape(-1).tolist()
            self.output.publish(output)
            self.last_output = stamp
            self.converted += 1
            return

    def status(self):
        stale = time.monotonic()-self.reference_arrival > 2.
        detail = self.fault or ('Waiting for fresh /clock and FCU references' if stale else
                               'Experimental receipt-time alignment; arrival bias unmeasured')
        status = DiagnosticStatus(name='live_mapping_clock',
                                  level=DiagnosticStatus.ERROR if self.fault else DiagnosticStatus.WARN,
                                  message=detail, values=[KeyValue(key='converted', value=str(self.converted)),
                                  KeyValue(key='dropped', value=str(self.dropped))])
        self.diagnostics.publish(DiagnosticArray(status=[status]))


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--pose-topic', default='/mavros/local_position/odom')
    args = parser.parse_args()
    rclpy.init()
    node = LiveClock(args.pose_topic)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
