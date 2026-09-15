"""Deployment contracts: exercise Compose resolution, not YAML source text."""

import json
import os
from pathlib import Path
import subprocess
import unittest


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
