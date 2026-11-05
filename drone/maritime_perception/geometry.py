"""OpenCV camera model plus the narrow analytic horizontal-plane fallback."""
from dataclasses import dataclass

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from .validation import Unavailable, array, covariance, finite_nonnegative, rotation


@dataclass(frozen=True)
class CameraCalibration:
    calibration_id: str
    width: int
    height: int
    intrinsics: np.ndarray
    distortion: np.ndarray
    optical_to_body: object
    camera_in_body: np.ndarray
    antenna_in_body: np.ndarray
    intrinsics_cov: np.ndarray
    mount_cov: np.ndarray
    synthetic: bool

    @classmethod
    def from_dict(cls, data):
        if not data or not data.get("calibration_id"):
            raise Unavailable("calibration_unavailable")
        if data.get("distortion_model") != "plumb_bob":
            raise Unavailable("unsupported_distortion_model")
        if type(data.get("synthetic")) is not bool:
            raise Unavailable("missing_calibration_provenance")
        width, height = data["width"], data["height"]
        if type(width) is not int or type(height) is not int or min(width, height) <= 0:
            raise Unavailable("invalid_image_size")
        intrinsics = array(data["fx_fy_cx_cy"], (4,), "intrinsics")
        if min(intrinsics[:2]) <= 0:
            raise Unavailable("invalid_intrinsics")
        return cls(data["calibration_id"], width, height, intrinsics,
                   array(data["distortion"], (5,), "distortion"), rotation(data["optical_to_body_xyzw"]),
                   array(data["camera_in_body_m"], (3,), "camera_offset"),
                   array(data["antenna_in_body_m"], (3,), "antenna_offset"),
                   covariance(data.get("intrinsics_covariance"), 4, "intrinsics_covariance"),
                   covariance(data.get("mount_covariance"), 6, "mount_covariance"), data["synthetic"])


class ImageTransform:
    def __init__(self, frame, calibration):
        if frame["calibration_id"] != calibration.calibration_id:
            raise Unavailable("calibration_id_mismatch")
        if frame["source_image_size"] != [calibration.width, calibration.height]:
            raise Unavailable("calibration_resolution_mismatch")
        self.size = frame["input_image_size"]
        if len(self.size) != 2 or any(type(x) is not int or x <= 0 for x in self.size):
            raise Unavailable("invalid_input_image_size")
        self.matrix = array(frame["source_from_input"], (3, 3), "pixel_transform")
        if not np.allclose(self.matrix[2], [0, 0, 1]) or abs(np.linalg.det(self.matrix[:2, :2])) < 1e-12:
            raise Unavailable("invalid_pixel_transform")

    def to_source(self, pixel, cov):
        pixel = array(pixel, (2,), "pixel")
        if np.any(pixel < 0) or np.any(pixel >= self.size):
            raise Unavailable("pixel_outside_input")
        restored = (self.matrix @ np.r_[pixel, 1])[:2]
        linear = self.matrix[:2, :2]
        return restored, linear @ covariance(cov, 2, "pixel_covariance", positive=True) @ linear.T


class CameraGeometry:
    @staticmethod
    def ray(pixel, intrinsics, distortion, image_domain):
        fx, fy, cx, cy = intrinsics
        if image_domain == "rectified":
            xy = (pixel-np.array([cx, cy]))/np.array([fx, fy])
        elif image_domain == "raw":
            k = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1.]])
            xy = cv2.undistortPoints(np.asarray(pixel, dtype=float).reshape(1, 1, 2), k, distortion).reshape(2)
        else:
            raise Unavailable("unknown_image_domain")
        ray = np.r_[xy, 1.]
        return ray/np.linalg.norm(ray)


class PlaneProjector:
    def __init__(self, calibration, water, limits):
        self.calibration = calibration
        if not water or water.get("model") != "horizontal_plane":
            raise Unavailable("water_surface_unavailable")
        self.height = float(water["up_m"])
        if not np.isfinite(self.height) or not water.get("model_id"):
            raise Unavailable("invalid_water_surface")
        self.water_id = water["model_id"]
        self.water_sigma = finite_nonnegative(water["shared_sigma_m"], "water_sigma")
        self.min_down = float(limits["minimum_down_cosine"])
        self.max_range = float(limits["maximum_range_m"])
        if not 0 < self.min_down <= 1 or not 0 < self.max_range < np.inf:
            raise Unavailable("invalid_projection_limits")

    def project(self, pixel, pose, image_domain, delta=None):
        """20 parameters: pixel2, pose6, K4, mount6, water1, clock1."""
        d = np.zeros(20) if delta is None else array(delta, (20,), "perturbation")
        cal = self.calibration
        attitude = Rotation.from_rotvec(d[5:8] + pose.angular_velocity*d[19])*pose.attitude
        position = pose.position+d[2:5]+pose.velocity*d[19]
        mount = Rotation.from_rotvec(d[15:18])*cal.optical_to_body
        offset = cal.camera_in_body+d[12:15]
        if pose.position_reference == "antenna":
            offset = offset-cal.antenna_in_body
        centre = position+attitude.apply(offset)
        ray = attitude.apply(mount.apply(CameraGeometry.ray(pixel+d[:2], cal.intrinsics+d[8:12], cal.distortion, image_domain)))
        water = self.height+d[18]
        if not np.isfinite(centre).all() or not np.isfinite(ray).all():
            raise Unavailable("nonfinite_projection")
        if centre[2] <= water:
            raise Unavailable("camera_not_above_water")
        if ray[2] >= 0:
            raise Unavailable("nonintersecting_ray")
        if -ray[2] < self.min_down:
            raise Unavailable("ill_conditioned_ray")
        distance = (water-centre[2])/ray[2]
        if distance > self.max_range:
            raise Unavailable("range_exceeded")
        return (centre+distance*ray)[:2]
