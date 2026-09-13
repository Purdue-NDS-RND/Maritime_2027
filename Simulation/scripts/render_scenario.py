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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--base-world", required=True, type=Path)
    parser.add_argument("--output-world", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--seed", type=int)
    return parser.parse_args()


def resolved_pose(spec: dict, rng: random.Random | None) -> dict:
    pose = dict(spec["pose"])
    if rng is not None:
        jitter = spec.get("jitter", {})
        for key in ("x", "y", "yaw_deg"):
            extent = float(jitter.get(key, 0.0))
            pose[key] = float(pose[key]) + rng.uniform(-extent, extent)
    pose["z"] = float(pose.get("z", 0.0))
    return {key: float(value) for key, value in pose.items()}


def validate_buoys(buoys: list[dict]) -> None:
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
        if item["marker_id"] not in CATEGORY_BY_MARKER_ID:
            raise SystemExit("Only marker IDs 0 through 3 are available")
        if pose["x"] < 4.0 or abs(pose["x"]) > 40.0 or abs(pose["y"]) > 20.0:
            raise SystemExit(f"Buoy {item['name']} is outside the approved test area")
    for index, first in enumerate(buoys):
        for second in buoys[index + 1 :]:
            dx = first["resolved_pose"]["x"] - second["resolved_pose"]["x"]
            dy = first["resolved_pose"]["y"] - second["resolved_pose"]["y"]
            if math.hypot(dx, dy) < 1.0:
                raise SystemExit(f"Buoys {first['name']} and {second['name']} overlap")


def main() -> int:
    args = parse_args()
    config = json.loads(args.scenario.read_text(encoding="utf-8"))
    rng = random.Random(args.seed) if args.seed is not None else None
    buoys = []
    for source in config["buoys"]:
        item = dict(source)
        item["marker_id"] = int(item["marker_id"])
        item["resolved_pose"] = resolved_pose(item, rng)
        buoys.append(item)
    validate_buoys(buoys)

    tree = ET.parse(args.base_world)
    world = tree.find("./world")
    if world is None or world.get("name") != "blueboat_rgbd":
        raise SystemExit("Base world must be named blueboat_rgbd")

    manifest_buoys = []
    panel_offset = 0.311
    for item in buoys:
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

    args.output_world.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(tree, space="  ")
    tree.write(args.output_world, encoding="utf-8", xml_declaration=True)
    manifest = {
        "schema_version": 1,
        "scenario": config["name"],
        "seed": args.seed,
        "world": "blueboat_rgbd",
        "boat_pose": {"x": 0.0, "y": 0.0, "z": 0.0, "yaw_rad": 0.0},
        "camera_mount": {"x": 0.35, "y": 0.0, "z": 0.40},
        "buoys": manifest_buoys,
    }
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Rendered {config['name']} with {len(buoys)} buoy(s) to {args.output_world}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
