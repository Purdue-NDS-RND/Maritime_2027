"""Bounded acquisition-time pose lookup. Never infer clock offsets from arrivals."""

from dataclasses import dataclass

import numpy as np
from scipy.spatial.transform import Rotation, Slerp


@dataclass
class TimedPose:
    stamp_ns: int
    transform: np.ndarray
    covariance: np.ndarray


class PoseBuffer:
    def __init__(self, max_gap_s=.3, history_s=10., max_samples=1000,
                 max_speed_mps=15., max_turn_rad_s=4.):
        self.max_gap_ns = int(max_gap_s * 1e9)
        self.history_ns = int(history_s * 1e9)
        self.max_samples = max_samples
        self.max_speed = max_speed_mps
        self.max_turn = max_turn_rad_s
        self.samples = []
        self.fault = None

    def add(self, sample):
        if self.fault:
            return
        if self.samples:
            previous = self.samples[-1]
            dt = (sample.stamp_ns - previous.stamp_ns) / 1e9
            distance = np.linalg.norm(sample.transform[:3, 3] - previous.transform[:3, 3])
            turn = Rotation.from_matrix(previous.transform[:3, :3].T @ sample.transform[:3, :3]).magnitude()
            if dt < 0 or (dt == 0 and (distance > 1e-6 or turn > 1e-6)):
                self.fault = 'Pose clock rewound or conflicting duplicate; restart mapping session'
                return
            if dt == 0:
                return
            if distance > self.max_speed * dt or turn > self.max_turn * dt:
                self.fault = 'Pose discontinuity/origin reset; restart mapping session'
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
