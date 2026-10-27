"""Behavior tests for scenario rendering and buoy category assets."""

import copy
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
    def test_gate_follows_competition_buoy_sides(self):
        scenario = json.loads((SIMULATION_ROOT/'scenarios/gate.json').read_text())
        by_marker = {b['marker_id']: b for b in scenario['buoys']}
        self.assertLess(by_marker[1]['pose']['y'], 0.)
        self.assertGreater(by_marker[2]['pose']['y'], 0.)

    def test_slalom_has_entry_exit_gates_and_alternating_turns(self):
        scenario = json.loads((SIMULATION_ROOT/'scenarios/slalom.json').read_text())
        result, _, manifest_path = self.render(scenario)
        self.assertEqual(result.returncode, 0, result.stderr)
        buoys = json.loads(manifest_path.read_text())['buoys']
        self.assertEqual(len(buoys), 8)
        self.assertEqual(len({b['evaluation_key'] for b in buoys}), 8)
        for gate, x in (('a', 7.), ('b', 37.)):
            pair = [b for b in buoys if b['name'].startswith(f'slalom_{gate}_')]
            self.assertEqual({b['category'] for b in pair}, {'red', 'green'})
            self.assertEqual({b['model_pose']['x'] for b in pair}, {x})
            self.assertEqual({b['model_pose']['y'] for b in pair}, {-2., 2.})
            self.assertEqual({b['category']: b['model_pose']['y'] for b in pair},
                             {'red': -2., 'green': 2.})
        turns = [b for b in buoys if 'turn' in b['name']]
        self.assertEqual([b['category'] for b in turns], ['red', 'green', 'red', 'green'])
        self.assertEqual([b['model_pose']['x'] for b in turns], [13., 19., 25., 31.])
        self.assertTrue(all(b['model_pose']['y'] == 0. for b in turns))

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

    def assert_rejected_before_output(self, scenario, message):
        result, world_path, manifest_path = self.render(scenario)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(message, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(world_path.exists())
        self.assertFalse(manifest_path.exists())

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

    def test_non_finite_pose_inputs_are_rejected_before_output(self):
        baseline = {
            "name": "invalid_pose",
            "buoys": [
                {
                    "name": "red_gate_port",
                    "marker_id": 1,
                    "pose": {"x": 7.0, "y": 1.5, "z": 0.0, "yaw_deg": 192.0},
                }
            ],
        }
        for field in ("x", "y", "z", "yaw_deg"):
            for value in (float("nan"), float("inf"), 10**400, "7.0", True):
                with self.subTest(field=field, value=value):
                    scenario = copy.deepcopy(baseline)
                    scenario["buoys"][0]["pose"][field] = value
                    self.assert_rejected_before_output(
                        scenario,
                        f"Buoy red_gate_port pose.{field} must be a finite number",
                    )

    def test_non_finite_jitter_inputs_are_rejected_before_output(self):
        baseline = {
            "name": "invalid_jitter",
            "buoys": [
                {
                    "name": "red_gate_port",
                    "marker_id": 1,
                    "pose": {"x": 7.0, "y": 1.5, "z": 0.0, "yaw_deg": 192.0},
                    "jitter": {"x": 0.1, "y": 0.1, "yaw_deg": 1.0},
                }
            ],
        }
        for field in ("x", "y", "yaw_deg"):
            for value in (float("nan"), float("inf"), 10**400, "0.1", True):
                with self.subTest(field=field, value=value):
                    scenario = copy.deepcopy(baseline)
                    scenario["buoys"][0]["jitter"][field] = value
                    self.assert_rejected_before_output(
                        scenario,
                        f"Buoy red_gate_port jitter.{field} must be a finite number",
                    )

    def test_marker_id_requires_integer_source_type(self):
        for marker_id in (1.0, "1", True):
            with self.subTest(marker_id=marker_id):
                scenario = {
                    "name": "invalid_marker_id",
                    "buoys": [
                        {
                            "name": "red_gate_port",
                            "marker_id": marker_id,
                            "pose": {"x": 7.0, "y": 1.5, "yaw_deg": 192.0},
                        }
                    ],
                }
                self.assert_rejected_before_output(
                    scenario,
                    "Buoy red_gate_port marker_id must be an integer",
                )

    def test_entity_name_requires_string_source_type(self):
        scenario = {
            "name": "invalid_entity_name_type",
            "buoys": [
                {
                    "name": 7,
                    "marker_id": 1,
                    "pose": {"x": 7.0, "y": 1.5, "yaw_deg": 192.0},
                }
            ],
        }

        self.assert_rejected_before_output(
            scenario,
            "Buoy at index 0 name must be a string",
        )

    def test_scenario_name_requires_valid_string_identity(self):
        for scenario_name in (7, "Repeated-Red"):
            with self.subTest(scenario_name=scenario_name):
                scenario = {
                    "name": scenario_name,
                    "buoys": [
                        {
                            "name": "red_gate_port",
                            "marker_id": 1,
                            "pose": {"x": 7.0, "y": 1.5, "yaw_deg": 192.0},
                        }
                    ],
                }
                self.assert_rejected_before_output(
                    scenario,
                    "Scenario name must be a string matching ^[a-z][a-z0-9_]*$",
                )


if __name__ == "__main__":
    unittest.main()
