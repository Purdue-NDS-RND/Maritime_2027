"""Static/random-walk tracks with explicit correlated-error sensitivities."""
from dataclasses import dataclass

import numpy as np
from scipy.linalg import solve
from scipy.optimize import linear_sum_assignment
from scipy.stats import chi2

from .validation import Unavailable, difference_factors, factors_covariance, finite_nonnegative


@dataclass
class Track:
    track_id: str
    class_id: str
    mean: np.ndarray
    independent_cov: np.ndarray
    factors: dict
    state_ns: int
    first_ns: int
    last_ns: int
    count: int = 1
    ambiguous: bool = False

    @property
    def covariance(self):
        return self.independent_cov + factors_covariance(self.factors)

    def predict(self, stamp_ns, spectral_density):
        if stamp_ns < self.state_ns:
            raise Unavailable("out_of_sequence_prediction")
        self.independent_cov += np.eye(2)*spectral_density*(stamp_ns-self.state_ns)*1e-9
        self.state_ns = stamp_ns
        self.ambiguous = False

    def update(self, observation):
        diff = difference_factors(self.factors, observation.factors)
        innovation_cov = self.independent_cov + observation.independent_cov + factors_covariance(diff)
        # Cov(track error, track error - observation error), including shared terms.
        numerator = self.independent_cov.copy()
        for key in sorted(self.factors):
            numerator += self.factors[key] @ diff[key].T
        gain = solve(innovation_cov, numerator.T, assume_a="pos").T
        residual = np.eye(2)-gain
        self.mean += gain @ (observation.mean-self.mean)
        self.independent_cov = residual @ self.independent_cov @ residual.T + gain @ observation.independent_cov @ gain.T
        keys = self.factors.keys() | observation.factors.keys()
        factors = {}
        for key in sorted(keys):
            template = self.factors.get(key, observation.factors.get(key))
            factors[key] = residual @ self.factors.get(key, np.zeros_like(template)) + gain @ observation.factors.get(key, np.zeros_like(template))
        self.factors = {key: factor for key, factor in factors.items() if np.any(factor)}
        self.independent_cov = (self.independent_cov+self.independent_cov.T)/2
        self.last_ns = observation.stamp_ns
        self.count += 1


class ObjectAssociator:
    def __init__(self, gate_probability=.99, ambiguity_cost_margin=.5):
        if not 0 < gate_probability < 1:
            raise Unavailable("invalid_gate_probability")
        self.gate = chi2.ppf(gate_probability, 2)
        self.margin = finite_nonnegative(ambiguity_cost_margin, "ambiguity_margin")

    def assign(self, tracks, observations):
        costs = np.full((len(tracks), len(observations)), np.inf)
        for i, track in enumerate(tracks):
            for j, observation in enumerate(observations):
                if track.class_id != observation.class_id:
                    continue
                cov = track.independent_cov + observation.independent_cov
                cov = cov + factors_covariance(difference_factors(track.factors, observation.factors))
                delta = observation.mean-track.mean
                distance = float(delta @ solve(cov, delta, assume_a="pos"))
                if distance <= self.gate:
                    costs[i, j] = .5*(distance+np.linalg.slogdet(cov)[1])
        ambiguous_tracks, ambiguous_observations = set(), set()
        for i, row in enumerate(costs):
            choices = np.flatnonzero(np.isfinite(row))
            if len(choices) > 1 and np.diff(np.sort(row[choices]))[0] < self.margin:
                ambiguous_tracks.add(i)
                ambiguous_observations.update(choices)
        for j, col in enumerate(costs.T):
            choices = np.flatnonzero(np.isfinite(col))
            if len(choices) > 1 and np.diff(np.sort(col[choices]))[0] < self.margin:
                ambiguous_observations.add(j)
                ambiguous_tracks.update(choices)
        for i in ambiguous_tracks:
            costs[i, :] = np.inf
        for j in ambiguous_observations:
            costs[:, j] = np.inf
        matches = []
        if len(tracks) and len(observations):
            # Dedicated dummy columns permit every track to remain unmatched.
            augmented = np.full((len(tracks), len(observations)+len(tracks)), 1e12)
            augmented[:, :len(observations)] = np.where(np.isfinite(costs), costs, 1e12)
            finite = costs[np.isfinite(costs)]
            miss_cost = (max(0., float(finite.max()))+1.) if len(finite) else 1.
            for i in range(len(tracks)):
                augmented[i, len(observations)+i] = miss_cost
            rows, columns = linear_sum_assignment(augmented)
            matches = [(int(i), int(j)) for i, j in zip(rows, columns)
                       if j < len(observations) and np.isfinite(costs[i, j])]
        used = {j for _, j in matches}
        unmatched = set(range(len(observations)))-used-ambiguous_observations
        return matches, unmatched, ambiguous_tracks, ambiguous_observations


class ObjectTracker:
    def __init__(self, settings):
        self.process_noise = finite_nonnegative(settings["random_walk_m2_s"], "process_noise")
        self.stale_s = finite_nonnegative(settings["stale_after_s"], "stale_after")
        self.confirm_hits = settings["confirm_hits"]
        self.max_tracks = settings["maximum_tracks"]
        if type(self.confirm_hits) is not int or self.confirm_hits < 2 or type(self.max_tracks) is not int or self.max_tracks < 1:
            raise Unavailable("invalid_tracker_limits")
        self.associator = ObjectAssociator(settings["gate_probability"], settings["ambiguity_cost_margin"])
        self.tracks = []
        self.next_id = 1

    def step(self, stamp_ns, observations):
        for track in self.tracks:
            track.predict(stamp_ns, self.process_noise)
        matches, unmatched, ambiguous_tracks, ambiguous_obs = self.associator.assign(self.tracks, observations)
        decisions = []
        for i in ambiguous_tracks:
            self.tracks[i].ambiguous = True
        for j in sorted(ambiguous_obs):
            decisions.append({"detection_id": observations[j].detection_id, "status": "ambiguous", "reason": "overlapping_association_hypotheses"})
        for i, j in matches:
            self.tracks[i].update(observations[j])
            decisions.append({"detection_id": observations[j].detection_id, "status": "matched", "track_id": self.tracks[i].track_id})
        for j in sorted(unmatched, key=lambda j: (observations[j].class_id, *observations[j].mean)):
            observation = observations[j]
            if len(self.tracks) >= self.max_tracks:
                decisions.append({"detection_id": observation.detection_id, "status": "rejected", "reason": "track_capacity"})
                continue
            track_id = f"object_{self.next_id:04d}"
            self.next_id += 1
            self.tracks.append(Track(track_id, observation.class_id, observation.mean.copy(), observation.independent_cov.copy(),
                                     {key: value.copy() for key, value in observation.factors.items()}, stamp_ns, stamp_ns, stamp_ns))
            decisions.append({"detection_id": observation.detection_id, "status": "initiated", "track_id": track_id})
        return decisions
