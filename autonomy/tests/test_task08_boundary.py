"""Static checks for Task 08's simulation-only autonomy boundary."""

import ast
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest


AUTONOMY_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = AUTONOMY_ROOT / "ros_ws" / "src" / "maritime_bringup"
sys.path.insert(0, str(PACKAGE_ROOT))

from maritime_bringup.bootstrap_policy import validate_environment


class Task08BoundaryTests(unittest.TestCase):
    def test_bootstrap_requires_explicit_simulation_opt_in(self):
        self.assertIsNone(validate_environment("simulation", "1"))
        self.assertEqual(
            validate_environment(None, "1"),
            "adapter_environment_not_simulation",
        )
        self.assertEqual(
            validate_environment("hardware", "1"),
            "adapter_environment_not_simulation",
        )
        self.assertEqual(
            validate_environment("simulation", None),
            "placeholder_opt_in_missing",
        )

    def test_placeholder_runtime_only_publishes_false_mission_diagnostics(self):
        source = PACKAGE_ROOT / "maritime_bringup" / "placeholder.py"
        tree = ast.parse(source.read_text())
        definitions = [item for item in tree.body if isinstance(item, (ast.ClassDef, ast.Assign))]
        publications, topics, timers = [], [], []
        class NodeHarness:
            def __init__(self, name):
                self.name = name
            def create_publisher(self, message_type, topic, qos):
                topics.append(topic)
                return SimpleNamespace(publish=publications.append)
            def create_timer(self, period, callback):
                timers.append((period, callback))
                return object()
        class Status:
            WARN = 1
        namespace = dict(Node=NodeHarness, DiagnosticStatus=Status,
                         DiagnosticArray=SimpleNamespace, KeyValue=SimpleNamespace)
        # Execute the real constructor/publisher logic, replacing ROS transport
        # with a recorder. Any subscription or client creation fails this harness.
        exec(compile(ast.Module(body=definitions, type_ignores=[]), str(source), "exec"), namespace)
        node = namespace["PreimplementationPlaceholder"]()
        self.assertEqual(node.name, "maritime_preimplementation_placeholder")
        self.assertEqual(topics, ["/diagnostics"])
        self.assertEqual(len(timers), 1)
        timers[0][1]()
        self.assertEqual(len(publications), 2)
        for message in publications:
            self.assertEqual(len(message.status), 1)
            status = message.status[0]
            self.assertEqual(status.level, 1)
            self.assertEqual(status.message, "preimplementation_placeholder")
            self.assertEqual({value.key: value.value for value in status.values}, {
                "adapter_environment": "simulation", "placeholder_active": "true",
                "mission_ready": "false", "vehicle_commands_permitted": "false",
            })

    def test_autonomy_image_excludes_adapter_owned_runtime(self):
        dockerfile = (AUTONOMY_ROOT / "container" / "Dockerfile").read_text()
        for forbidden in ("mavros", "geographiclib", "FCU_URL"):
            self.assertNotIn(forbidden, dockerfile)

    def test_autonomy_package_excludes_environment_dependencies(self):
        package_xml = (PACKAGE_ROOT / "package.xml").read_text()
        for forbidden in ("mavros", "gazebo", "ros_gz", "zed", "geographiclib"):
            self.assertNotIn(forbidden, package_xml.lower())

    def test_only_the_named_placeholder_entrypoints_remain(self):
        setup_py = (PACKAGE_ROOT / "setup.py").read_text()
        self.assertIn("preimplementation_placeholder", setup_py)
        self.assertIn("placeholder_healthcheck", setup_py)
        self.assertNotIn("healthcheck = maritime_bringup.healthcheck", setup_py)
        self.assertFalse((PACKAGE_ROOT / "launch" / "vehicle.launch.py").exists())


if __name__ == "__main__":
    unittest.main()
