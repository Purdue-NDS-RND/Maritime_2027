from dataclasses import replace

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from maritime_perception.contracts import PoseEstimate
from maritime_perception.geometry import CameraCalibration, PlaneProjector
from maritime_perception.uncertainty import ProjectionUncertainty, ellipse
from maritime_perception.validation import covariance, Unavailable


def test_independent_nadir_covariance(settings, events):
    frame = next(e["data"] for e in events if e["kind"] == "frame")
    pose = PoseEstimate(frame["stamp_ns"], np.array([0., 0., 4.]), Rotation.identity(), np.zeros(3), np.zeros(3), {}, "body", (0, 0))
    projector = PlaneProjector(CameraCalibration.from_dict(settings["calibration"]), settings["water_surface"], settings["projection_limits"])
    result = ProjectionUncertainty(projector).propagate(np.array([640., 480.]), np.eye(2)*.25, pose, frame,
                                                      {"id": "test", "class_id": "buoy"}, settings["clocks"]["survey_utc"])
    np.testing.assert_allclose(result.covariance, np.eye(2)*(4/600)**2*.25, rtol=1e-7)


def test_propagation_against_seeded_monte_carlo(settings, events):
    frame = next(e["data"] for e in events if e["kind"] == "frame")
    factor = np.diag([.02, .03, .01, .0008, .001, .0015])
    pose = PoseEstimate(frame["stamp_ns"], np.array([.2, -.1, 4.]), Rotation.from_euler("xyz", [.05, -.04, .3]),
                        np.zeros(3), np.zeros(3), {"navigation:test": factor}, "body", (0, 0))
    projector = PlaneProjector(CameraCalibration.from_dict(settings["calibration"]), settings["water_surface"], settings["projection_limits"])
    pixel = np.array([760., 550.])
    result = ProjectionUncertainty(projector).propagate(pixel, np.eye(2)*.64, pose, frame,
                                                      {"id": "test", "class_id": "buoy"}, settings["clocks"]["survey_utc"])
    rng = np.random.default_rng(73)
    hits = []
    for _ in range(5000):
        error = factor @ rng.standard_normal(6)
        noisy_pose = replace(pose, position=pose.position+error[:3], attitude=Rotation.from_rotvec(error[3:])*pose.attitude)
        hits.append(projector.project(pixel+rng.normal(0., .8, 2), noisy_pose, "raw"))
    empirical = np.cov(np.asarray(hits).T)
    # 5000 independent samples: this 8% matrix tolerance exceeds sampling variability.
    assert np.linalg.norm(empirical-result.covariance)/np.linalg.norm(result.covariance) < .08


def test_ellipse_probability_orientation_and_isotropy():
    result = ellipse(np.diag([9., 1.]))
    assert result["semi_major_m"] == pytest.approx(3*2.44774683068)
    assert result["semi_minor_m"] == pytest.approx(2.44774683068)
    assert result["angle_ccw_from_east_rad"] == pytest.approx(0.)
    assert ellipse(np.eye(2))["angle_ccw_from_east_rad"] is None
    angle = np.pi/4
    rot = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    assert ellipse(rot @ np.diag([9, 1]) @ rot.T)["angle_ccw_from_east_rad"] == pytest.approx(angle)
    rng = np.random.default_rng(81)
    data = rng.normal(size=(20000, 2))
    inside = np.mean(np.sum(data**2, axis=1) <= result["semi_minor_m"]**2)
    # Binomial standard error is .00154; tolerance .008 is over five standard errors.
    assert abs(inside-.95) < .008


@pytest.mark.parametrize("matrix", [None, [[-1., 0], [0, 1]], [[1, .5], [0, 1]], [[1, 0], [0, float('nan')]]])
def test_unknown_or_invalid_covariance(matrix):
    with pytest.raises(Unavailable):
        covariance(matrix, 2)
