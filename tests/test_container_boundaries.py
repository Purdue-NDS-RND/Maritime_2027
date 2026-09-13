"""Deployment contracts: exercise Compose resolution, not YAML source text."""

import json
import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


def resolve(path, *options, fcu_url="udp://:14552@"):
    env = {**os.environ, "DISPLAY": ":0", "XAUTH_FILE": "/dev/null"}
    env.pop("FCU_URL", None)
    if fcu_url is not None:
        env["FCU_URL"] = fcu_url
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
        self.assertEqual(services["autonomy"]["environment"]["FCU_URL"], "udp://:14552@")
        contexts = set()
        for service in services.values():
            build = service["build"]
            context = Path(build["context"])
            self.assertTrue((context / build.get("dockerfile", "Dockerfile")).is_file())
            contexts.add(context)
        self.assertEqual(len(contexts), 3)
        self.assertNotIn("SCENARIO_MANIFEST", services["autonomy"].get("environment", {}))
        self.assertFalse(services["autonomy"].get("volumes"))

    def test_autonomy_can_be_resolved_without_simulator(self):
        services = self.config("deployment/compose.autonomy.yaml")
        self.assertEqual(set(services), {"autonomy"})
        self.assertFalse(services["autonomy"].get("depends_on"))
        self.assertFalse(services["autonomy"].get("profiles"))

    def test_standalone_requires_explicit_vehicle_connection(self):
        result = resolve("deployment/compose.autonomy.yaml", fcu_url=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FCU_URL", result.stderr)

    def test_simulation_provides_its_own_default_connection(self):
        result = resolve("Simulation/container/compose.yaml", "--profile", "ros", fcu_url=None)
        self.assertEqual(result.returncode, 0, result.stderr)
        service = json.loads(result.stdout)["services"]["autonomy"]
        self.assertEqual(service["environment"]["FCU_URL"], "udp://:14552@")


if __name__ == "__main__":
    unittest.main()
