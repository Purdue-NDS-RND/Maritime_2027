"""ROS/Kalibr pinhole intrinsics, with explicit image-domain and resize geometry."""
import hashlib
import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

import cv2
import numpy as np
import yaml

from ..validation import Unavailable, array


def builtin_calibration(name="arducam_info.yaml"):
    return files("maritime_perception").joinpath("config", name)


@dataclass(frozen=True)
class Intrinsics:
    width: int
    height: int
    k: np.ndarray
    d: np.ndarray
    provenance: dict

    @classmethod
    def load(cls, path):
        raw = Path(path).read_bytes()
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            raise Unavailable("invalid_camera_calibration")
        if "cam0" in data:
            cam = data["cam0"]
            if cam["camera_model"] != "pinhole" or cam["distortion_model"] != "radtan":
                raise Unavailable("unsupported_camera_calibration")
            width, height = cam["resolution"]
            fx, fy, cx, cy = cam["intrinsics"]
            k = [[fx, 0., cx], [0., fy, cy], [0., 0., 1.]]
            d = list(cam["distortion_coeffs"])
            if len(d) != 4:
                raise Unavailable("unsupported_kalibr_distortion")
            d.append(0.)
        else:
            if data.get("distortion_model") != "plumb_bob":
                raise Unavailable("unsupported_camera_calibration")
            width, height = data["image_width"], data["image_height"]
            k = array(data["camera_matrix"]["data"], (9,), "camera_matrix").reshape(3, 3)
            d = data["distortion_coefficients"]["data"]
            r = data.get("rectification_matrix", {}).get("data", np.eye(3).reshape(-1))
            if not np.allclose(array(r, (9,), "rectification_matrix").reshape(3, 3), np.eye(3)):
                raise Unavailable("nonidentity_rectification_not_supported")
        if type(width) is not int or type(height) is not int or min(width, height) <= 0:
            raise Unavailable("invalid_calibration_size")
        k, d = array(k, (3, 3), "camera_matrix"), array(d, (5,), "distortion")
        if min(k[0, 0], k[1, 1]) <= 0 or not np.allclose(k[2], [0., 0., 1.]) or k[0, 1] != 0 or k[1, 0] != 0:
            raise Unavailable("unsupported_camera_matrix")
        return cls(width, height, k, d, {"file_name": Path(path).name,
                   "sha256": hashlib.sha256(raw).hexdigest(), "lens_mode_verified": False})

    def for_capture(self, size, roi=None):
        if roi is None:
            if list(size) != [self.width, self.height]:
                raise Unavailable("calibration_mode_transform_required")
            return self
        x, y, width, height = array(roi, (4,), "calibration_roi")
        if min(x, y) < 0 or min(width, height) <= 0 or x+width > self.width or y+height > self.height:
            raise Unavailable("invalid_calibration_roi")
        sx, sy = size[0]/width, size[1]/height
        # OpenCV resize pixel-centre convention; ROI is in calibration-image pixels.
        transform = np.array([[sx, 0., sx*(.5-x)-.5], [0., sy, sy*(.5-y)-.5], [0., 0., 1.]])
        return Intrinsics(*size, transform @ self.k, self.d.copy(),
                          dict(self.provenance, reference_roi=list(roi),
                               reference_size=[self.width, self.height], mode_transform="caller_declared_crop_resize"))


class ImageProcessor:
    def __init__(self, intrinsics, capture_size, output_size, *, rectify=False, alpha=0.):
        self.capture_size, self.output_size = list(capture_size), list(output_size)
        self.rectify, self.maps = rectify, None
        self.intrinsics = intrinsics
        self.roi = None
        self.model = None
        if rectify and intrinsics is None:
            raise Unavailable("rectification_requires_calibration")
        if intrinsics is not None:
            k, d = intrinsics.k.copy(), intrinsics.d.copy()
            if rectify:
                k, roi = cv2.getOptimalNewCameraMatrix(k, d, tuple(capture_size), alpha, tuple(capture_size))
                self.roi = [int(v) for v in roi]
                self.maps = cv2.initUndistortRectifyMap(intrinsics.k, d, None, k, tuple(capture_size), cv2.CV_16SC2)
                d = np.zeros(5)
            sx, sy = output_size[0]/capture_size[0], output_size[1]/capture_size[1]
            resize = np.array([[sx, 0., (sx-1)/2], [0., sy, (sy-1)/2], [0., 0., 1.]])
            k = resize @ k
            # Stable identity distinguishes domain, alpha, mode transform and delivered size.
            model = dict(width=output_size[0], height=output_size[1], camera_matrix=k.tolist(),
                         distortion=d.tolist(), distortion_model="plumb_bob",
                         image_domain="rectified" if rectify else "raw",
                         provenance=intrinsics.provenance, rectify_alpha=alpha if rectify else None,
                         capture_size=self.capture_size, rectification_valid_roi_capture_px=self.roi)
            model["calibration_id"] = "camera_" + hashlib.sha256(json.dumps(model, sort_keys=True).encode()).hexdigest()[:20]
            self.model = model

    def process(self, image):
        if image is None or image.dtype != np.uint8 or image.shape != (self.capture_size[1], self.capture_size[0], 3):
            raise Unavailable("negotiated_camera_resolution_mismatch")
        if self.maps is not None:
            image = cv2.remap(image, *self.maps, interpolation=cv2.INTER_LINEAR)
        if self.output_size != self.capture_size:
            image = cv2.resize(image, tuple(self.output_size), interpolation=cv2.INTER_LINEAR)
        return image

    def camera_info(self):
        if self.model is None:
            # ROS's K[0] == 0 explicitly indicates an uncalibrated camera.
            return dict(width=self.output_size[0], height=self.output_size[1],
                        k=[0.]*9, d=[], r=np.eye(3).reshape(-1).tolist(), p=[0.]*12, distortion_model="plumb_bob")
        k = np.asarray(self.model["camera_matrix"])
        return dict(width=self.output_size[0], height=self.output_size[1], k=k.reshape(-1).tolist(),
                    d=self.model["distortion"], r=np.eye(3).reshape(-1).tolist(),
                    p=np.column_stack((k, np.zeros(3))).reshape(-1).tolist(), distortion_model="plumb_bob")
