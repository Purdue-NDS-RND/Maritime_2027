"""Behavior tests for scenario rendering and buoy category assets."""

import json
import math
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET


SIMULATION_ROOT = Path(__file__).resolve().parents[1]
RENDERER = SIMULATION_ROOT / "scripts" / "render_scenario.py"
BASE_WORLD = SIMULATION_ROOT / "worlds" / "blueboat_rgbd_base.sdf"


class ScenarioRenderingTests(unittest.TestCase):
    def render(self, scenario):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        directory = Path(temporary_directory.name)
        scenario_path = directory / "scenario.json"
        world_path = directory / "world.sdf"
        manifest_path = directory / "manifest.json"
        scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
        result = subprocess.run(
            [
                "python3",
                str(RENDERER),
                "--scenario",
                str(scenario_path),
                "--base-world",
                str(BASE_WORLD),
                "--output-world",
                str(world_path),
                "--manifest",
                str(manifest_path),
            ],
            capture_output=True,
            text=True,
        )
        return result, world_path, manifest_path

    def test_repeated_category_entities_preserve_distinct_identity_contract(self):
        scenario = json.loads(
            (SIMULATION_ROOT / "scenarios" / "repeated_red.json").read_text(
                encoding="utf-8"
            )
        )

        result, world_path, manifest_path = self.render(scenario)

        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(
            manifest["buoys"],
            [
                {
                    "name": "red_gate_port",
                    "marker_id": 1,
                    "category": "red",
                    "gazebo_model_name": "red_gate_port",
                    "model_uri": "model://aruco_buoy_id1",
                    "model_pose": {
                        "x": 7.0,
                        "y": 1.5,
                        "z": 0.0,
                        "yaw_deg": 192.0,
                        "yaw_rad": math.radians(192.0),
                    },
                    "marker_plane_center": {
                        "x": 7.0 + 0.311 * math.cos(math.radians(192.0)),
                        "y": 1.5 + 0.311 * math.sin(math.radians(192.0)),
                        "z": 0.75,
                        "normal_x": math.cos(math.radians(192.0)),
                        "normal_y": math.sin(math.radians(192.0)),
                    },
                    "truth_topic": "/blueboat/ground_truth/red_gate_port/odometry",
                    "evaluation_key": "red_gate_port",
                },
                {
                    "name": "red_gate_starboard",
                    "marker_id": 1,
                    "category": "red",
                    "gazebo_model_name": "red_gate_starboard",
                    "model_uri": "model://aruco_buoy_id1",
                    "model_pose": {
                        "x": 7.0,
                        "y": -1.5,
                        "z": 0.0,
                        "yaw_deg": 168.0,
                        "yaw_rad": math.radians(168.0),
                    },
                    "marker_plane_center": {
                        "x": 7.0 + 0.311 * math.cos(math.radians(168.0)),
                        "y": -1.5 + 0.311 * math.sin(math.radians(168.0)),
                        "z": 0.75,
                        "normal_x": math.cos(math.radians(168.0)),
                        "normal_y": math.sin(math.radians(168.0)),
                    },
                    "truth_topic": "/blueboat/ground_truth/red_gate_starboard/odometry",
                    "evaluation_key": "red_gate_starboard",
                },
            ],
        )
        includes = ET.parse(world_path).findall("./world/include")
        rendered = [(item.findtext("name"), item.findtext("uri")) for item in includes]
        self.assertEqual(
            rendered[-2:],
            [
                ("red_gate_port", "model://aruco_buoy_id1"),
                ("red_gate_starboard", "model://aruco_buoy_id1"),
            ],
        )

    def test_duplicate_entity_identity_is_rejected_actionably(self):
        scenario = {
            "name": "duplicate_name",
            "buoys": [
                {
                    "name": "red_gate_port",
                    "marker_id": 1,
                    "pose": {"x": 7.0, "y": 1.5, "yaw_deg": 192.0},
                },
                {
                    "name": "red_gate_port",
                    "marker_id": 2,
                    "pose": {"x": 7.0, "y": -1.5, "yaw_deg": 168.0},
                },
            ],
        }

        result, _, _ = self.render(scenario)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Duplicate buoy entity name: red_gate_port", result.stderr)

    def test_invalid_entity_identity_is_rejected_actionably(self):
        scenario = {
            "name": "invalid_name",
            "buoys": [
                {
                    "name": "red-gate-port",
                    "marker_id": 1,
                    "pose": {"x": 7.0, "y": 1.5, "yaw_deg": 192.0},
                }
            ],
        }

        result, _, _ = self.render(scenario)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "Buoy entity name must match ^[a-z][a-z0-9_]*$: red-gate-port",
            result.stderr,
        )

    def test_marker_categories_and_assets_are_aligned(self):
        scenario = json.loads(
            (SIMULATION_ROOT / "scenarios" / "multi.json").read_text(encoding="utf-8")
        )

        result, _, manifest_path = self.render(scenario)

        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [(item["marker_id"], item["category"]) for item in manifest["buoys"]],
            [(0, "white"), (1, "red"), (2, "green"), (3, "blue")],
        )
        for marker_id, category in enumerate(("white", "red", "green", "blue")):
            model_root = SIMULATION_ROOT / "models" / f"aruco_buoy_id{marker_id}"
            description = ET.parse(model_root / "model.config").findtext("description")
            self.assertIn(f"Static {category} buoy", description)
            material = ET.parse(model_root / "model.sdf").find(
                ".//visual[@name='body_visual']/material"
            )
            ambient = [float(value) for value in material.findtext("ambient").split()]
            diffuse = [float(value) for value in material.findtext("diffuse").split()]
            self.assertEqual(ambient, diffuse)
            red, green, blue, alpha = ambient
            self.assertEqual(alpha, 1.0)
            if category == "white":
                self.assertEqual((red, green, blue), (1.0, 1.0, 1.0))
            elif category == "red":
                self.assertGreater(red, max(green, blue))
            elif category == "green":
                self.assertGreater(green, max(red, blue))
            else:
                self.assertGreater(blue, max(red, green))


if __name__ == "__main__":
    unittest.main()
