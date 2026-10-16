"""One bounded, RGB-only semantic map shared by every camera.

Unknown range stays unresolved. Robust NLS initializes each metric track once;
new selected observations then update its independent 2D EKF. This is not SLAM.
"""

from collections import Counter
from dataclasses import dataclass, field
import uuid

import numpy as np
from scipy.optimize import linear_sum_assignment

from maritime_localization.bearing import Bearing, initialize, prediction, update, wrap


@dataclass(frozen=True)
class MappingSettings:
    min_range_m: float = .3
    max_range_m: float = 80.
    min_baseline_m: float = 1.
    min_parallax_deg: float = 5.
    min_views: int = 4
    max_views: int = 40
    max_tracks: int = 128
    solver_iterations: int = 60
    solve_interval_s: float = .5
    inlier_sigma: float = 3.
    min_inlier_fraction: float = .75
    max_residual_deg: float = 2.
    max_condition: float = 1000.
    max_initial_std_m: float = 2.
    position_floor_m: float = .25
    bearing_std_deg: float = 1.
    pose_position_floor_m: float = .15
    pose_attitude_floor_deg: float = 1.
    keyframe_distance_m: float = .2
    keyframe_angle_deg: float = 2.
    min_update_interval_s: float = .2
    association_angle_deg: float = 8.
    ambiguity_cost_margin: float = 1.
    gate_chi2: float = 9.
    unmatched_cost: float = 8.
    inconsistent_after: int = 5
    confirmation_updates: int = 3
    tentative_timeout_s: float = 5.
    stale_after_s: float = 5.
    process_noise_m2_s: float = .0025
    footprint_radius_m: float = .35
    shared_shift_deg: float = 3.

    def __post_init__(self):
        if (not np.isfinite(list(vars(self).values())).all()
                or any(value <= 0 for value in vars(self).values())
                or self.min_range_m >= self.max_range_m or self.min_views < 3
                or self.max_views < self.min_views or self.min_inlier_fraction > 1
                or self.min_parallax_deg >= 90 or self.association_angle_deg >= 90):
            raise ValueError('Invalid RGB mapping settings')


@dataclass
class WorldTrack:
    identifier: str
    category: str
    first_seen_ns: int
    last_seen_ns: int
    last_view: Bearing
    state: str = 'unresolved'
    mean: np.ndarray | None = None
    covariance: np.ndarray | None = None
    views: list = field(default_factory=list)
    cameras: set = field(default_factory=set)
    observations: int = 0
    selected_observations: int = 0
    confirmation_evidence: int = 0
    last_update_ns: int = 0
    last_predict_ns: int = 0
    last_solve_ns: int = 0
    provenance: list = field(default_factory=list)
    residual_rad: float = 0.
    contradictions: int = 0


class BearingMapper:
    def __init__(self, settings=None):
        self.settings = settings or MappingSettings()
        self.session_id = uuid.uuid4().hex
        self.tracks = []
        self.next_identifier = 1
        self.last_stamp_ns = None
        self.diagnostics = Counter()
        self.decisions = []
        self.paused_reason = None

    def pause(self, reason):
        self.paused_reason = reason
        self.diagnostics['session_paused'] += 1

    def snapshot(self):
        return [track for track in self.tracks if track.mean is not None]

    def _selected(self, old, new):
        return (new.stamp_ns-old.stamp_ns >= self.settings.min_update_interval_s*1e9
                and (np.linalg.norm(new.origin-old.origin) >= self.settings.keyframe_distance_m
                     or abs(wrap(new.angle-old.angle)) >= np.deg2rad(self.settings.keyframe_angle_deg)))

    def _cost(self, track, view):
        s = self.settings
        if track.category != view.category or track.state == 'inconsistent':
            return np.inf
        if track.mean is None:
            # Tracklets stay camera-local until a defensible world position exists.
            if view.camera != track.last_view.camera:
                return np.inf
            residual = abs(wrap(view.angle-track.last_view.angle))
            return 3. + .5*(residual/np.deg2rad(s.bearing_std_deg*2))**2 if residual < np.deg2rad(s.association_angle_deg) else np.inf
        model = prediction(track.mean, view, s)
        if model is None:
            return np.inf
        residual, h, variance = model
        innovation_variance = float(h @ track.covariance @ h + variance)
        nis = residual**2/innovation_variance
        if nis > s.gate_chi2 or abs(residual) > np.deg2rad(s.association_angle_deg):
            return np.inf
        return .5*(nis + np.log(innovation_variance / np.deg2rad(s.bearing_std_deg)**2))

    def _assign(self, measurements):
        """Frame-wide assignment with explicit unmatched alternatives and global margin."""
        n, m = len(measurements), len(self.tracks)
        if not n:
            return {}, set()
        costs = np.array([[self._cost(track, view) for track in self.tracks]
                          for view in measurements]).reshape(n, m)
        self.diagnostics["gated_candidates"] += int(np.isfinite(costs).sum())
        # One dummy per measurement. Missed tracks cost zero; unmatched detections pay.
        matrix = np.full((n, m+n), self.settings.unmatched_cost)
        matrix[:, :m] = np.where(np.isfinite(costs), costs, 1e9)
        rows, columns = linear_sum_assignment(matrix)
        total = matrix[rows, columns].sum()
        assignments, deferred = {}, set()
        for row, column in zip(rows, columns):
            if column >= m:
                if np.isfinite(costs[row]).any():
                    deferred.add(row)  # A possible existing identity must not create a duplicate.
                else:
                    # Near a known landmark but inconsistent with its uncertainty:
                    # withhold a duplicate and count sustained contradictory evidence.
                    view = measurements[row]
                    near = []
                    for track in self.snapshot():
                        model = prediction(track.mean, view, self.settings)
                        if (track.category == view.category and model is not None
                                and abs(model[0]) < np.deg2rad(self.settings.association_angle_deg)):
                            near.append(track)
                    if near:
                        deferred.add(row)
                        if len(near) == 1:
                            near[0].contradictions += 1
                            if near[0].contradictions >= self.settings.inconsistent_after:
                                near[0].state = 'inconsistent'
                                self.diagnostics['inconsistent_track'] += 1
                continue
            alternative = matrix.copy()
            alternative[row, column] = 1e9
            ar, ac = linear_sum_assignment(alternative)
            if alternative[ar, ac].sum()-total < self.settings.ambiguity_cost_margin:
                deferred.add(row)
            else:
                assignments[row] = self.tracks[column]
        return assignments, deferred

    def process(self, stamp_ns, measurements):
        self.decisions = []
        if self.paused_reason:
            return []
        if self.last_stamp_ns is not None and stamp_ns < self.last_stamp_ns:
            self.diagnostics['late_frame_rejected'] += 1
            return []  # Delay policy: reject; no out-of-sequence posterior mutation.
        if any(view.stamp_ns != stamp_ns for view in measurements):
            raise ValueError('A frame must contain only its acquisition-time measurements')
        self.last_stamp_ns = stamp_ns
        s = self.settings
        self.tracks = [track for track in self.tracks if track.mean is not None
                       or stamp_ns-track.last_seen_ns <= s.tentative_timeout_s*1e9]
        for track in self.snapshot():
            elapsed = max(0., (stamp_ns-track.last_predict_ns)/1e9)
            track.covariance += np.eye(2)*s.process_noise_m2_s*elapsed
            track.last_predict_ns = stamp_ns
            if stamp_ns-track.last_seen_ns > s.stale_after_s*1e9 and track.state == 'confirmed':
                track.state = 'stale'
        # Coherent errors across several confidently distinct categories suggest shared
        # pose/calibration trouble. Defer the entire frame instead of making duplicates.
        shifts = []
        for view in measurements:
            candidates = [track for track in self.snapshot() if track.category == view.category]
            if len(candidates) == 1:
                model = prediction(candidates[0].mean, view, s)
                if model:
                    shifts.append(model[0])
        if (len(shifts) >= 3 and abs(np.median(shifts)) > np.deg2rad(s.shared_shift_deg)
                and np.std(shifts) < np.deg2rad(s.bearing_std_deg)):
            self.diagnostics['shared_residual_frame_rejected'] += 1
            self.decisions = [(view, '', 'shared_residual') for view in measurements]
            return []
        assignments, deferred = self._assign(measurements)
        updated = []
        for row, view in enumerate(measurements):
            if row in deferred:
                self.diagnostics['ambiguous_observation'] += 1
                self.decisions.append((view, '', 'ambiguous'))
                continue
            track = assignments.get(row)
            if track is None:
                if len(self.tracks) >= s.max_tracks:
                    self.diagnostics['track_capacity_rejected'] += 1
                    self.decisions.append((view, '', 'capacity'))
                    continue
                track = WorldTrack(f'buoy-{self.next_identifier}', view.category,
                                   stamp_ns, stamp_ns, view)
                self.next_identifier += 1
                self.tracks.append(track)
            track.last_seen_ns = stamp_ns
            track.cameras.add(view.camera)
            track.observations += 1
            track.provenance = [*track.provenance, view.observation_id][-s.max_views:]
            selected = not track.views or self._selected(track.views[-1], view)
            decision = 'redundant'
            if selected:
                track.selected_observations += 1
                if track.mean is None:
                    # Preserve the oldest useful baseline while bounding recent history.
                    track.views.append(view)
                    if len(track.views) > s.max_views:
                        track.views.pop(1)
                    if stamp_ns-track.last_solve_ns >= s.solve_interval_s*1e9:
                        track.last_solve_ns = stamp_ns
                        self.diagnostics["initializer_attempts"] += 1
                        fit = initialize(track.views, s)
                        if fit:
                            # Two unresolved camera-local tracklets may converge on
                            # the same world location. Do not promote a duplicate.
                            # Cross-camera evidence is not independently fused here.
                            competing = []
                            for known in self.snapshot():
                                if known.category != track.category:
                                    continue
                                delta = fit[0]-known.mean
                                if delta @ np.linalg.solve(fit[1]+known.covariance, delta) < s.gate_chi2:
                                    competing.append(known)
                            if competing:
                                decision = 'promotion_identity_deferred'
                                self.diagnostics[decision] += 1
                                self.decisions.append((view, track.identifier, decision))
                                continue
                            track.mean, track.covariance, _ = fit
                            track.last_update_ns = track.last_predict_ns = stamp_ns
                            track.state = 'tentative'
                            decision = 'initialized'
                            self.diagnostics['initialized'] += 1
                        else:
                            decision = 'unresolved_geometry'
                else:
                    posterior = update(track.mean, track.covariance, view, s)
                    if posterior:
                        track.mean, track.covariance, track.residual_rad = posterior
                        track.last_update_ns = stamp_ns
                        track.contradictions = 0
                        track.views = [view]  # No optimizer reuse of filter evidence.
                        track.confirmation_evidence += 1
                        if track.confirmation_evidence >= s.confirmation_updates:
                            track.state = 'confirmed'
                        elif track.state == 'stale':
                            track.state = 'confirmed'
                        updated.append(track)
                        decision = 'updated'
                        self.diagnostics['ekf_update'] += 1
                    else:
                        decision = 'innovation_rejected'
                        self.diagnostics[decision] += 1
            track.last_view = view
            self.decisions.append((view, track.identifier, decision))
        self.diagnostics['frames'] += 1
        self.diagnostics['observations'] += len(measurements)
        return updated
