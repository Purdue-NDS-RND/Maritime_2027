"""Exercise terminal setup and launcher dispatch without starting Docker."""

import errno
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SELECTION_KEYS = ("WORLD", "SCENARIO", "BUOY_SEED", "ROS_SIM")


class RunMenuTests(unittest.TestCase):
    def launch(self, answers="", overrides=None, argument=None, terminal=True):
        # Stop at Docker preflight and report the environment that the real
        # launcher received. No containers, generated worlds, or locks touched.
        with tempfile.TemporaryDirectory() as directory:
            docker = Path(directory) / "docker"
            docker.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "if sys.argv[1:] == ['compose', 'version']: sys.exit(0)\n"
                "Path(__file__).with_name('selection').write_text('SELECTED=' + "
                "json.dumps({k: os.environ.get(k) "
                "for k in ('WORLD', 'SCENARIO', 'BUOY_SEED', 'ROS_SIM')}) + '\\n')\n"
                "sys.exit(1)\n"
            )
            docker.chmod(0o755)
            def captured_selection():
                selection = Path(directory) / "selection"
                return selection.read_text() if selection.exists() else ""

            environment = dict(os.environ)
            for key in SELECTION_KEYS:
                environment.pop(key, None)
            environment.update(overrides or {})
            environment["PATH"] = directory + os.pathsep + environment["PATH"]
            command = ["make", "--no-print-directory", "run"]
            if argument:
                command = ["./scripts/run.sh", argument]
            if not terminal:
                process = subprocess.run(command, cwd=ROOT, env=environment,
                                         input=answers, capture_output=True,
                                         text=True, timeout=10)
                return process.returncode, process.stdout + process.stderr + captured_selection()
            master, slave = pty.openpty()
            process = subprocess.Popen(command, cwd=ROOT, env=environment,
                                       stdin=slave, stdout=slave, stderr=slave)
            os.close(slave)
            output = bytearray()
            try:
                os.write(master, answers.encode())
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if not select.select([master], [], [], 0.1)[0]:
                        continue
                    try:
                        chunk = os.read(master, 65536)
                    except OSError as error:
                        if error.errno == errno.EIO:
                            break
                        raise
                    if not chunk:
                        break
                    output.extend(chunk)
                else:
                    self.fail("launcher hung waiting for input")
                return process.wait(timeout=2), output.decode() + captured_selection()
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
                os.close(master)

    def selected(self, answers, overrides=None):
        code, output = self.launch(answers, overrides)
        self.assertNotEqual(code, 0)  # Intentional Docker preflight stop.
        rows = [line for line in output.splitlines() if line.startswith("SELECTED=")]
        self.assertEqual(len(rows), 1, output)
        return json.loads(rows[0].removeprefix("SELECTED=")), output

    def test_direct_worlds_and_enter_defaults(self):
        for answer, world in (("", "waves"), ("1", "waves"),
                              ("2", "calm"), ("3", "harbor")):
            with self.subTest(world=world, answer=answer):
                values, _ = self.selected(answer + "\n\n")
                self.assertEqual(values["WORLD"], f"blueboat_{world}.sdf")
                self.assertEqual(values["ROS_SIM"], "0")
                self.assertIsNone(values["SCENARIO"])

    def test_buoy_scenarios_and_seed(self):
        for answer, scenario in ((4, "one"), (5, "gate"),
                                 (6, "multi"), (7, "repeated_red")):
            for seed in ("", "42", "-7", "0"):
                with self.subTest(scenario=scenario, seed=seed):
                    values, output = self.selected(f"{answer}\n{seed}\n")
                    self.assertEqual(values["SCENARIO"], scenario)
                    self.assertEqual(values["BUOY_SEED"], seed or None)
                    self.assertIsNone(values["WORLD"])
                    self.assertNotIn("Enable ROS/MAVROS", output)

    def test_camera_only(self):
        values, _ = self.selected("8\n")
        self.assertEqual(values["WORLD"], "blueboat_rgbd_base.sdf")
        self.assertEqual(values["ROS_SIM"], "1")

    def test_invalid_answers_retry(self):
        values, output = self.selected("bad\n9\n5\n1.5\n42\n")
        self.assertEqual(values["SCENARIO"], "gate")
        self.assertEqual(values["BUOY_SEED"], "42")
        self.assertIn("Please enter a number", output)
        self.assertIn("Please enter an integer", output)
        values, output = self.selected("1\nmaybe\ny\n")
        self.assertEqual(values["ROS_SIM"], "1")
        self.assertIn("Please enter y, n", output)

    def test_existing_seed_and_ros_defaults(self):
        values, _ = self.selected("5\n\n", {"BUOY_SEED": "17"})
        self.assertEqual(values["BUOY_SEED"], "17")
        values, _ = self.selected("1\n\n", {"ROS_SIM": "true"})
        self.assertEqual(values["ROS_SIM"], "1")

    def test_cancel_at_each_prompt(self):
        for answers in ("q\n", "5\nQ\n", "1\nq\n"):
            with self.subTest(answers=answers):
                code, output = self.launch(answers)
                self.assertEqual(code, 0, output)
                self.assertIn("Setup cancelled", output)
                self.assertNotIn("SELECTED=", output)

    def test_eof_cancels(self):
        code, output = self.launch("\x04")
        self.assertEqual(code, 0, output)
        self.assertIn("Setup cancelled", output)

    def test_explicit_configuration_skips_menu(self):
        for values in ({"WORLD": "blueboat_calm.sdf"}, {"SCENARIO": "gate"}):
            code, output = self.launch(overrides=values)
            self.assertNotEqual(code, 0)
            self.assertNotIn("Choose a world", output)
            self.assertIn("SELECTED=", output)

    def test_noninteractive_and_other_actions_skip_menu(self):
        for argument in ("--non-interactive", "--build-only", "--rebuild-only", "--down"):
            with self.subTest(argument=argument):
                code, output = self.launch(argument=argument)
                self.assertNotEqual(code, 0)
                self.assertNotIn("Choose a world", output)
                self.assertIn("SELECTED=", output)
        code, output = self.launch(terminal=False)
        self.assertNotEqual(code, 0)
        self.assertNotIn("Choose a world", output)


if __name__ == "__main__":
    unittest.main()
