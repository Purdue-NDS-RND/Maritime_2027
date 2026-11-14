"""Launch selection and running-container protection without Docker or vehicles."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.boat = root / "boat"
        (self.boat / "container").mkdir(parents=True)
        shutil.copyfile(Path(__file__).resolve().parents[1] / "container/launch.sh",
                        self.boat / "container/launch.sh")
        (self.boat / "sim.env").write_text("# simulator settings\n")
        (self.boat / "field.env.example").write_text("# field settings template\n")
        binary = root / "bin"
        binary.mkdir()
        docker = binary / "docker"
        docker.write_text("""#!/usr/bin/env python3
import json
import os
import sys
with open(os.environ['DOCKER_CALLS'], 'a') as output:
    output.write(json.dumps(sys.argv[1:]) + '\\n')
if sys.argv[1] == 'ps':
    print(os.environ.get('FAKE_RUNNING', ''))
""")
        docker.chmod(0o755)
        self.calls_path = root / "docker-calls.jsonl"
        self.env = {**os.environ, "PATH": str(binary) + os.pathsep + os.environ["PATH"],
                    "DOCKER_CALLS": str(self.calls_path), "FAKE_RUNNING": ""}

    def launch(self, deployment):
        return subprocess.run(["bash", "container/launch.sh", deployment], cwd=self.boat,
                              env=self.env, capture_output=True, text=True)

    def calls(self):
        if not self.calls_path.exists():
            return []
        return [json.loads(line) for line in self.calls_path.read_text().splitlines()]

    def test_field_requires_local_settings_without_touching_docker(self):
        result = self.launch("field")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cp field.env.example field.env", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_sim_loads_its_own_settings_and_uses_shared_project(self):
        (self.boat / "field.env").write_text("BOAT_SERIAL_DEVICE=/not/a/device\n")
        result = self.launch("sim")
        self.assertEqual(result.returncode, 0, result.stderr)
        launch = self.calls()[-1]
        self.assertEqual(launch, ["compose", "-p", "maritime-boat", "--env-file", "sim.env",
                                  "up", "--no-build"])

    def test_field_uses_same_launch_command_with_different_env(self):
        (self.boat / "field.env").write_text("# local settings\n")
        result = self.launch("field")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls()[-1], ["compose", "-p", "maritime-boat", "--env-file",
                                           "field.env", "up", "--no-build"])

    def test_missing_sim_settings_fails_without_touching_docker(self):
        (self.boat / "sim.env").unlink()
        result = self.launch("sim")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing sim.env", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_neither_launch_replaces_running_boat(self):
        (self.boat / "field.env").write_text("# local settings\n")
        self.env["FAKE_RUNNING"] = "existing-boat"
        for deployment in ("sim", "field"):
            with self.subTest(deployment=deployment):
                result = self.launch(deployment)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("already running", result.stderr)
        self.assertFalse(any("up" in call for call in self.calls()))


if __name__ == "__main__":
    unittest.main()
