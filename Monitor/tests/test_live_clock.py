"""Clock diagnostic capture without GUI or camera decoding dependencies."""
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, '/opt/live')
import rclpy
import numpy as np
from scipy.spatial.transform import Rotation
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
from nav_msgs.msg import Odometry
from live_clock import LiveClock
from live_geometry import ns
from maritime_localization.timing import PoseBuffer, TimedPose


class ClockTraceTests(unittest.TestCase):
    def test_compressed_clock_interval_is_captured_and_not_used_as_pose_bracket(self):
        rclpy.init()
        node = LiveClock()
        try:
            # Synthetic valid converter slope of 0.05 compresses 20 ms to 1 ms.
            node.bridge.add(1_000_000_000, 2_000_000_000)
            node.bridge.add(2_000_000_000, 2_050_000_000)
            outputs = []
            node.output.publish = outputs.append
            for source_ns, yaw in [(1_000_000_000, 0.), (1_020_000_000, .005),
                                   (1_400_000_000, .02)]:
                pose = Odometry()
                pose.header.stamp.sec, pose.header.stamp.nanosec = divmod(source_ns, 1_000_000_000)
                pose.pose.pose.orientation.z = float(np.sin(yaw/2))
                pose.pose.pose.orientation.w = float(np.cos(yaw/2))
                node.on_pose(pose)
            self.assertEqual(node.anomalies_logged, 1)
            self.assertEqual(ns(outputs[1].header.stamp)-ns(outputs[0].header.stamp), 1_000_000)
            buffer = PoseBuffer()
            for pose in outputs:
                q = pose.pose.pose.orientation
                transform = np.eye(4)
                transform[:3, :3] = Rotation.from_quat([q.x, q.y, q.z, q.w]).as_matrix()
                buffer.add(TimedPose(ns(pose.header.stamp), transform, np.eye(6)))
            self.assertIsNone(buffer.fault)
            self.assertEqual(buffer.withheld, 1)
            _, bracket = buffer.lookup(2_001_000_000)
            self.assertEqual(bracket, (2_000_000_000, 2_020_000_000))
        finally:
            node.destroy_node()
            rclpy.shutdown()

    def test_capture_preserves_source_stamp_and_dumps_once_on_mapper_fault(self):
        rclpy.init()
        node = LiveClock()
        try:
            node.bridge.add(1_000_000_000, 2_000_000_000)
            node.bridge.add(2_000_000_000, 3_000_000_000)
            pose = Odometry()
            pose.header.stamp.sec, pose.header.stamp.nanosec = 1, 500_000_000
            pose.pose.pose.orientation.w = 1.
            node.on_pose(pose)
            self.assertEqual(ns(pose.header.stamp), 1_500_000_000)
            self.assertEqual(node.pose_trace[-1]['source_ns'], 1_500_000_000)
            self.assertEqual(node.pose_trace[-1]['converted_ns'], 2_500_000_000)
            self.assertEqual(node.pose_trace[-1]['reference_bracket'],
                             (1_000_000_000, 2_000_000_000, 2_000_000_000, 3_000_000_000))
            status = DiagnosticStatus(name='other', level=DiagnosticStatus.ERROR, message='unrelated')
            node.on_mapping_status(DiagnosticArray(status=[status]))
            self.assertFalse(node.trace_logged)
            status.name = 'bearing_ekf_buoy_mapping'
            with patch.object(node.get_logger(), 'error') as log:
                node.on_mapping_status(DiagnosticArray(status=[status]))
                node.on_mapping_status(DiagnosticArray(status=[status]))
                self.assertEqual(log.call_count, 1)
                self.assertIn('POSE_CLOCK_TRACE', log.call_args.args[0])
        finally:
            node.destroy_node()
            rclpy.shutdown()


