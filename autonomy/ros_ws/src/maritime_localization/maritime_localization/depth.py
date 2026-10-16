"""Registered optical-Z depth near each box center, transformed into map XY."""

from dataclasses import dataclass

import numpy as np

from maritime_localization.geometry import camera_ray, validate_observation
from maritime_localization.interfaces import Observation, PositionEstimate


@dataclass(frozen=True)
class DepthSettings:
    min_depth_m: float = 0.2
    max_depth_m: float = 80.0
    patch_fraction: float = 0.25  # Central quarter of box width/height.
    min_valid_pixels: int = 3
    min_valid_fraction: float = 0.5
    max_depth_spread_m: float = 0.5  # Reject mixed surfaces (90th - 10th percentile).

    def __post_init__(self):
        if (not np.isfinite(list(vars(self).values())).all() or not 0 < self.min_depth_m < self.max_depth_m
                or not 0 < self.patch_fraction <= 1 or self.min_valid_pixels < 1
                or not 0 < self.min_valid_fraction <= 1 or self.max_depth_spread_m <= 0):
            raise ValueError("Invalid depth settings")


class DepthLocalizer:
    implemented = True

    def __init__(self, settings=None):
        self.settings = settings or DepthSettings()

    def reset(self):
        """This method returns independent measurements and has no track state."""

    def process(self, observation: Observation) -> list[PositionEstimate]:
        validate_observation(observation)
        depth = observation.depth_m
        if depth is None or depth.ndim != 2:
            raise ValueError("Depth positioning requires registered optical-Z depth in metres")
        height, width = depth.shape
        settings = self.settings
        estimates = []
        for box in observation.boxes:
            ray = camera_ray(observation, box)
            if ray is None or not (0 <= box.center_x < width and 0 <= box.center_y < height):
                continue
            half_x = max(0.5, box.width * settings.patch_fraction / 2)
            half_y = max(0.5, box.height * settings.patch_fraction / 2)
            left, right = max(0, int(np.ceil(box.center_x-half_x))), min(width, int(np.floor(box.center_x+half_x))+1)
            top, bottom = max(0, int(np.ceil(box.center_y-half_y))), min(height, int(np.floor(box.center_y+half_y))+1)
            patch = depth[top:bottom, left:right]
            valid = patch[np.isfinite(patch) & (patch >= settings.min_depth_m) & (patch <= settings.max_depth_m)]
            if (valid.size < settings.min_valid_pixels
                    or valid.size < settings.min_valid_fraction * patch.size):
                continue
            if np.percentile(valid, 90) - np.percentile(valid, 10) > settings.max_depth_spread_m:
                continue
            # Registered depth is optical Z, not distance along a unit ray.
            point = observation.camera_to_reference @ np.append(ray * float(np.median(valid)), 1.)
            estimates.append(PositionEstimate(observation.timestamp_ns, observation.reference_frame,
                                               box.category, (float(point[0]), float(point[1]))))
        return estimates
