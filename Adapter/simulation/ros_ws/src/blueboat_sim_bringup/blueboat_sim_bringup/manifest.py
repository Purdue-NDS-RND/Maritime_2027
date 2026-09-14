"""Strict scenario-manifest validation for evaluation-only truth bridges."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path


NAME = re.compile(r"^[a-z][a-z0-9_]*$")
CATEGORIES = {0: "white", 1: "red", 2: "green", 3: "blue"}


def _finite_fields(value, fields, context):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError(f"{context} must contain exactly {', '.join(fields)}")
    for field in fields:
        number = value[field]
        if type(number) not in (int, float) or not math.isfinite(number):
            raise ValueError(f"{context}.{field} must be finite")


def load_manifest(path: str) -> dict:
    source = Path(path)
    if not source.is_absolute():
        raise ValueError("SCENARIO_MANIFEST must be an absolute path")
    with source.open(encoding="utf-8") as stream:
        manifest = json.load(stream)
    required = {
        "schema_version", "scenario", "seed", "world", "boat_pose",
        "camera_mount", "buoys",
    }
    if not isinstance(manifest, dict) or set(manifest) != required:
        raise ValueError("manifest top-level fields do not match schema_version 1")
    if manifest["schema_version"] != 1:
        raise ValueError("unsupported scenario manifest schema_version")
    if not isinstance(manifest["scenario"], str) or not NAME.fullmatch(manifest["scenario"]):
        raise ValueError("invalid scenario identity")
    if manifest["seed"] is not None and type(manifest["seed"]) is not int:
        raise ValueError("manifest seed must be an integer or null")
    if manifest["world"] != "blueboat_rgbd":
        raise ValueError("unsupported manifest world")
    _finite_fields(manifest["boat_pose"], ("x", "y", "z", "yaw_rad"), "boat_pose")
    _finite_fields(manifest["camera_mount"], ("x", "y", "z"), "camera_mount")
    if manifest["camera_mount"] != {"x": 0.35, "y": 0.0, "z": 0.4}:
        raise ValueError("manifest camera mount disagrees with camera contract")
    if not isinstance(manifest["buoys"], list):
        raise ValueError("manifest buoys must be an array")
    identities = set()
    gazebo_names = set()
    truth_topics = set()
    evaluation_keys = set()
    positions = []
    fields = {
        "name", "marker_id", "category", "gazebo_model_name", "model_uri",
        "model_pose", "marker_plane_center", "truth_topic", "evaluation_key",
    }
    for index, buoy in enumerate(manifest["buoys"]):
        if not isinstance(buoy, dict) or set(buoy) != fields:
            raise ValueError(f"buoys[{index}] fields do not match schema_version 1")
        name = buoy["name"]
        if not isinstance(name, str) or not NAME.fullmatch(name) or name in identities:
            raise ValueError(f"invalid or duplicate entity identity at buoys[{index}]")
        identities.add(name)
        marker_id = buoy["marker_id"]
        if type(marker_id) is not int or marker_id not in CATEGORIES:
            raise ValueError(f"invalid marker_id for entity {name}")
        expected = {
            "category": CATEGORIES[marker_id],
            "gazebo_model_name": name,
            "model_uri": f"model://aruco_buoy_id{marker_id}",
            "truth_topic": f"/blueboat/ground_truth/{name}/odometry",
            "evaluation_key": name,
        }
        for field, value in expected.items():
            if buoy[field] != value:
                raise ValueError(f"invalid {field} for entity {name}")
        _finite_fields(buoy["model_pose"], ("x", "y", "z", "yaw_deg", "yaw_rad"), f"{name}.model_pose")
        _finite_fields(
            buoy["marker_plane_center"],
            ("x", "y", "z", "normal_x", "normal_y"),
            f"{name}.marker_plane_center",
        )
        if not math.isclose(
            buoy["model_pose"]["yaw_rad"],
            math.radians(buoy["model_pose"]["yaw_deg"]),
            abs_tol=1e-8,
        ):
            raise ValueError(f"inconsistent yaw for entity {name}")
        pose = buoy["model_pose"]
        if pose["x"] < 4.0 or abs(pose["x"]) > 40.0 or abs(pose["y"]) > 20.0:
            raise ValueError(f"entity {name} is outside the supported test area")
        for other_name, other_x, other_y in positions:
            if math.hypot(pose["x"] - other_x, pose["y"] - other_y) < 1.0:
                raise ValueError(f"entities {other_name} and {name} are less than 1 metre apart")
        positions.append((name, pose["x"], pose["y"]))
        normal = buoy["marker_plane_center"]
        if not math.isclose(math.hypot(normal["normal_x"], normal["normal_y"]), 1.0, abs_tol=1e-8):
            raise ValueError(f"marker normal for entity {name} is not unit length")
        if not (
            math.isclose(normal["normal_x"], math.cos(pose["yaw_rad"]), abs_tol=1e-8)
            and math.isclose(normal["normal_y"], math.sin(pose["yaw_rad"]), abs_tol=1e-8)
        ):
            raise ValueError(f"marker normal for entity {name} disagrees with yaw")
        for collection, value, label in (
            (gazebo_names, buoy["gazebo_model_name"], "gazebo_model_name"),
            (truth_topics, buoy["truth_topic"], "truth_topic"),
            (evaluation_keys, buoy["evaluation_key"], "evaluation_key"),
        ):
            if value in collection:
                raise ValueError(f"duplicate {label}: {value}")
            collection.add(value)
    return manifest


def truth_bridge_arguments(manifest: dict) -> list[tuple[str, str, str]]:
    return [
        (
            buoy["evaluation_key"],
            buoy["truth_topic"],
            f"/model/{buoy['gazebo_model_name']}/odometry@nav_msgs/msg/Odometry[gz.msgs.Odometry",
        )
        for buoy in manifest["buoys"]
    ]
