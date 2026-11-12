import numpy as np
import pytest

from maritime_perception.contracts import Observation
from maritime_perception.tracking import ObjectTracker


def observation(point, time, ident="d", sigma=.03, factors=None):
    return Observation(ident, "buoy", time, np.asarray(point, dtype=float), np.eye(2)*sigma**2,
                       {} if factors is None else factors, "frame", "calibration")


def tracker(settings):
    return ObjectTracker(settings["tracking"])


def test_shared_translation_does_not_average_away(settings):
    tracking = tracker(settings)
    shared = {"navigation:common": np.eye(2)*2}
    for i in range(100):
        tracking.step(i*1_000_000_000, [observation([.7, -.4], i*1_000_000_000, factors=shared, sigma=.1)])
    assert len(tracking.tracks) == 1
    track = tracking.tracks[0]
    np.testing.assert_allclose(track.mean, [.7, -.4])
    np.testing.assert_allclose(track.covariance, np.eye(2)*(4+.01/100), rtol=1e-10)
    assert track.count == 100


def test_shared_linear_filter_covariance_against_monte_carlo(settings):
    rng = np.random.default_rng(991)
    means = []
    for _ in range(1000):
        common = rng.normal(0., 2., 2)
        # One object; direct updates avoid association-selection bias in this statistical check.
        tracking = tracker(settings)
        tracking.step(0, [observation(common+rng.normal(0, .3, 2), 0, sigma=.3, factors={"b": np.eye(2)*2})])
        track = tracking.tracks[0]
        for i in range(1, 8):
            track.predict(i, 0.)
            track.update(observation(common+rng.normal(0, .3, 2), i, sigma=.3, factors={"b": np.eye(2)*2}))
        means.append(track.mean)
    empirical = np.cov(np.asarray(means).T)
    # 1000 independent trials; 12% tolerance is wider than covariance sampling error.
    assert np.linalg.norm(empirical-track.covariance)/np.linalg.norm(track.covariance) < .12


def test_nearby_same_class_objects_misses_and_outlier(settings):
    tracking = tracker(settings)
    shared = {"gps": np.eye(2)*2}
    tracking.step(0, [observation([0, 0], 0, "a", factors=shared), observation([.5, 0], 0, "b", factors=shared)])
    decisions = tracking.step(1_000_000_000, [observation([.5, 0], 1_000_000_000, "b2", factors=shared),
                                            observation([0, 0], 1_000_000_000, "a2", factors=shared)])
    assert {d["detection_id"]: d["track_id"] for d in decisions} == {"a2": "object_0001", "b2": "object_0002"}
    tracking.step(2_000_000_000, [])
    decisions = tracking.step(3_000_000_000, [observation([.5, 0], 3_000_000_000, "return", factors=shared),
                                            observation([8, 0], 3_000_000_000, "outlier", factors=shared)])
    assert next(d for d in decisions if d["detection_id"] == "return")["track_id"] == "object_0002"
    assert next(d for d in decisions if d["detection_id"] == "outlier")["status"] == "initiated"
    assert tracking.tracks[-1].count == 1  # Explicit tentative track, not a confirmed map object.


def test_ambiguous_observation_is_not_forced_or_duplicated(settings):
    tracking = tracker(settings)
    tracking.step(0, [observation([0, 0], 0, sigma=.3), observation([.2, 0], 0, sigma=.3)])
    decisions = tracking.step(1, [observation([.1, 0], 1, sigma=.3)])
    assert decisions[0]["status"] == "ambiguous"
    assert len(tracking.tracks) == 2
    assert all(track.count == 1 and track.ambiguous for track in tracking.tracks)


def test_static_prediction_increases_covariance_and_preserves_mean(settings):
    settings["tracking"]["random_walk_m2_s"] = .1
    tracking = tracker(settings)
    tracking.step(0, [observation([2, 3], 0)])
    old = tracking.tracks[0].covariance.copy()
    tracking.step(2_000_000_000, [])
    np.testing.assert_allclose(tracking.tracks[0].mean, [2, 3])
    np.testing.assert_allclose(tracking.tracks[0].covariance-old, np.eye(2)*.2)
