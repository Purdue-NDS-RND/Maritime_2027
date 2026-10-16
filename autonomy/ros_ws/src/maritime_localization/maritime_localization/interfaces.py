"""Shared input/output for future methods, independent of ROS and simulation."""

from dataclasses import dataclass

import numpy as np

from maritime_perception.aruco import BoundingBox


@dataclass(frozen=True)
class Observation:
    timestamp_ns: int
    camera_frame: str
    boxes: tuple[BoundingBox, ...]
    camera_matrix: np.ndarray  # 3x3 intrinsics; pixel distortion must be handled.
    distortion: tuple[float, ...]
    depth_m: np.ndarray | None = None  # Registered to this exact RGB frame.
    camera_to_reference: np.ndarray | None = None  # 4x4 pose at image capture time.
    reference_frame: str | None = None


@dataclass(frozen=True)
class PositionEstimate:
    timestamp_ns: int
    frame_id: str
    category: str
    position_m: tuple[float, float, float]
    track_id: str | None = None  # Assigned by association, never the marker ID.
