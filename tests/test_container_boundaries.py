"""Deployment contracts: exercise Compose resolution, not YAML source text."""

import ast
import json
import os
from pathlib import Path
import subprocess
import shlex
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

    def test_adapter_owns_mavros_configuration_geoid_and_fcu_health(self):
        # Source ownership complements separate image inspection and live
        # acceptance; this test makes no claim that a Docker build was run.
        services = self.config("Simulation/container/compose.yaml", "--profile", "ros")
        adapter = Path(services["adapter"]["build"]["context"])
        autonomy = Path(services["autonomy"]["build"]["context"])
        package = adapter / "ros_ws/src/blueboat_sim_bringup"
        dependencies = {item.text for item in ET.parse(package / "package.xml").getroot() if "depend" in item.tag}
        self.assertTrue({"mavros", "mavros_msgs"} <= dependencies)

        dockerfile = (adapter / "container/Dockerfile").read_text()
        instructions = dockerfile.replace("\\\n", " ").splitlines()
        run_tokens = [token for line in instructions if line.startswith("RUN ") for token in shlex.split(line[4:])]
        self.assertTrue(any(token.startswith("ros-jazzy-mavros=") for token in run_tokens))
        self.assertTrue(any(token.startswith("ros-jazzy-mavros-extras=") for token in run_tokens))
        self.assertIn("geographiclib-tools", run_tokens)
        self.assertIn("/opt/ros/jazzy/lib/mavros/install_geographiclib_datasets.sh", run_tokens)
        self.assertIn("/usr/share/GeographicLib/geoids/egm96-5.pgm", run_tokens)

        launch = ast.parse((package / "launch/bringup.launch.py").read_text())
        mavros_calls = [node for node in ast.walk(launch) if isinstance(node, ast.Call)
                        and any(keyword.arg == "package" and isinstance(keyword.value, ast.Constant)
                                and keyword.value.value == "mavros" for keyword in node.keywords)]
        self.assertEqual(len(mavros_calls), 1)
        parameters = next(keyword.value for keyword in mavros_calls[0].keywords if keyword.arg == "parameters")
        self.assertTrue(any(isinstance(node, ast.Constant) and node.value == "mavros.yaml" for node in ast.walk(parameters)))
        self.assertTrue((package / "config/mavros.yaml").is_file())
        health = ast.parse((package / "blueboat_sim_bringup/healthcheck.py").read_text())
        diagnostic_requirements = next(node.value for node in ast.walk(health) if isinstance(node, ast.Assign)
                                       and any(isinstance(target, ast.Attribute) and target.attr == "required_diagnostics" for target in node.targets))
        self.assertIn("mavros_adapter/fcu_readiness", ast.literal_eval(diagnostic_requirements))
        self.assertIn("blueboat_sim_bringup healthcheck", " ".join(services["adapter"]["healthcheck"]["test"]))

        autonomy_dockerfile = (autonomy / "container/Dockerfile").read_text().lower()
        for forbidden in ("mavros", "geographiclib", "fcu_url"):
            self.assertNotIn(forbidden, autonomy_dockerfile)
        self.assertFalse(list((autonomy / "ros_ws/src").rglob("mavros*")))
        self.assertNotIn("FCU_URL", services["autonomy"]["environment"])
        autonomy_health = " ".join(services["autonomy"]["healthcheck"]["test"])
        self.assertIn("placeholder_healthcheck", autonomy_health)
        self.assertNotIn("mavros", autonomy_health.lower())
        for source in (autonomy / "ros_ws/src").rglob("*.py"):
            imports = [node for node in ast.walk(ast.parse(source.read_text())) if isinstance(node, (ast.Import, ast.ImportFrom))]
            modules = [node.module or "" for node in imports if isinstance(node, ast.ImportFrom)]
            modules += [alias.name for node in imports if isinstance(node, ast.Import) for alias in node.names]
            self.assertFalse(any(module.startswith(("mavros", "geographiclib")) for module in modules), source)

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
