#!/usr/bin/env python3
"""Render a deterministic buoy scenario into a Gazebo world and manifest."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import random
import re
import xml.etree.ElementTree as ET


CATEGORY_BY_MARKER_ID = {
    0: "white",
    1: "red",
    2: "green",
    3: "blue",
}
ENTITY_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
POSE_FIELDS = ("x", "y", "yaw_deg")
JITTER_FIELDS = ("x", "y", "yaw_deg")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--base-world", required=True, type=Path)
    parser.add_argument("--output-world", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--cameras", choices=("on", "off"), default="on")
    parser.add_argument("--boat-model", choices=("single", "dual"), default="single")
    return parser.parse_args()


def is_finite_number(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def validate_scenario_source(config: object) -> dict:
    if not isinstance(config, dict):
        raise SystemExit("Scenario source must be a JSON object")
    scenario_name = config.get("name")
    if not isinstance(scenario_name, str) or not ENTITY_NAME_PATTERN.fullmatch(
        scenario_name
    ):
        raise SystemExit(
            "Scenario name must be a string matching ^[a-z][a-z0-9_]*$"
        )
    buoys = config.get("buoys")
    if not isinstance(buoys, list):
        raise SystemExit("Scenario buoys must be an array")
    for index, source in enumerate(buoys):
        if not isinstance(source, dict):
            raise SystemExit(f"Buoy at index {index} must be an object")
        name = source.get("name")
        if not isinstance(name, str):
            raise SystemExit(f"Buoy at index {index} name must be a string")
        marker_id = source.get("marker_id")
        if scenario_name != "competition" and type(marker_id) is not int:
            raise SystemExit(f"Buoy {name} marker_id must be an integer")
        pose = source.get("pose")
        if not isinstance(pose, dict):
            raise SystemExit(f"Buoy {name} pose must be an object")
        for field in (*POSE_FIELDS, "z"):
            value = pose.get(field, 0.0) if field == "z" else pose.get(field)
            if not is_finite_number(value):
                raise SystemExit(
                    f"Buoy {name} pose.{field} must be a finite number"
                )
        jitter = source.get("jitter", {})
        if not isinstance(jitter, dict):
            raise SystemExit(f"Buoy {name} jitter must be an object")
        for field in JITTER_FIELDS:
            value = jitter.get(field, 0.0)
            if not is_finite_number(value):
                raise SystemExit(
                    f"Buoy {name} jitter.{field} must be a finite number"
                )
    return config


def resolved_pose(spec: dict, rng: random.Random | None) -> dict:
    source_pose = spec["pose"]
    pose = {field: float(source_pose[field]) for field in POSE_FIELDS}
    pose["z"] = float(source_pose.get("z", 0.0))
    if rng is not None:
        jitter = spec.get("jitter", {})
        for key in JITTER_FIELDS:
            extent = float(jitter.get(key, 0.0))
            pose[key] += rng.uniform(-extent, extent)
    for field, value in pose.items():
        if not math.isfinite(value):
            raise SystemExit(
                f"Buoy {spec['name']} resolved pose.{field} must be a finite number"
            )
    return pose


def validate_buoys(buoys: list[dict], competition=False) -> None:
    seen_names = set()
    for item in buoys:
        name = item["name"]
        if not ENTITY_NAME_PATTERN.fullmatch(name):
            raise SystemExit(
                f"Buoy entity name must match ^[a-z][a-z0-9_]*$: {name}"
            )
        if name in seen_names:
            raise SystemExit(f"Duplicate buoy entity name: {name}")
        seen_names.add(name)
        pose = item["resolved_pose"]
        if not competition and item["marker_id"] not in CATEGORY_BY_MARKER_ID:
            raise SystemExit("Only marker IDs 0 through 3 are available")
        if not competition and (pose["x"] < 4.0 or abs(pose["x"]) > 40.0 or abs(pose["y"]) > 20.0):
            raise SystemExit(f"Buoy {item['name']} is outside the approved test area")
    for index, first in enumerate(buoys):
        for second in buoys[index + 1 :]:
            dx = first["resolved_pose"]["x"] - second["resolved_pose"]["x"]
            dy = first["resolved_pose"]["y"] - second["resolved_pose"]["y"]
            if math.hypot(dx, dy) < 1.0:
                raise SystemExit(f"Buoys {first['name']} and {second['name']} overlap")


def main() -> int:
    args = parse_args()
    try:
        loaded_config = json.loads(args.scenario.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"Scenario source is not valid JSON: {error.msg}") from None
    config = validate_scenario_source(loaded_config)
    rng = random.Random(args.seed) if args.seed is not None else None
    buoys = []
    for source in config["buoys"]:
        item = dict(source)
        item["resolved_pose"] = resolved_pose(item, rng)
        buoys.append(item)
    validate_buoys(buoys, config["name"] == "competition")

    tree = ET.parse(args.base_world)
    world = tree.find("./world")
    if world is None or world.get("name") != "blueboat_rgbd":
        raise SystemExit("Base world must be named blueboat_rgbd")

    if args.boat_model == "dual":
        world.find("include/uri").text = "model://blueboat_dual_rgbd"

    if args.cameras == "off":
        world.find("include/uri").text = "model://blueboat"
        for plugin in list(world.findall("plugin")):
            if 'sensors-system' in plugin.get('filename', ''):
                world.remove(plugin)

    competition_objects = None
    if config["name"] == "competition":
        from competition_scene import render_objects
        competition_objects = render_objects(world, config, buoys)
        world.find("include/pose").text = "0 0 0 0 0 3.141592653589793"

    manifest_buoys = []
    panel_offset = 0.311
    for item in ([] if competition_objects is not None else buoys):
        pose = item["resolved_pose"]
        yaw = math.radians(pose["yaw_deg"])
        model_uri = f"model://aruco_buoy_id{item['marker_id']}"
        include = ET.SubElement(world, "include")
        ET.SubElement(include, "name").text = item["name"]
        ET.SubElement(include, "pose").text = (
            f"{pose['x']:.6f} {pose['y']:.6f} {pose['z']:.6f} 0 0 {yaw:.9f}"
        )
        ET.SubElement(include, "uri").text = model_uri
        manifest_buoys.append(
            {
                "name": item["name"],
                "marker_id": item["marker_id"],
                "category": CATEGORY_BY_MARKER_ID[item["marker_id"]],
                "gazebo_model_name": item["name"],
                "model_uri": model_uri,
                "model_pose": {**pose, "yaw_rad": yaw},
                "marker_plane_center": {
                    "x": pose["x"] + panel_offset * math.cos(yaw),
                    "y": pose["y"] + panel_offset * math.sin(yaw),
                    "z": pose["z"] + 0.75,
                    "normal_x": math.cos(yaw),
                    "normal_y": math.sin(yaw),
                },
                "truth_topic": f"/blueboat/ground_truth/{item['name']}/odometry",
                "evaluation_key": item["name"],
            }
        )

    manifest = {
        "schema_version": 1,
        "scenario": config["name"],
        "seed": args.seed,
        "world": "blueboat_rgbd",
        "boat_pose": {"x": 0.0, "y": 0.0, "z": 0.0, "yaw_rad": 0.0},
        "camera_mount": {"x": 0.35, "y": 0.0, "z": 0.40},
        "buoys": manifest_buoys,
    }
    if competition_objects is not None:
        manifest.update(boat_pose=config["boat_pose"], buoys=[o for o in competition_objects if o.get("kind", "buoy") == "buoy"],
                        props=[o for o in competition_objects if o.get("kind", "buoy") != "buoy"],
                        stations=config["stations"], source=config["source"], approximation_notes=config["approximation_notes"])
    if args.boat_model == "dual":
        manifest["boat_model"] = "dual"
    try:
        manifest_text = json.dumps(manifest, indent=2, allow_nan=False) + "\n"
    except ValueError:
        raise SystemExit("Resolved manifest contains a non-finite numeric value") from None

    args.output_world.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(tree, space="  ")
    tree.write(args.output_world, encoding="utf-8", xml_declaration=True)
    args.manifest.write_text(manifest_text, encoding="utf-8")
    print(f"Rendered {config['name']} with {len(buoys)} buoy(s) to {args.output_world}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
