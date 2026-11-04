"""Source-neutral records. Position/rotation errors use ENU translation/left rotation."""
from dataclasses import dataclass

import numpy as np

from .validation import Unavailable, array, covariance, rotation, timestamp


@dataclass(frozen=True)
class VehicleState:
    stamp_ns: int
    origin_id: str
    epoch_id: str
    position: np.ndarray
    attitude: object
    velocity: np.ndarray
    angular_velocity: np.ndarray
    sample_cov: np.ndarray
    shared_cov: np.ndarray
    shared_id: str
    position_reference: str
    clock_id: str

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise Unavailable("invalid_vehicle_state")
        if data.get("frame_id") != "survey_enu" or data.get("body_frame") != "FLU":
            raise Unavailable("unsupported_state_frame")
        if not isinstance(data.get("quality"), dict) or not all(data["quality"].get(key) is True for key in ("position_valid", "heading_valid", "height_valid")):
            raise Unavailable("invalid_state_quality")
        if data.get("position_reference") not in ("body", "antenna"):
            raise Unavailable("unknown_position_reference")
        for key in ("origin_id", "epoch_id", "shared_model_id", "clock_id"):
            if not isinstance(data.get(key), str) or not data[key]:
                raise Unavailable("missing_" + key)
        return cls(timestamp(data["stamp_ns"]), data["origin_id"], data["epoch_id"],
                   array(data["position_enu_m"], (3,), "position"), rotation(data["quaternion_xyzw"]),
                   array(data["velocity_enu_m_s"], (3,), "velocity"),
                   array(data["angular_velocity_enu_rad_s"], (3,), "angular_velocity"),
                   covariance(data.get("sample_pose_covariance"), 6, "pose_covariance"),
                   covariance(data.get("shared_pose_covariance"), 6, "shared_pose_covariance"),
                   data["shared_model_id"], data["position_reference"], data["clock_id"])


@dataclass(frozen=True)
class PoseEstimate:
    stamp_ns: int
    position: np.ndarray
    attitude: object
    velocity: np.ndarray
    angular_velocity: np.ndarray
    factors: dict
    position_reference: str
    sample_stamps: tuple


@dataclass(frozen=True)
class Observation:
    detection_id: str
    class_id: str
    stamp_ns: int
    mean: np.ndarray
    independent_cov: np.ndarray
    factors: dict
    frame_id: str
    calibration_id: str

    @property
    def covariance(self):
        from .validation import factors_covariance
        return self.independent_cov + factors_covariance(self.factors)
