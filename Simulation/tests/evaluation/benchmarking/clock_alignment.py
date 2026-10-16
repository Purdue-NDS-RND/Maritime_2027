"""Recover a simulation replay clock bridge from recorded FCU TimeReference data.

This is replay input normalization, not part of the RGB localization algorithm.
Source bags remain untouched. Receipt-time anchors have unmeasured common delay;
observed consistency is not an acquisition-time accuracy guarantee.
"""

from dataclasses import dataclass

import numpy as np
from nav_msgs.msg import Odometry
from rclpy.serialization import deserialize_message
import rosbag2_py
from sensor_msgs.msg import Image, TimeReference


POSE = '/mavros/local_position/odom'
REFERENCE = '/mavros/time_reference'
IMAGE = '/sensors/camera_0/color/image_raw'
ALIGNED_POSE = '/benchmark/vessel/odometry'


def ns(stamp):
    return stamp.sec*1_000_000_000 + stamp.nanosec


def reader(bag, topics):
    result = rosbag2_py.SequentialReader()
    result.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id='mcap'),
                rosbag2_py.ConverterOptions('cdr', 'cdr'))
    result.set_filter(rosbag2_py.StorageFilter(topics=topics))
    return result


@dataclass
class ClockAlignment:
    source_ns: list[int]
    target_ns: list[int]
    report: dict

    def convert(self, stamp):
        index = int(np.searchsorted(self.source_ns, stamp))
        if stamp < self.source_ns[0]-10_000_000 or stamp > self.source_ns[-1]+10_000_000:
            raise ValueError('Pose stamp outside calibrated clock interval (10 ms endpoint allowance)')
        index = max(1, min(index, len(self.source_ns)-1))
        a, b = self.source_ns[index-1:index+1]
        x, y = self.target_ns[index-1:index+1]
        # Subtract large epochs before arithmetic to preserve nanosecond precision.
        return x + round((stamp-a)*(y-x)/(b-a))


def calibrate(dataset, mode='auto', explicit_offset_s=0.):
    if mode not in ('auto', 'source', 'recorded-reference'):
        raise ValueError('Invalid pose clock mode')
    if mode == 'recorded-reference' and explicit_offset_s != 0:
        raise ValueError('Choose recorded-reference recovery or a constant offset, not both')
    if mode == 'source' or explicit_offset_s != 0:
        return None
    images = reader(dataset / 'bag', [IMAGE])
    if not images.has_next():
        raise ValueError('Recording contains no RGB frames')
    _, data, _ = images.read_next()
    image_stamp = ns(deserialize_message(data, Image).header.stamp)
    del images
    rows, pose_stamp = [], None
    sources = set()
    messages = reader(dataset / 'bag', [POSE, REFERENCE])
    while messages.has_next():
        topic, data, bag_stamp = messages.read_next()
        if topic == POSE:
            if pose_stamp is None:
                pose_stamp = ns(deserialize_message(data, Odometry).header.stamp)
        else:
            message = deserialize_message(data, TimeReference)
            sources.add(message.source)
            rows.append((ns(message.header.stamp), ns(message.time_ref), int(bag_stamp)))
    if pose_stamp is None:
        raise ValueError('Recording contains no vessel odometry')
    if mode == 'auto' and abs(pose_stamp-image_stamp) < 5_000_000_000:
        return None  # Already compatible clocks: preserve acquisition stamps.
    if rows and sources != {'fcu'}:
        raise ValueError('Clock recovery requires FCU TimeReference source')
    if len(rows) < 5:
        raise ValueError('Different pose/image clocks require at least five recorded FCU time references; '
                         'supply a verified offset or record compatible clocks')
    values = np.asarray(rows, dtype=np.int64)
    steps = np.diff(values, axis=0)
    if (steps <= 0).any() or np.max(steps[:, 0]) > 2_000_000_000:
        raise ValueError('Nonmonotonic/reset or gapped clock references')
    offsets = sorted(int(remote)-int(bag) for _, remote, bag in rows)
    remote_minus_sim = offsets[len(offsets)//2]
    residuals = np.array([offset-remote_minus_sim for offset in offsets], dtype=float)/1e9
    # Simulation FCU time must agree with recorded simulation-time bag stamps.
    # A tight residual screen prevents treating arbitrary hardware/receipt clocks
    # or a changing epoch as a valid simulation clock bridge.
    if max(abs(residuals)) > .02 or np.ptp(residuals) > .03:
        raise ValueError('FCU/simulation clock reference disagreement exceeds recovery limits')
    if abs(rows[0][2]-image_stamp) > 5_000_000_000:
        raise ValueError('Bag record clock is not compatible with source image simulation time')
    target = [int(remote)-remote_minus_sim for _, remote, _ in rows]
    rates = np.diff(target)/steps[:, 0]
    if np.any(rates < .1) or np.any(rates > 2.):
        raise ValueError('Implausible simulation clock rate')
    report = dict(mode='recorded-reference', source_topic=REFERENCE, reference_count=len(rows),
                  conversion='piecewise linear: source ROS stamp -> FCU time -> simulation time',
                  fcu_minus_sim_ns=remote_minus_sim,
                  reference_residual_max_s=float(max(abs(residuals))),
                  reference_residual_span_s=float(np.ptp(residuals)),
                  source_interval_ns=[int(values[0, 0]), int(values[-1, 0])],
                  target_interval_ns=[target[0], target[-1]],
                  sim_per_source_second_min=float(min(rates)), sim_per_source_second_max=float(max(rates)),
                  timing_uncertainty_floor_s=.02,
                  limitation='Recorded reference receipt delays and any common timing bias are unmeasured; '
                             '20 ms covariance inflation is a modeling floor, not a validated delay bound',
                  source_knots_ns=[int(row[0]) for row in rows], target_knots_ns=target)
    return ClockAlignment(report['source_knots_ns'], target, report)
