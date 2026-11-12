from copy import deepcopy

import numpy as np
import pytest

from maritime_perception.pipeline import PerceptionPipeline
from maritime_perception.validation import Unavailable, parse_utc, utc


def prepare(settings, events):
    pipeline = PerceptionPipeline(settings)
    for event in events:
        if event["kind"] == "vehicle_state":
            pipeline.add_state(event["data"])
        else:
            return pipeline, deepcopy(event["data"])


@pytest.mark.parametrize("value", [float('nan'), float('inf')])
def test_nonfinite_pixels_never_produce_a_location(settings, events, value):
    pipeline, frame = prepare(settings, events)
    frame["detections"] = [frame["detections"][0]]
    frame["detections"][0]["pixel_uv"] = [value, 480.]
    report, _ = pipeline.process_frame(frame)
    assert report["tracks"] == []
    assert report["diagnostics"][0]["reason"] == "invalid_pixel"


@pytest.mark.parametrize("field,value,reason", [
    ("stamp_semantics", "host_arrival", "exposure_time_unavailable"),
    ("origin_id", "changed", "frame_origin_mismatch"),
    ("calibration_id", "missing", "calibration_id_mismatch")])
def test_frame_metadata_is_not_silently_assumed(settings, events, field, value, reason):
    pipeline, frame = prepare(settings, events)
    frame[field] = value
    report, _ = pipeline.process_frame(frame)
    assert not report["tracks"]
    assert report["diagnostics"][0]["reason"] == reason


def test_missing_heading_rejects_vehicle_state(settings, events):
    pipeline = PerceptionPipeline(settings)
    frame = None
    for event in events:
        if event["kind"] == "vehicle_state":
            data = deepcopy(event["data"])
            data["quality"]["heading_valid"] = False
            pipeline.add_state(data)
        else:
            frame = event["data"]
            break
    report, _ = pipeline.process_frame(frame)
    assert not report["tracks"]
    assert {d["reason"] for d in report["diagnostics"]} == {"invalid_state_quality", "pose_not_bracketed"}


def test_unmapped_clock_and_bad_timestamps_fail_without_fake_epoch(settings, events):
    pipeline, frame = prepare(settings, events)
    frame["clock_id"] = "unmapped_camera_clock"
    with pytest.raises(Unavailable, match="unmapped_clock"):
        pipeline.process_frame(frame)
    frame["clock_id"] = "survey_utc"
    frame["stamp_ns"] = float('nan')
    with pytest.raises(Unavailable, match="invalid_timestamp"):
        pipeline.process_frame(frame)


def test_nanosecond_report_times_are_exact_and_calendar_validated():
    stamp = 1_793_804_400_123_456_789
    assert parse_utc(utc(stamp)) == stamp
    with pytest.raises(Unavailable):
        parse_utc("2026-02-30T15:00:00.000000000Z")


@pytest.mark.parametrize("field,value", [("id", None), ("id", []), ("detections", None)])
def test_malformed_frame_envelopes_are_unavailable(settings, events, field, value):
    pipeline, frame = prepare(settings, events)
    frame[field] = value
    with pytest.raises(Unavailable):
        pipeline.process_frame(frame)


def test_malformed_state_and_detection_are_rejected_without_crashing(settings, events):
    pipeline, frame = prepare(settings, events)
    pipeline.add_state(None)
    frame["detections"] = [None]
    report, _ = pipeline.process_frame(frame)
    assert not report["tracks"]
    assert {d["reason"] for d in report["diagnostics"]} == {"invalid_vehicle_state", "invalid_detection"}
