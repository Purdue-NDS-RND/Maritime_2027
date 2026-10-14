"""Pure camera-contract checks shared by diagnostics and focused tests."""

from __future__ import annotations

import math


OPTICAL_FRAME = "camera_0_optical_frame"
MATCH_TOLERANCE_NS = 0
MAX_ACQUISITION_AGE_NS = 100_000_000
MAX_ARRIVAL_SILENCE_NS = 2_000_000_000


def stamp_ns(message) -> int:
    return message.header.stamp.sec * 1_000_000_000 + message.header.stamp.nanosec


def validate_image(message, depth=False) -> str | None:
    expected = "32FC1" if depth else ("rgb8", "bgr8")
    if message.header.frame_id != OPTICAL_FRAME:
        return "frame_mismatch"
    if message.width <= 0 or message.height <= 0 or message.step <= 0:
        return "invalid_dimensions"
    if len(message.data) != message.step * message.height:
        return "invalid_data_layout"
    if depth and message.encoding != expected:
        return "unsupported_encoding"
    if not depth and message.encoding not in expected:
        return "unsupported_encoding"
    if depth:
        if message.step != message.width * 4:
            return "invalid_data_layout"
    return None


def validate_camera_info(message) -> str | None:
    if message.header.frame_id != OPTICAL_FRAME:
        return "frame_mismatch"
    if message.width <= 0 or message.height <= 0:
        return "invalid_dimensions"
    coefficient_counts = {"plumb_bob": 5, "rational_polynomial": 8, "equidistant": 4}
    if message.distortion_model not in coefficient_counts:
        return "invalid_calibration"
    if len(message.d) != coefficient_counts[message.distortion_model]:
        return "invalid_calibration"
    values = (*message.d, *message.k, *message.r, *message.p)
    if not all(math.isfinite(value) for value in values):
        return "invalid_calibration"
    if not (
        message.k[0] > 0 and message.k[4] > 0 and message.k[8] == 1
        and message.p[0] > 0 and message.p[5] > 0 and message.p[10] == 1
    ):
        return "invalid_calibration"
    return None


def freshness(header_ns, arrival_ns, ros_now_ns, steady_now_ns):
    acquisition_age = ros_now_ns - header_ns
    arrival_silence = steady_now_ns - arrival_ns
    if acquisition_age < 0:
        return "ERROR", "future_acquisition_stamp"
    if arrival_silence < 0:
        return "ERROR", "steady_clock_regression"
    if acquisition_age > MAX_ACQUISITION_AGE_NS:
        return "STALE", "acquisition_timeout"
    if arrival_silence > MAX_ARRIVAL_SILENCE_NS:
        return "STALE", "arrival_timeout"
    return "OK", "ready"
