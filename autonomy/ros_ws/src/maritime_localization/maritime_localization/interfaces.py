"""Shared input/output for positioning methods, independent of ROS and simulation."""

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
    depth_m: np.ndarray | None = None  # Latest registered depth; no time matching yet.
    camera_to_reference: np.ndarray | None = None  # Latest received vessel pose + mounting transform.
    reference_frame: str | None = None
    distortion_model: str = "plumb_bob"


@dataclass(frozen=True)
class PositionEstimate:
    timestamp_ns: int
    frame_id: str
    category: str
    position_m: tuple[float, float]  # XY in frame_id, metres.
    track_id: str | None = None  # Assigned by association, never the marker ID.
