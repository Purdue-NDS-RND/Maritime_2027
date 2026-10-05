"""Deployment contracts: exercise Compose resolution, not YAML source text."""

import json
import os
from pathlib import Path
import subprocess
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


def resolve(path, *options):
    env = {**os.environ, "DISPLAY": ":0", "XAUTH_FILE": "/dev/null"}
    return subprocess.run(
        ["docker", "compose", "-f", str(ROOT / path), *options, "config", "--format", "json"],
        env=env, text=True, capture_output=True,
    )


class ContainerBoundaries(unittest.TestCase):
    def config(self, path, *options):
        result = resolve(path, *options)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["services"]

    def test_simulation_connects_independent_adapter_and_autonomy(self):
        services = self.config("Simulation/container/compose.yaml", "--profile", "ros")
        self.assertEqual(set(services), {"simulator", "adapter", "autonomy"})
        self.assertEqual(services["adapter"]["environment"]["FCU_URL"], "udp://:14552@")
        self.assertNotIn("FCU_URL", services["autonomy"].get("environment", {}))
        self.assertEqual(services["autonomy"]["environment"]["ADAPTER_ENVIRONMENT"], "simulation")
        self.assertEqual(services["autonomy"]["environment"]["MARITIME_PREIMPLEMENTATION_PLACEHOLDER"], "1")
        contexts = set()
        for service in services.values():
            build = service["build"]
            context = Path(build["context"])
            self.assertTrue((context / build.get("dockerfile", "Dockerfile")).is_file())
            contexts.add(context)
        self.assertEqual(len(contexts), 3)
        self.assertTrue(str(services["adapter"]["build"]["context"]).endswith("Adapter/simulation"))
        self.assertNotIn("SCENARIO_MANIFEST", services["autonomy"].get("environment", {}))
        self.assertFalse(services["autonomy"].get("volumes"))

    def test_autonomy_has_only_environment_neutral_runtime(self):
        services = self.config("Simulation/container/compose.yaml", "--profile", "ros")
        autonomy = services["autonomy"]
        self.assertEqual(set(autonomy["environment"]), {
            "ROS_DOMAIN_ID", "ADAPTER_ENVIRONMENT", "MARITIME_PREIMPLEMENTATION_PLACEHOLDER",
            "RUN_ID", "RUN_CONFIG_SHA256",
        })
        self.assertEqual(autonomy["environment"]["RUN_ID"], services["adapter"]["environment"]["RUN_ID"])
        self.assertEqual(autonomy["environment"]["RUN_CONFIG_SHA256"], services["adapter"]["environment"]["RUN_CONFIG_SHA256"])
        self.assertEqual(set(autonomy["depends_on"]), {"adapter"})
        self.assertEqual(autonomy["depends_on"]["adapter"]["condition"], "service_healthy")
        self.assertFalse(autonomy.get("devices"))
        self.assertFalse(autonomy.get("volumes"))
        self.assertFalse(autonomy.get("privileged", False))
        self.assertFalse(any("hardware" in service.get("profiles", []) for service in services.values()))
        for service in services.values():
            self.assertNotIn("ACTIVE_BUOY_IDS", service.get("environment", {}))
        package = ET.parse(ROOT / "autonomy/ros_ws/src/maritime_bringup/package.xml")
        dependencies = {item.text for item in package.getroot() if "depend" in item.tag}
        self.assertEqual(dependencies, {"ament_python", "rclpy", "diagnostic_msgs"})

        adapter = services["adapter"]
        self.assertEqual(adapter["environment"]["ADAPTER_ENVIRONMENT"], "simulation")
        self.assertIn("SCENARIO_MANIFEST", adapter["environment"])
        self.assertTrue(all(volume.get("read_only") for volume in adapter["volumes"]))
        self.assertEqual(set(adapter["depends_on"]), {"simulator"})

    def test_no_standalone_autonomy_transport_profile_remains(self):
        self.assertFalse((ROOT / "deployment" / "compose.autonomy.yaml").exists())

    def test_evaluation_is_explicit_and_simulation_guarded(self):
        services = self.config("Simulation/container/compose.yaml", "--profile", "ros", "--profile", "evaluation")
        evaluation = services["evaluation"]
        self.assertEqual(evaluation["environment"]["ADAPTER_ENVIRONMENT"], "simulation")
        self.assertEqual(evaluation["environment"]["SIMULATION_EVALUATION"], "0")
        self.assertEqual(evaluation["environment"]["FCU_URL"], "udp://:14552@")
        self.assertEqual(evaluation["depends_on"]["adapter"]["condition"], "service_healthy")


if __name__ == "__main__":
    unittest.main()
