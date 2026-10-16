"""Camera geometry shared by both methods; no marker-size or pose APIs."""

import cv2
import numpy as np


def validate_observation(observation):
    matrix = np.asarray(observation.camera_matrix, dtype=float)
    transform = np.asarray(observation.camera_to_reference, dtype=float)
    if (matrix.shape != (3, 3) or not np.isfinite(matrix).all()
            or matrix[0, 0] <= 0 or matrix[1, 1] <= 0):
        raise ValueError("Expected finite calibrated camera intrinsics")
    if (not observation.reference_frame or transform.shape != (4, 4)
            or not np.isfinite(transform).all()
            or not np.allclose(transform[3], [0, 0, 0, 1])
            or not np.allclose(transform[:3, :3].T @ transform[:3, :3], np.eye(3), atol=1e-6)
            or not np.isclose(np.linalg.det(transform[:3, :3]), 1.)):
        raise ValueError("Expected a rigid camera-to-reference transform and named frame")
    if observation.distortion_model not in ("", "plumb_bob", "rational_polynomial", "equidistant"):
        raise ValueError(f"Unsupported distortion model: {observation.distortion_model}")
    if not np.isfinite(observation.distortion).all():
        raise ValueError("Distortion coefficients must be finite")


def camera_ray(observation, box):
    """Unnormalized optical ray [x/z, y/z, 1] through the box center."""
    if (not np.isfinite([box.center_x, box.center_y, box.width, box.height]).all()
            or box.width <= 0 or box.height <= 0):
        return None
    pixel = np.array([[[box.center_x, box.center_y]]], dtype=np.float64)
    distortion = np.asarray(observation.distortion, dtype=float)
    if observation.distortion_model == "equidistant":
        if distortion.size != 4:
            raise ValueError("Equidistant cameras require four distortion coefficients")
        xy = cv2.fisheye.undistortPoints(pixel, observation.camera_matrix, distortion)
    else:
        xy = cv2.undistortPoints(pixel, observation.camera_matrix, distortion if distortion.size else None)
    ray = np.array([*xy.reshape(2), 1.])
    return ray if np.isfinite(ray).all() else None


def angle(first, second):
    """Angle in radians between unit vectors."""
    return float(np.arccos(np.clip(np.dot(first, second), -1., 1.)))


def rigid_transform(position, quaternion):
    """Homogeneous transform from a ROS position/translation and quaternion."""
    xyz = np.array([position.x, position.y, position.z], dtype=float)
    q = np.array([quaternion.x, quaternion.y, quaternion.z, quaternion.w], dtype=float)
    norm = np.linalg.norm(q)
    if not np.isfinite(xyz).all() or not np.isfinite(q).all() or norm < 1e-12:
        raise ValueError("Pose must have finite coordinates and a nonzero quaternion")
    x, y, z, w = q / norm
    matrix = np.eye(4)
    matrix[:3, :3] = [
        [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
        [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
        [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)],
    ]
    matrix[:3, 3] = xyz
    return matrix
