from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest
from jsonschema.exceptions import ValidationError

from maritime_perception.pipeline import PerceptionPipeline
from maritime_perception.replay import replay_session
from maritime_perception.validation import Unavailable
from perception_synthetic.demo import run
from perception_synthetic.generator import load_scenario


def first_report(settings, events):
    pipeline = PerceptionPipeline(settings)
    for event in events:
        if event["kind"] == "vehicle_state":
            pipeline.add_state(event["data"])
        else:
            report, _ = pipeline.process_frame(event["data"])
            return pipeline, report


def test_analytic_end_to_end_and_no_truth_replay(tmp_path):
    summary = run(load_scenario("analytic"), tmp_path/"demo")
    assert summary["horizontal_error_m"]["max"] < 1e-10
    assert summary["identity_switches"] == 0 and summary["final_confirmed_track_count"] == 3
    (tmp_path/"demo/session/truth.json").unlink()
    replay_session(tmp_path/"demo/session", tmp_path/"replay")
    assert (tmp_path/"replay/reports.jsonl").read_bytes() == (tmp_path/"demo/result/reports.jsonl").read_bytes()


def test_stationary_survey_and_process_independent_determinism(tmp_path):
    summary = run(load_scenario("stationary"), tmp_path/"demo")
    assert summary["final_confirmed_track_count"] == 3
    assert summary["identity_switches"] == summary["mixed_identity_tracks"] == summary["fragmentations"] == 0
    assert .65 < summary["mean_bias_en_m"][0] < .75
    assert -.45 < summary["mean_bias_en_m"][1] < -.35
    assert min(summary["final_min_shared_eigenvalues_m2"]) >= 2.25-1e-7
    assert summary["ambiguous_observations"] >= 1
    assert set(summary["rejection_counts"]) >= {"pose_not_bracketed", "calibration_resolution_mismatch", "pixel_outside_input"}
    assert summary["track_status_counts"]["predicted"] > 0 and summary["track_status_counts"]["stale"] > 0
    assert summary["replay_error_count"] == 0
    # Different process/hash seed catches nondeterministic set/summation order.
    import os
    env = dict(os.environ, PYTHONHASHSEED="91")
    subprocess.run([sys.executable, "-m", "maritime_perception.replay", "--session", str(tmp_path/"demo/session"),
                    "--output", str(tmp_path/"replay")], check=True, capture_output=True, env=env)
    for name in ("reports.jsonl", "observations.jsonl", "replay_errors.jsonl"):
        assert (tmp_path/"replay"/name).read_bytes() == (tmp_path/"demo/result"/name).read_bytes()


@pytest.mark.parametrize("field,value,reason", [("calibration", None, "calibration_unavailable"),
                                              ("water_surface", None, "water_surface_unavailable")])
def test_missing_real_calibration_or_surface_is_explicit(settings, events, field, value, reason):
    settings[field] = value
    settings.update(source_mode="hardware", synthetic=False)
    if settings.get("calibration"):
        settings["calibration"]["synthetic"] = False
    pipeline, report = first_report(settings, events)
    assert report["tracks"] == []
    assert reason in {d.get("reason") for d in report["diagnostics"]}


def test_hardware_never_falls_back_to_synthetic(settings):
    settings["source_mode"] = "hardware"
    with pytest.raises(Unavailable, match="synthetic_configuration_forbidden"):
        PerceptionPipeline(settings)


@pytest.mark.parametrize("mutation", ["units", "covariance", "ellipse", "identity", "time", "coordinates"])
def test_report_boundary_rejects_corruption(settings, events, mutation):
    pipeline, report = first_report(settings, events)
    report = deepcopy(report)
    if mutation == "units":
        report["frame"]["units"] = "degrees"
    elif mutation == "covariance":
        report["tracks"][0]["uncertainty"]["covariance_en_m2"] = None
    elif mutation == "ellipse":
        report["tracks"][0]["uncertainty"]["ellipse_en"]["semi_major_m"] = 0.
    elif mutation == "identity":
        report["tracks"].append(deepcopy(report["tracks"][0]))
    elif mutation == "time":
        report["tracks"][0]["last_observed_at"] = "2030-01-01T00:00:00Z"
    else:
        report["tracks"][0]["position_wgs84"]["latitude_deg"] += .01
    with pytest.raises((Unavailable, ValidationError)):
        pipeline.encoder.validate(report)


def test_unknown_pixel_noise_rejected_and_duplicate_frame_rejected(settings, events):
    frame = deepcopy(next(e["data"] for e in events if e["kind"] == "frame"))
    for detection in frame["detections"]:
        detection["pixel_covariance"] = None
    pipeline = PerceptionPipeline(settings)
    for event in events:
        if event["kind"] == "vehicle_state":
            pipeline.add_state(event["data"])
        else:
            break
    report, _ = pipeline.process_frame(frame)
    assert not report["tracks"]
    assert all(d.get("reason") == "unknown_pixel_covariance" for d in report["diagnostics"])
    with pytest.raises(Unavailable, match="duplicate_or_out_of_sequence"):
        pipeline.process_frame(frame)
