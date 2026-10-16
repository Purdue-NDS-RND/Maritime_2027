"""Planar bearing geometry, robust metric initialization, and Joseph EKF update."""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares


def wrap(value):
    return (value + np.pi) % (2*np.pi) - np.pi


@dataclass
class Bearing:
    stamp_ns: int
    camera: str
    origin: np.ndarray  # World camera XY.
    angle: float  # Attitude compensated world azimuth.
    variance: float
    pose_covariance: np.ndarray  # Camera XY covariance, independent-pose approximation.
    category: str
    observation_id: str

    @property
    def direction(self):
        return np.array([np.cos(self.angle), np.sin(self.angle)])


def prediction(point, view, settings):
    delta = point - view.origin
    q = float(delta @ delta)
    if q < settings.min_range_m**2 or q > settings.max_range_m**2:
        return None
    jacobian = np.array([-delta[1], delta[0]]) / q
    variance = view.variance + float(jacobian @ view.pose_covariance @ jacobian)
    return wrap(np.arctan2(delta[1], delta[0]) - view.angle), jacobian, variance


def initialize(views, settings):
    """Robust angular NLS, diverse inliers, and uncertainty/geometry gates."""
    if len(views) < settings.min_views:
        return None
    origins = np.array([view.origin for view in views])
    directions = np.array([view.direction for view in views])
    # Seed with ray intersections from a bounded set of geometrically useful pairs.
    seeds = []
    for i in range(len(views)):
        for j in range(i):
            parallax = abs(wrap(views[i].angle - views[j].angle))
            if (np.linalg.norm(origins[i]-origins[j]) < settings.min_baseline_m
                    or not np.deg2rad(settings.min_parallax_deg) <= parallax < np.pi/2):
                continue
            matrix = np.column_stack((directions[i], -directions[j]))
            distances = np.linalg.solve(matrix, origins[j]-origins[i])
            if np.all(distances > settings.min_range_m) and np.all(distances < settings.max_range_m):
                seeds.append(origins[i] + distances[0]*directions[i])
    if not seeds:
        return None
    def residual(point, selected):
        delta = point - np.array([view.origin for view in selected])
        q = np.maximum(np.einsum('ni,ni->n', delta, delta), 1e-8)
        jacobians = np.column_stack((-delta[:, 1], delta[:, 0])) / q[:, None]
        variances = np.array([view.variance + h @ view.pose_covariance @ h
                              for view, h in zip(selected, jacobians)])
        return wrap(np.arctan2(delta[:, 1], delta[:, 0]) - [view.angle for view in selected]) / np.sqrt(variances)
    # Robustly choose a seed, without running an optimizer for every pair.
    seed = min(seeds, key=lambda point: np.minimum(residual(point, views)**2, 9.).sum())
    result = least_squares(lambda point: residual(point, views), seed, loss='soft_l1',
                           max_nfev=settings.solver_iterations)
    inliers = np.abs(residual(result.x, views)) <= settings.inlier_sigma
    if inliers.sum() < settings.min_views or inliers.mean() < settings.min_inlier_fraction:
        return None
    selected = [view for view, accepted in zip(views, inliers) if accepted]
    # Refit only the accepted evidence. Consumed once when initializing the filter.
    result = least_squares(lambda point: residual(point, selected), result.x,
                           loss='soft_l1', max_nfev=settings.solver_iterations)
    if not result.success or not np.isfinite(result.x).all():
        return None
    useful_pair = any(np.linalg.norm(a.origin-b.origin) >= settings.min_baseline_m
                      and np.deg2rad(settings.min_parallax_deg) <= abs(wrap(a.angle-b.angle)) < np.pi/2
                      for i, a in enumerate(selected) for b in selected[:i])
    if not useful_pair:
        return None
    information = np.zeros((2, 2))
    for view in selected:
        model = prediction(result.x, view, settings)
        if model is None or np.dot(result.x-view.origin, view.direction) <= 0:
            return None
        innovation, h, variance = model
        if abs(innovation) > np.deg2rad(settings.max_residual_deg):
            return None
        information += np.outer(h, h) / variance
    if np.linalg.cond(information) > settings.max_condition:
        return None
    covariance = np.linalg.inv(information) + np.eye(2)*settings.position_floor_m**2
    if np.sqrt(np.linalg.eigvalsh(covariance)[-1]) > settings.max_initial_std_m:
        return None
    return result.x, covariance, len(selected)


def update(point, covariance, view, settings):
    model = prediction(point, view, settings)
    if model is None:
        return None
    innovation, h, variance = model
    s = float(h @ covariance @ h + variance)
    if innovation**2/s > settings.gate_chi2:
        return None
    gain = covariance @ h / s
    mean = point - gain*innovation
    a = np.eye(2) - np.outer(gain, h)
    posterior = a @ covariance @ a.T + np.outer(gain, gain)*variance
    # Persistent pose/model bias does not vanish by averaging adjacent images.
    values, vectors = np.linalg.eigh((posterior+posterior.T)/2)
    posterior = (vectors*np.maximum(values, settings.position_floor_m**2)) @ vectors.T
    return mean, posterior, float(innovation)
