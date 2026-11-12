"""Explicit clock mapping and bounded pose resolution using SciPy SLERP."""
from bisect import bisect_left
from dataclasses import replace

import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from .contracts import PoseEstimate
from .validation import Unavailable, finite_nonnegative, root_cov, timestamp


class ClockMapper:
    def __init__(self, mappings):
        self.mappings = mappings
        for item in mappings.values():
            timestamp(item["reference_ns"])
            if not np.isfinite(item["drift_ppm"]) or abs(item["drift_ppm"]) > 1000:
                raise Unavailable("invalid_clock_drift")
            finite_nonnegative(item["independent_sigma_s"], "clock_sigma")
            finite_nonnegative(item["shared_sigma_s"], "clock_sigma")

    def at(self, stamp_ns, clock_id):
        timestamp(stamp_ns)
        if clock_id not in self.mappings:
            raise Unavailable("unmapped_clock")
        item = self.mappings[clock_id]
        mapped = stamp_ns + int(item["offset_ns"]) + round((stamp_ns-item["reference_ns"])*item["drift_ppm"]*1e-6)
        return timestamp(mapped), item


def interpolate(a, b, alpha):
    attitude = Slerp([0., 1.], Rotation.from_quat([a.attitude.as_quat(), b.attitude.as_quat()]))([alpha])[0]
    return (1-alpha)*a.position + alpha*b.position, attitude


def endpoint_jacobian(a, b, alpha, which):
    """Tangent derivative of SLERP; avoids averaging covariances without a model."""
    result = np.zeros((6, 6))
    result[:3, :3] = np.eye(3) * ((1-alpha) if which == 0 else alpha)
    _, nominal = interpolate(a, b, alpha)
    eps = 1e-6
    for axis in range(3):
        delta = np.eye(3)[axis]*eps
        target = a if which == 0 else b
        plus = replace(target, attitude=Rotation.from_rotvec(delta)*target.attitude)
        minus = replace(target, attitude=Rotation.from_rotvec(-delta)*target.attitude)
        _, rp = interpolate(plus, b, alpha) if which == 0 else interpolate(a, plus, alpha)
        _, rm = interpolate(minus, b, alpha) if which == 0 else interpolate(a, minus, alpha)
        result[3:, axis+3] = ((rp*nominal.inv()).as_rotvec()-(rm*nominal.inv()).as_rotvec())/(2*eps)
    return result


class PoseProvider:
    def __init__(self, origin_id, max_gap_s, history_s=30.):
        self.origin_id = origin_id
        self.max_gap_ns = round(finite_nonnegative(max_gap_s, "max_gap")*1e9)
        self.history_ns = round(finite_nonnegative(history_s, "history")*1e9)
        self.samples = []
        self.shared_models = {}

    def add(self, state):
        if self.samples and state.stamp_ns <= self.samples[-1].stamp_ns:
            raise Unavailable("unordered_state")
        if self.samples and state.epoch_id != self.samples[-1].epoch_id:
            raise Unavailable("pose_reset_requires_new_session")
        known = self.shared_models.get(state.shared_id)
        if known is not None and not np.array_equal(known, state.shared_cov):
            raise Unavailable("shared_model_changed_without_new_id")
        self.shared_models[state.shared_id] = state.shared_cov
        self.samples.append(state)
        cutoff = state.stamp_ns-self.history_ns
        while len(self.samples) > 2 and self.samples[1].stamp_ns < cutoff:
            self.samples.pop(0)

    def at(self, stamp_ns):
        timestamp(stamp_ns)
        times = [s.stamp_ns for s in self.samples]
        index = bisect_left(times, stamp_ns)
        if index < len(times) and times[index] == stamp_ns:
            a = b = self.samples[index]
            ja, jb = np.eye(6), np.zeros((6, 6))
            position, attitude, alpha = a.position, a.attitude, 0.
        else:
            if index == 0 or index == len(times):
                raise Unavailable("pose_not_bracketed")
            a, b = self.samples[index-1:index+1]
            if b.stamp_ns-a.stamp_ns > self.max_gap_ns:
                raise Unavailable("pose_gap_exceeded")
            alpha = (stamp_ns-a.stamp_ns)/(b.stamp_ns-a.stamp_ns)
            position, attitude = interpolate(a, b, alpha)
            ja, jb = endpoint_jacobian(a, b, alpha, 0), endpoint_jacobian(a, b, alpha, 1)
        if a.origin_id != self.origin_id or b.origin_id != self.origin_id:
            raise Unavailable("origin_mismatch")
        if a.epoch_id != b.epoch_id or a.position_reference != b.position_reference:
            raise Unavailable("pose_reset_boundary")
        factors = {}
        for state, jac in ((a, ja), (b, jb)):
            key = "pose_sample:" + state.epoch_id + ":" + str(state.stamp_ns)
            factors[key] = factors.get(key, np.zeros((6, 6))) + jac @ root_cov(state.sample_cov)
            key = "navigation:" + state.shared_id
            factors[key] = factors.get(key, np.zeros((6, 6))) + jac @ root_cov(state.shared_cov)
        factors = {key: value for key, value in factors.items() if np.any(value)}
        return PoseEstimate(stamp_ns, position, attitude,
                            (1-alpha)*a.velocity+alpha*b.velocity,
                            (1-alpha)*a.angular_velocity+alpha*b.angular_velocity,
                            factors, a.position_reference, (a.stamp_ns, b.stamp_ns))
