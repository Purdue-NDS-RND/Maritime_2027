"""Clock recovery uses time-reference evidence only, never landmark geometry."""

from pathlib import Path
import unittest
from unittest.mock import patch

from nav_msgs.msg import Odometry
from rclpy.serialization import serialize_message
from sensor_msgs.msg import Image, TimeReference

from clock_alignment import ClockAlignment, IMAGE, POSE, REFERENCE, calibrate


SOURCE = 1_790_000_000_000_000_000
REMOTE = 1_789_000_000_000_000_000


def stamp(message_stamp, value):
    message_stamp.sec, message_stamp.nanosec = divmod(value, 1_000_000_000)


class FakeReader:
    def __init__(self, rows):
        self.rows = list(rows)
    def has_next(self):
        return bool(self.rows)
    def read_next(self):
        return self.rows.pop(0)


class ClockTests(unittest.TestCase):
    def rows(self, same_clock=False, bad=False, reset=False, missing=False):
        image = Image()
        stamp(image.header.stamp, 10_000_000_000)
        pose = Odometry()
        stamp(pose.header.stamp, 10_000_000_000 if same_clock else SOURCE)
        rows = [(IMAGE, serialize_message(image), 10_000_000_000),
                (POSE, serialize_message(pose), 10_000_000_000)]
        if not missing:
            for i in range(6):
                ref = TimeReference(source='fcu')
                stamp(ref.header.stamp, SOURCE+i*1_400_000_000)
                stamp(ref.time_ref, REMOTE+i*1_000_000_000+(i*50_000_000 if bad else 0))
                if reset and i == 5:
                    stamp(ref.header.stamp, SOURCE-1)
                rows.append((REFERENCE, serialize_message(ref), 10_000_000_000+i*1_000_000_000))
        return rows

    def calibration(self, rows, mode='auto'):
        with patch('clock_alignment.reader', side_effect=lambda _, topics: FakeReader(
                row for row in rows if row[0] in topics)):
            return calibrate(Path('/fake'), mode)

    def test_large_epoch_different_rate_clock_interpolates_without_precision_loss(self):
        alignment = self.calibration(self.rows())
        self.assertEqual(alignment.convert(SOURCE+700_000_000), 10_500_000_000)
        self.assertEqual(alignment.report['reference_count'], 6)
        self.assertAlmostEqual(alignment.report['sim_per_source_second_min'], 1/1.4)
        with self.assertRaises(ValueError):
            alignment.convert(SOURCE-20_000_000)

    def test_compatible_source_clocks_are_preserved(self):
        self.assertIsNone(self.calibration(self.rows(same_clock=True)))

    def test_unneeded_non_fcu_references_do_not_change_compatible_source_time(self):
        rows = self.rows(same_clock=True)
        changed = []
        from rclpy.serialization import deserialize_message
        for topic, data, bag_stamp in rows:
            if topic == REFERENCE:
                message = deserialize_message(data, TimeReference)
                message.source = 'other'
                data = serialize_message(message)
            changed.append((topic, data, bag_stamp))
        self.assertIsNone(self.calibration(changed))
        with self.assertRaisesRegex(ValueError, 'FCU TimeReference'):
            self.calibration(changed, 'recorded-reference')

    def test_source_mode_never_rewrites_pose_time(self):
        self.assertIsNone(self.calibration(self.rows(), 'source'))

    def test_missing_references_do_not_allow_silent_arrival_time_fallback(self):
        with self.assertRaisesRegex(ValueError, 'five recorded FCU'):
            self.calibration(self.rows(missing=True))

    def test_drifting_remote_clock_or_reset_is_rejected(self):
        for kwargs in ({'bad': True}, {'reset': True}):
            with self.assertRaises(ValueError):
                self.calibration(self.rows(**kwargs))

    def test_constant_offset_and_forced_clock_recovery_are_mutually_exclusive(self):
        with self.assertRaisesRegex(ValueError, 'not both'):
            calibrate(Path('/unused'), 'recorded-reference', 1.)


if __name__ == '__main__':
    unittest.main()
