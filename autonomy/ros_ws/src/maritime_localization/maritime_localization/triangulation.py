"""Temporal bearing-only triangulation of stationary, category-associated boxes."""

from dataclasses import dataclass, field

import numpy as np

from maritime_localization.geometry import angle, camera_ray, validate_observation
from maritime_localization.interfaces import Observation, PositionEstimate


@dataclass(frozen=True)
class TriangulationSettings:
    min_baseline_m: float = 1.0
    min_parallax_deg: float = 5.0
    keyframe_distance_m: float = 0.15
    association_angle_deg: float = 6.0
    ambiguity_margin_deg: float = 0.5
    max_residual_deg: float = 1.0
    min_range_m: float = 0.2
    max_range_m: float = 80.0
    track_timeout_s: float = 3.0  # Source image clock; no pose-clock comparisons.
    min_views: int = 3
    max_views: int = 40
    max_tracks: int = 128

    def __post_init__(self):
        if (not np.isfinite(list(vars(self).values())).all()
                or any(value <= 0 for value in vars(self).values())
                or self.min_views < 3 or self.max_views < self.min_views or self.max_tracks < 1
                or self.min_range_m >= self.max_range_m
                or not self.max_residual_deg < self.association_angle_deg < 90
                or self.min_parallax_deg >= 90):
            raise ValueError("Invalid triangulation settings")


@dataclass
class Track:
    identifier: str
    category: str
    last_seen_ns: int
    last_direction: np.ndarray
    views: list = field(default_factory=list)  # (camera origin, unit world ray)
    point: np.ndarray | None = None


def intersect_rays(views, settings):
    """Least-squares distance to viewing lines, with observable forward geometry."""
    if len(views) < settings.min_views:
        return None
    origins = np.array([origin for origin, _ in views])
    directions = np.array([direction for _, direction in views])
    # Repeated frames from one camera position do not supply independent views.
    if len(np.unique(origins.round(decimals=6), axis=0)) < settings.min_views:
        return None
    # Require translation AND parallax from the same pair. Pure rotation cannot range.
    good_pair = any(np.linalg.norm(origins[i]-origins[j]) >= settings.min_baseline_m
                    and np.deg2rad(settings.min_parallax_deg) <= angle(directions[i], directions[j]) < np.pi/2
                    for i in range(len(views)) for j in range(i))
    if not good_pair:
        return None
    projectors = np.eye(3) - directions[:, :, None] * directions[:, None, :]
    matrix = projectors.sum(axis=0)
    if np.linalg.cond(matrix) > 1e5:
        return None
    point = np.linalg.solve(matrix, np.einsum("nij,nj->i", projectors, origins))
    offsets = point - origins
    ranges = np.linalg.norm(offsets, axis=1)
    if (not np.isfinite(point).all() or np.any(ranges < settings.min_range_m)
            or np.any(ranges > settings.max_range_m)
            or np.any(np.einsum("ni,ni->n", offsets, directions) <= 0)):
        return None
    residuals = [angle(offset / distance, direction)
                 for offset, distance, direction in zip(offsets, ranges, directions)]
    return point if max(residuals) <= np.deg2rad(settings.max_residual_deg) else None


class TriangulationLocalizer:
    implemented = True

    def __init__(self, settings=None):
        self.settings = settings or TriangulationSettings()
        self.reset()

    def reset(self):
        self.tracks = []
        self.next_identifier = 1
        self.last_timestamp_ns = None
        self.frame = None

    def process(self, observation: Observation) -> list[PositionEstimate]:
        if observation.depth_m is not None:
            raise ValueError("RGB triangulation observations must not include depth")
        validate_observation(observation)
        stamp = observation.timestamp_ns
        frame = (observation.reference_frame, observation.camera_frame)
        if self.frame != frame or (self.last_timestamp_ns is not None and stamp < self.last_timestamp_ns):
            self.reset()
        self.frame, self.last_timestamp_ns = frame, stamp
        settings = self.settings
        self.tracks = [track for track in self.tracks
                       if stamp - track.last_seen_ns <= settings.track_timeout_s * 1e9]
        origin = observation.camera_to_reference[:3, 3].copy()
        measurements = []
        for box in observation.boxes:
            ray = camera_ray(observation, box)
            if ray is not None:
                direction = observation.camera_to_reference[:3, :3] @ ray
                measurements.append((box.category, direction / np.linalg.norm(direction)))
        # Match by category and rotation-compensated world bearing, or by the
        # predicted bearing of a triangulated point. Marker IDs are never consulted.
        costs = np.full((len(measurements), len(self.tracks)), np.inf)
        for row, (category, direction) in enumerate(measurements):
            for column, track in enumerate(self.tracks):
                if category != track.category:
                    continue
                predicted = track.last_direction if track.point is None else track.point-origin
                norm = np.linalg.norm(predicted)
                if norm > 1e-9:
                    error = angle(direction, predicted / norm)
                    if error <= np.deg2rad(settings.association_angle_deg):
                        costs[row, column] = error
        # Mutual nearest match with a margin in both directions. Ambiguous
        # measurements are skipped rather than merged into a same-color track.
        assignments, ambiguous = {}, set()
        margin = np.deg2rad(settings.ambiguity_margin_deg)
        for row in range(len(measurements)):
            columns = np.argsort(costs[row])
            if not len(columns) or not np.isfinite(costs[row, columns[0]]):
                continue
            column = columns[0]
            rows = np.argsort(costs[:, column])
            if (rows[0] != row
                    or (len(columns) > 1 and costs[row, columns[1]] - costs[row, column] < margin)
                    or (len(rows) > 1 and costs[rows[1], column] - costs[row, column] < margin)):
                ambiguous.add(row)
            else:
                assignments[row] = self.tracks[column]
        estimates = []
        for row, (category, direction) in enumerate(measurements):
            if row in ambiguous:
                continue
            track = assignments.get(row)
            if track is None:
                if len(self.tracks) >= settings.max_tracks:
                    continue
                track = Track(f"track-{self.next_identifier}", category, stamp, direction)
                self.next_identifier += 1
                self.tracks.append(track)
            track.last_seen_ns, track.last_direction = stamp, direction
            view = (origin.copy(), direction.copy())
            # Keep spatial keyframes; update the latest bearing even at rest.
            views = [*track.views, view]
            if not track.views or np.linalg.norm(origin-track.views[-1][0]) >= settings.keyframe_distance_m:
                track.views = views[-settings.max_views:]
                views = track.views
            point = intersect_rays(views, settings)
            if point is not None:
                track.point = point
                estimates.append(PositionEstimate(stamp, observation.reference_frame, category,
                                                   (float(point[0]), float(point[1])), track.identifier))
        return estimates
