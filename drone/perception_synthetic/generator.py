"""Small seeded forward camera model. Truth is written separately from input events."""
import json
from pathlib import Path

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from maritime_perception.replay import line, write_json
from maritime_perception.validation import Unavailable, load_json


EPOCH_NS = 1_793_804_400_000_000_000  # 2026-11-04T15:00:00Z


def diagonal(sigmas):
    return np.diag(np.square(sigmas)).tolist()


def calibration():
    mount = Rotation.from_matrix([[0., -1., 0.], [-1., 0., 0.], [0., 0., -1.]])
    return {"calibration_id": "synthetic_imx519_like_v1", "synthetic": True,
            "width": 1280, "height": 960, "fx_fy_cx_cy": [600., 600., 640., 480.],
            "distortion_model": "plumb_bob", "distortion": [-.03, .002, .0001, -.0002, 0.],
            "optical_to_body_xyzw": mount.as_quat().tolist(),
            "camera_in_body_m": [.12, -.03, -.08], "antenna_in_body_m": [-.05, 0., .1],
            "intrinsics_covariance": diagonal([.2, .2, .1, .1]),
            "mount_covariance": diagonal([.003]*3+[.001]*3)}


def true_pose(t, analytic):
    if analytic:
        return np.array([0., 0., 4.]), Rotation.identity()
    position = np.array([.45*np.sin(t/3), .35*np.cos(t/3), 4.+.05*np.sin(t/4)])
    attitude = Rotation.from_euler("xyz", [.02*np.sin(t/4), .015*np.cos(t/4), .045*t])
    return position, attitude


def state_at(t, scenario, cal, rng):
    position, attitude = true_pose(t, scenario["analytic"])
    eps = 1e-3
    before, rb = true_pose(t-eps, scenario["analytic"])
    after, ra = true_pose(t+eps, scenario["analytic"])
    velocity = (after-before)/(2*eps)
    angular_velocity = (ra*rb.inv()).as_rotvec()/(2*eps)
    if scenario["analytic"]:
        pos_sigma = att_sigma = 0.
        shared_sigma = heading_sigma = 0.
    else:
        pos_sigma = scenario["sample_position_sigma_m"]
        att_sigma = np.deg2rad(scenario["sample_attitude_sigma_deg"])
        shared_sigma = scenario["shared_position_sigma_m"]
        heading_sigma = np.deg2rad(scenario["shared_heading_sigma_deg"])
    # This input is antenna position; the inverse must remove its lever arm.
    antenna = position+attitude.apply(cal["antenna_in_body_m"])
    velocity = velocity+np.cross(angular_velocity, attitude.apply(cal["antenna_in_body_m"]))
    observed_position = antenna+np.asarray(scenario["shared_offset_m"])+rng.normal(0., pos_sigma, 3)
    observed_attitude = Rotation.from_rotvec(rng.normal(0., att_sigma, 3)+[0., 0., np.deg2rad(scenario["shared_heading_bias_deg"])])*attitude
    return {"stamp_ns": EPOCH_NS+round(t*1e9), "frame_id": "survey_enu", "body_frame": "FLU",
            "origin_id": "synthetic_origin", "epoch_id": "synthetic_epoch_1", "clock_id": "survey_utc",
            "position_reference": "antenna", "position_enu_m": observed_position.tolist(),
            "quaternion_xyzw": observed_attitude.as_quat().tolist(),
            "velocity_enu_m_s": velocity.tolist(), "angular_velocity_enu_rad_s": angular_velocity.tolist(),
            "sample_pose_covariance": diagonal([pos_sigma]*3+[att_sigma]*3),
            "shared_pose_covariance": diagonal([shared_sigma, shared_sigma, 0., 0., 0., heading_sigma]),
            "shared_model_id": "standalone_gnss_session_1",
            "quality": {"position_valid": True, "heading_valid": True, "height_valid": True}}


def forward_pixel(point, position, attitude, cal):
    """World target -> optical point -> OpenCV projection (not inverse pipeline)."""
    camera = position+attitude.apply(cal["camera_in_body_m"])
    optical = Rotation.from_quat(cal["optical_to_body_xyzw"]).inv().apply(attitude.inv().apply(np.asarray(point)-camera))
    if optical[2] <= 0:
        return None
    fx, fy, cx, cy = cal["fx_fy_cx_cy"]
    k = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1.]])
    pixel, _ = cv2.projectPoints(optical.reshape(1, 3), np.zeros(3), np.zeros(3), k, np.asarray(cal["distortion"]))
    return pixel.reshape(2)


def generate(scenario, output):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise Unavailable("session_directory_must_be_empty")
    output.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(scenario["seed"])
    cal = calibration()
    if scenario["analytic"]:
        cal["camera_in_body_m"] = [0., 0., 0.]
        cal["antenna_in_body_m"] = [0., 0., 0.]
        cal["distortion"] = [0.]*5
        cal["intrinsics_covariance"] = np.zeros((4, 4)).tolist()
        cal["mount_covariance"] = np.zeros((6, 6)).tolist()
    settings = {"survey_id": "synthetic_"+scenario["name"], "source_mode": "synthetic", "synthetic": True,
                "origin": {"origin_id": "synthetic_origin", "latitude_deg": 40., "longitude_deg": -86.,
                           "ellipsoid_height_m": 200., "provenance": "synthetic_configured_coordinate"},
                "calibration": cal,
                "water_surface": {"model": "horizontal_plane", "up_m": scenario["assumed_water_up_m"],
                                  "shared_sigma_m": scenario["water_sigma_m"], "model_id": "synthetic_water_1"},
                "clocks": {"survey_utc": {"reference_ns": EPOCH_NS, "offset_ns": 0, "drift_ppm": 0.,
                                          "independent_sigma_s": 0., "shared_sigma_s": 0. if scenario["analytic"] else .005,
                                          "mapping_id": "synthetic_clock_1"}},
                "max_pose_gap_s": .21, "pose_history_s": 30.,
                "projection_limits": {"minimum_down_cosine": .25, "maximum_range_m": 30.},
                "tracking": {"random_walk_m2_s": scenario["random_walk_m2_s"], "stale_after_s": 1.5,
                             "confirm_hits": 2, "maximum_tracks": 32, "gate_probability": .999,
                             "ambiguity_cost_margin": .5}}
    write_json(output/"config.json", settings)
    truth = {"scenario": scenario, "targets": scenario["targets"], "detections": {}, "frames": {}}
    states_until = -1
    with (output/"measurements.jsonl").open("w") as stream:
        for index in range(scenario["frames"]):
            t = .05+index*scenario["frame_period_s"]
            end = int(np.ceil(t/.1))
            for state_index in range(states_until+1, end+1):
                stream.write(line({"kind": "vehicle_state", "data": state_at(state_index*.1, scenario, cal, rng)}))
            states_until = end
            position, attitude = true_pose(t, scenario["analytic"])
            detections = []
            frame_id = f"frame_{index:04d}"
            for target_index, target in enumerate(scenario["targets"]):
                if not scenario["analytic"] and target_index == 1 and 18 <= index <= 24:
                    continue
                pixel = forward_pixel(target["position_enu_m"], position, attitude, cal)
                if pixel is None or np.any(pixel < 0) or np.any(pixel >= [cal["width"], cal["height"]]):
                    continue
                # Analytic scenario is noiseless but declares a nonzero pixel uncertainty.
                if not scenario["analytic"]:
                    pixel += rng.normal(0., scenario["pixel_sigma_px"], 2)
                detection_id = f"{frame_id}_d{target_index}"
                detections.append({"id": detection_id, "class_id": "buoy", "pixel_uv": pixel.tolist(),
                                   "pixel_covariance": diagonal([scenario["pixel_sigma_px"]]*2), "reference_method": "water_centre"})
                truth["detections"][detection_id] = target["id"]
            if not scenario["analytic"] and index == 30:
                detections.append({"id": frame_id+"_invalid", "class_id": "buoy", "pixel_uv": [-10., 100.],
                                   "pixel_covariance": diagonal([1., 1.]), "reference_method": "water_centre"})
            if not scenario["analytic"] and index == 35 and detections:
                duplicate = dict(detections[0], id=frame_id+"_duplicate")
                detections.append(duplicate)
                truth["detections"][duplicate["id"]] = truth["detections"][detections[0]["id"]]
            frame = {"id": frame_id, "stamp_ns": EPOCH_NS+round(t*1e9), "published_ns": EPOCH_NS+round((t+.15)*1e9),
                     "clock_id": "survey_utc", "stamp_semantics": "exposure_midpoint", "origin_id": "synthetic_origin",
                     "calibration_id": cal["calibration_id"], "source_image_size": [cal["width"], cal["height"]],
                     "input_image_size": [cal["width"], cal["height"]], "source_from_input": np.eye(3).tolist(),
                     "image_domain": "raw", "detections": detections}
            if not scenario["analytic"] and index == 12:
                frame["source_image_size"] = [640, 480]
            truth["frames"][frame_id] = {"stamp_ns": frame["stamp_ns"], "camera_position_m": position.tolist(),
                                         "body_quaternion_xyzw": attitude.as_quat().tolist()}
            stream.write(line({"kind": "frame", "data": frame}))
        # Explicit lack of a bracketing pose, after the available history.
        if not scenario["analytic"]:
            frame = dict(frame, id="frame_stale_pose", stamp_ns=frame["stamp_ns"]+2_000_000_000,
                         published_ns=frame["published_ns"]+2_000_000_000)
            stream.write(line({"kind": "frame", "data": frame}))
    write_json(output/"truth.json", truth)
    return settings


def load_scenario(name):
    path = Path(name)
    if not path.is_file():
        path = Path(__file__).parent/"scenarios"/(name+".json")
    return load_json(path)
