"""Calibrated acquisition-time camera geometry, independent of ROS."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Observation:
    timestamp_ns: int
    camera_frame: str
    camera_matrix: np.ndarray
    distortion: tuple[float, ...]
    camera_to_reference: np.ndarray
    reference_frame: str
    distortion_model: str = "plumb_bob"
