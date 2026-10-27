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
SELECTION_KEYS = ("WORLD", "SCENARIO", "BUOY_SEED", "WATER", "BOAT_MODEL")


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
                "for k in ('WORLD', 'SCENARIO', 'BUOY_SEED', 'WATER', 'BOAT_MODEL')}) + '\\n')\n"
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
        code, output = self.launch(answers + "\n", overrides)
        self.assertNotEqual(code, 0)  # Intentional Docker preflight stop.
        rows = [line for line in output.splitlines() if line.startswith("SELECTED=")]
        self.assertEqual(len(rows), 1, output)
        return json.loads(rows[0].removeprefix("SELECTED=")), output

    def test_direct_worlds_and_enter_defaults(self):
        for water_answer, water in (("", "normal"), ("1", "calm"),
                                    ("2", "normal"), ("3", "harsh")):
            for answer, world in (("", "waves"), ("1", "waves"), ("2", "harbor")):
                with self.subTest(world=world, water=water):
                    values, output = self.selected(f"{water_answer}\n{answer}\n\n")
                    self.assertEqual(values["WORLD"], f"blueboat_{world}.sdf")
                    self.assertEqual(values["WATER"], water)
                    self.assertIsNone(values["SCENARIO"])
                    self.assertLess(output.index('Choose water'), output.index('Choose a scene'))

    def test_buoy_scenarios_and_seed(self):
        for answer, scenario in ((3, "one"), (4, "gate"),
                                 (5, "multi"), (6, "repeated_red"), (8, "slalom")):
            for seed in ("", "42", "-7", "0"):
                with self.subTest(scenario=scenario, seed=seed):
                    values, output = self.selected(f"3\n{answer}\n{seed}\n")
                    self.assertEqual(values["WATER"], "harsh")
                    self.assertEqual(values["SCENARIO"], scenario)
                    self.assertEqual(values["BUOY_SEED"], seed or None)
                    self.assertIsNone(values["WORLD"])

    def test_camera_only(self):
        values, _ = self.selected("1\n7\n")
        self.assertEqual(values["WORLD"], "blueboat_rgbd_base.sdf")

    def test_invalid_answers_retry(self):
        values, output = self.selected("bad\n2\n9\n4\n1.5\n42\n")
        self.assertEqual(values["SCENARIO"], "gate")
        self.assertEqual(values["BUOY_SEED"], "42")
        self.assertIn("Please enter a number", output)
        self.assertIn("Please enter an integer", output)
        values, output = self.selected("2\n1\nmaybe\n1\n")
        self.assertIn("Please enter 1 or 2", output)

    def test_existing_seed_default(self):
        values, _ = self.selected("2\n4\n\n", {"BUOY_SEED": "17"})
        self.assertEqual(values["BUOY_SEED"], "17")

    def test_cancel_at_each_prompt(self):
        for answers in ("q\n", "2\nq\n", "2\n4\nQ\n", "2\n1\nq\n"):
            with self.subTest(answers=answers):
                code, output = self.launch(answers)
                self.assertEqual(code, 0, output)
                self.assertIn("Setup cancelled", output)
                self.assertNotIn("SELECTED=", output)

    def test_dual_boat_selection(self):
        values, output = self.selected("2\n4\n\n2\n")
        self.assertEqual(values["BOAT_MODEL"], "dual")
        self.assertIn("BOAT_MODEL=dual", output)

    def test_eof_cancels(self):
        code, output = self.launch("\x04")
        self.assertEqual(code, 0, output)
        self.assertIn("Setup cancelled", output)

    def test_explicit_configuration_skips_menu(self):
        for values in ({"WORLD": "blueboat_calm.sdf"}, {"SCENARIO": "gate"},
                       {"SCENARIO": "gate", "WATER": "harsh"}):
            code, output = self.launch(overrides=values)
            self.assertNotEqual(code, 0)
            self.assertNotIn("Choose water", output)
            self.assertIn("SELECTED=", output)

    def test_explicit_water_keeps_scene_selection(self):
        values, output = self.selected('4\n\n', {'WATER': 'calm'})
        self.assertEqual(values['WATER'], 'calm')
        self.assertEqual(values['SCENARIO'], 'gate')
        self.assertNotIn('Choose water', output)
        self.assertIn('Choose a scene', output)

    def test_noninteractive_and_other_actions_skip_menu(self):
        for argument in ("--non-interactive", "--build-only", "--rebuild-only", "--down"):
            with self.subTest(argument=argument):
                code, output = self.launch(argument=argument)
                self.assertNotEqual(code, 0)
                self.assertNotIn("Choose water", output)
                self.assertIn("SELECTED=", output)
        code, output = self.launch(terminal=False)
        self.assertNotEqual(code, 0)
        self.assertNotIn("Choose water", output)


if __name__ == "__main__":
    unittest.main()
