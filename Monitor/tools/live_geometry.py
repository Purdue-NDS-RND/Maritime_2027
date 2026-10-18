"""Bounded clock conversion and planar display alignment, without ROS imports."""
from collections import deque
import math
import numpy as np


def ns(stamp):
    return stamp.sec*1_000_000_000 + stamp.nanosec


def yaw(quaternion):
    q = quaternion
    return math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))


def rotation(angle):
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, -s], [s, c]])


def ellipse(mean, covariance, sigma=3.):
    covariance = np.asarray(covariance, dtype=float).reshape(2, 2)
    if not np.isfinite(covariance).all():
        raise ValueError('Nonfinite covariance')
    values, vectors = np.linalg.eigh((covariance+covariance.T)/2)
    if values[0] < -1e-8:
        raise ValueError('Invalid covariance')
    angles = np.linspace(0, 2*np.pi, 81)
    return np.asarray(mean)[:, None] + sigma*(vectors*np.sqrt(np.maximum(values, 0))) @ np.array([np.cos(angles), np.sin(angles)])


class ReceiptClock:
    """Experimental source-clock -> /clock receipt anchors; never extrapolate.

    Arrival delay is unmeasured. This is for a simulation demonstration, not a
    replacement for acquisition timestamps. A discontinuity latches until restart.
    """
    def __init__(self):
        self.knots = deque(maxlen=40)
        self.fault = None
        self.deferred = 0

    def add(self, source, target, *, defer_arrival_jitter=False):
        if self.fault:
            raise ValueError(self.fault)
        if self.knots:
            a, b = self.knots[-1]
            dx, dy = source-a, target-b
            if dx == 0 and dy == 0:
                return False
            if dx <= 0 or dy < 0 or dx > 2_000_000_000 or dy > 2_000_000_000:
                self.fault = 'Clock reference reset/gap; restart live mapping'
                raise ValueError(self.fault)
            if dy == 0:
                return False  # Paused simulation supplies no new clock information.
            if not .05 <= dy/dx <= 3.:
                if defer_arrival_jitter:
                    # Receipt anchors have unmeasured scheduling delay. Skip a
                    # transient slope outlier and wait for a wider valid bracket;
                    # never extrapolate or refresh output from a rejected anchor.
                    # Reset/backward and >2 s gap checks above remain immediate.
                    self.deferred += 1
                    return False
                self.fault = 'Implausible live clock rate; restart live mapping'
                raise ValueError(self.fault)
        self.knots.append((source, target))
        return True

    def convert(self, stamp):
        if self.fault:
            raise ValueError(self.fault)
        for (a, x), (b, y) in zip(self.knots, list(self.knots)[1:]):
            if a <= stamp <= b:
                return x + round((stamp-a)*(y-x)/(b-a))
        raise LookupError('Waiting for enclosing live clock references')


class DisplayAlignment:
    """Freeze world->map SE(2) from a time-matched boat pose pair, viewer only."""
    def __init__(self):
        self.r = None
        self.t = None

    def set(self, world_xy, world_yaw, map_xy, map_yaw):
        self.r = rotation(map_yaw-world_yaw)
        self.t = np.asarray(map_xy)-self.r @ np.asarray(world_xy)

    def point(self, world_xy):
        if self.r is None:
            raise LookupError('Waiting for boat poses to align truth for display')
        return self.r @ np.asarray(world_xy) + self.t
