from dataclasses import replace

import cv2
import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from maritime_perception.contracts import PoseEstimate
from maritime_perception.geometry import CameraCalibration, ImageTransform, PlaneProjector
from maritime_perception.validation import Unavailable, rotation


def projector(settings):
    return PlaneProjector(CameraCalibration.from_dict(settings["calibration"]), settings["water_surface"], settings["projection_limits"])


def pose(attitude=None, position=None, reference="body"):
    return PoseEstimate(0, np.array([0., 0., 4.]) if position is None else position,
                        Rotation.identity() if attitude is None else attitude,
                        np.zeros(3), np.zeros(3), {}, reference, (0, 0))


@pytest.mark.parametrize("pixel,heading,expected", [
    ([640, 480], 0, [0, 0]), ([790, 480], 0, [0, -1]),
    ([640, 330], 0, [1, 0]), ([640, 330], 90, [0, 1]),
    ([790, 480], 90, [1, 0]), ([640, 330], 180, [-1, 0])])
def test_analytical_pixels_and_headings(settings, pixel, heading, expected):
    result = projector(settings).project(np.array(pixel, dtype=float), pose(Rotation.from_euler("z", heading, degrees=True)), "rectified")
    np.testing.assert_allclose(result, expected, atol=1e-12)


@pytest.mark.parametrize("axis,expected", [("x", [0., 4*np.tan(np.deg2rad(10))]),
                                           ("y", [-4*np.tan(np.deg2rad(10)), 0.])])
def test_analytical_roll_pitch(settings, axis, expected):
    result = projector(settings).project(np.array([640., 480.]), pose(Rotation.from_euler(axis, 10, degrees=True)), "rectified")
    np.testing.assert_allclose(result, expected, atol=1e-12)


def test_camera_and_antenna_lever_arms(settings):
    settings["calibration"]["camera_in_body_m"] = [.1, .2, .3]
    settings["calibration"]["antenna_in_body_m"] = [-.2, .3, .4]
    p = pose(position=np.array([-.2, .3, 4.4]), reference="antenna")
    np.testing.assert_allclose(projector(settings).project(np.array([640., 480.]), p, "rectified"), [.1, .2], atol=1e-12)


def test_measured_mount_rotation_changes_intersection(settings):
    cal = settings["calibration"]
    cal["optical_to_body_xyzw"] = (Rotation.from_euler("y", 10, degrees=True)*Rotation.from_quat(cal["optical_to_body_xyzw"])).as_quat().tolist()
    np.testing.assert_allclose(projector(settings).project(np.array([640., 480.]), pose(), "rectified"), [-4*np.tan(np.deg2rad(10)), 0], atol=1e-12)


def test_crop_resize_letterbox_coordinates_and_covariance(settings, events):
    frame = next(x["data"] for x in events if x["kind"] == "frame")
    frame["input_image_size"] = [700, 600]
    frame["source_from_input"] = [[2., 0., -20.], [0., 2., -40.], [0., 0., 1.]]
    transform = ImageTransform(frame, CameraCalibration.from_dict(settings["calibration"]))
    pixel, covariance = transform.to_source([330, 260], np.eye(2)*.25)
    np.testing.assert_array_equal(pixel, [640, 480])
    np.testing.assert_array_equal(covariance, np.eye(2))


def test_raw_and_rectified_equivalence(settings):
    settings["calibration"]["distortion"] = [-.1, .01, .001, -.002, 0.]
    p = projector(settings)
    optical = np.array([[.2, -.15, 1.]])
    k = np.array([[600., 0, 640.], [0, 600., 480.], [0, 0, 1.]])
    raw, _ = cv2.projectPoints(optical, np.zeros(3), np.zeros(3), k, np.asarray(settings["calibration"]["distortion"]))
    raw_hit = p.project(raw.reshape(2), pose(), "raw")
    rectified_hit = p.project(np.array([760., 390.]), pose(), "rectified")
    np.testing.assert_allclose(raw_hit, [.6, -.8], atol=1e-8)
    np.testing.assert_allclose(raw_hit, rectified_hit, atol=1e-8)


@pytest.mark.parametrize("q", [[0, 0, 0, 0], [0, 0, 0, 2], [0, float('nan'), 0, 1], [0, 0, 1]])
def test_invalid_quaternions_rejected(q):
    with pytest.raises(Unavailable):
        rotation(q)


@pytest.mark.parametrize("angle,reason", [(180, "nonintersecting_ray"), (89, "ill_conditioned_ray")])
def test_bad_rays(settings, angle, reason):
    with pytest.raises(Unavailable, match=reason):
        projector(settings).project(np.array([640., 480.]), pose(Rotation.from_euler("x", angle, degrees=True)), "rectified")


def test_water_and_range_checks(settings):
    p = projector(settings)
    with pytest.raises(Unavailable, match="camera_not_above_water"):
        p.project(np.array([640., 480.]), pose(position=np.array([0., 0., -1.])), "rectified")
    with pytest.raises(Unavailable, match="range_exceeded"):
        p.project(np.array([640., 480.]), pose(position=np.array([0., 0., 40.])), "rectified")
