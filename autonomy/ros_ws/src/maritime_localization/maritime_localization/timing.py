"""Bounded acquisition-time pose lookup. Never infer clock offsets from arrivals."""

from dataclasses import dataclass
from collections import deque

import numpy as np
from scipy.spatial.transform import Rotation, Slerp


@dataclass
class TimedPose:
    stamp_ns: int
    transform: np.ndarray
    covariance: np.ndarray


class PoseBuffer:
    def __init__(self, max_gap_s=.3, history_s=10., max_samples=1000,
                 max_speed_mps=15., max_turn_rad_s=4., min_motion_interval_s=.02):
        if not np.isfinite([max_gap_s, history_s, max_speed_mps, max_turn_rad_s,
                            min_motion_interval_s]).all() or not (
                0 < min_motion_interval_s <= max_gap_s and history_s > 0
                and max_samples >= 2 and max_speed_mps > 0 and max_turn_rad_s > 0):
            raise ValueError('Invalid pose buffer limits')
        self.max_gap_ns = int(max_gap_s * 1e9)
        self.history_ns = int(history_s * 1e9)
        self.max_samples = max_samples
        self.max_speed = max_speed_mps
        self.max_turn = max_turn_rad_s
        self.min_motion_ns = round(min_motion_interval_s * 1e9)
        self.last_received = None
        self.trace = deque(maxlen=100)
        self.withheld = 0
        self.samples = []
        self.fault = None

    def add(self, sample):
        if self.fault:
            return
        self.trace.append(dict(stamp_ns=sample.stamp_ns,
                               transform=sample.transform.tolist(),
                               covariance=sample.covariance.tolist()))
        # Ordering applies to ALL inputs, including poses withheld from lookup.
        if self.last_received is not None:
            previous = self.last_received
            dt = (sample.stamp_ns - previous.stamp_ns) / 1e9
            distance = np.linalg.norm(sample.transform[:3, 3] - previous.transform[:3, 3])
            turn = Rotation.from_matrix(previous.transform[:3, :3].T @ sample.transform[:3, :3]).magnitude()
            if dt < 0 or (dt == 0 and (distance > 1e-6 or turn > 1e-6)):
                self.fault = 'Pose clock rewound or conflicting duplicate; restart mapping session'
                return
            if dt == 0:
                return
        self.last_received = sample
        if self.samples:
            previous = self.samples[-1]
            interval_ns = sample.stamp_ns - previous.stamp_ns
            dt = interval_ns / 1e9
            distance = np.linalg.norm(sample.transform[:3, 3] - previous.transform[:3, 3])
            turn = Rotation.from_matrix(previous.transform[:3, :3].T @ sample.transform[:3, :3]).magnitude()
            # Do not divide tiny intervals into a noisy instantaneous rate.
            # The minimum-window envelope STILL rejects large jumps immediately.
            # Short-interval poses never enter interpolation or refresh its tail.
            window = max(interval_ns, self.min_motion_ns) / 1e9
            if distance > self.max_speed * window or turn > self.max_turn * window:
                self.fault = ('Pose discontinuity/origin reset; restart mapping session '
                              f'(dt={dt:.6f}s, window={window:.6f}s, '
                              f'distance={distance:.6f}m, turn={turn:.6f}rad)')
                return
            if interval_ns < self.min_motion_ns:
                self.withheld += 1
                return
        self.samples.append(sample)
        cutoff = sample.stamp_ns - self.history_ns
        self.samples = [item for item in self.samples if item.stamp_ns >= cutoff][-self.max_samples:]

    def lookup(self, stamp_ns):
        if self.fault:
            raise ValueError(self.fault)
        if not self.samples:
            raise LookupError('Waiting for acquisition-time pose brackets')
        stamps = [sample.stamp_ns for sample in self.samples]
        index = int(np.searchsorted(stamps, stamp_ns))
        if index < len(stamps) and stamps[index] == stamp_ns:
            sample = self.samples[index]
            return sample, (sample.stamp_ns, sample.stamp_ns)
        if index == 0 or index == len(stamps):
            raise LookupError('Image time outside pose history; check clock alignment')
        first, second = self.samples[index-1:index+1]
        gap = second.stamp_ns - first.stamp_ns
        if gap > self.max_gap_ns:
            raise ValueError('Acquisition-time pose interpolation gap exceeds limit')
        alpha = (stamp_ns - first.stamp_ns) / gap
        transform = np.eye(4)
        transform[:3, 3] = (1-alpha)*first.transform[:3, 3] + alpha*second.transform[:3, 3]
        transform[:3, :3] = Slerp([0., 1.], Rotation.from_matrix(
            np.array([first.transform[:3, :3], second.transform[:3, :3]])))([alpha]).as_matrix()[0]
        # Conservative interpolation: do not square weights and imply independent poses.
        covariance = (1-alpha)*first.covariance + alpha*second.covariance
        return TimedPose(stamp_ns, transform, covariance), (first.stamp_ns, second.stamp_ns)
