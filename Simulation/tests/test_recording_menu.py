"""Terminal entry point and recording menu workflows without a simulator."""

import contextlib
import errno
import importlib.util
import io
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch


SIMULATION = Path(__file__).resolve().parents[1]
TOOLS = SIMULATION / "recordings"
with patch.object(sys, "path", [str(TOOLS), *sys.path]):
    spec = importlib.util.spec_from_file_location("recording_menu", TOOLS / "menu.py")
    menu = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(menu)


class MenuTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.datasets = Path(temporary.name)
        dataset_patch = patch.object(menu.cli, "DATASETS", self.datasets)
        dataset_patch.start()
        self.addCleanup(dataset_patch.stop)

    def dataset(self, name="gate-pass", status="complete"):
        path = self.datasets / name
        path.mkdir()
        (path / "dataset.json").write_text(json.dumps({
            "name": name, "status": status, "capture_domain": 0,
            "run_id": "test-run", "timing_note": "Source clocks preserved.",
        }))
        return path

    def test_empty_browser_and_cancel_do_not_start_commands(self):
        with patch("builtins.input", side_effect=["2", "1", "q", "q"]), \
                patch.object(menu, "run_foreground") as run, contextlib.redirect_stdout(io.StringIO()) as screen:
            menu.main()
        self.assertIn("No recordings yet", screen.getvalue())
        run.assert_not_called()
        self.assertEqual(list(self.datasets.iterdir()), [])

    def test_inspect_and_return_to_menu(self):
        self.dataset()
        with patch("builtins.input", side_effect=["2", "1", "1", "", "q", "q"]), \
                contextlib.redirect_stdout(io.StringIO()) as screen:
            menu.main()
        self.assertIn("gate-pass: complete (run test-run)", screen.getvalue())
        self.assertGreater(screen.getvalue().count("BlueBoat recording tools"), 1)

    def test_record_retries_invalid_inputs_and_uses_explicit_settings(self):
        self.dataset("existing")
        with patch("builtins.input", side_effect=["../escape", "existing", "fresh", "bad", "0", "2.5"]), \
                patch.object(menu, "run_foreground", return_value=0) as run, \
                contextlib.redirect_stdout(io.StringIO()):
            menu.record()
        self.assertEqual(run.call_args.args[0][-5:], ["record", "--name", "fresh", "--duration", "2.5"])
        self.assertEqual(run.call_args.args[1]["DURATION"], "")

    def test_replay_validates_settings_and_clears_inherited_pause(self):
        path = self.dataset()
        with patch("builtins.input", side_effect=["bad", "0", "0.5", "0", "233", "98", "n"]), \
                patch.object(menu, "run_foreground", return_value=0) as run, \
                contextlib.redirect_stdout(io.StringIO()):
            menu.replay(path, with_viewer=False)
        args, environment = run.call_args.args
        self.assertEqual(args[-4:], ["--rate", "0.5", "--domain", "98"])
        self.assertNotIn("--start-paused", args)
        self.assertEqual(environment["START_PAUSED"], "")

    def test_incomplete_recording_cannot_be_replayed(self):
        path = self.dataset(status="incomplete")
        with patch.object(menu, "run_foreground") as run, contextlib.redirect_stdout(io.StringIO()) as screen:
            menu.replay(path, with_viewer=False)
        self.assertIn("incomplete", screen.getvalue())
        run.assert_not_called()

    def test_combined_replay_closes_only_its_own_viewer(self):
        path = self.dataset()
        viewer = MagicMock(returncode=0)
        viewer.wait.side_effect = subprocess.TimeoutExpired("viewer", 1)
        with patch("builtins.input", side_effect=["1", "97", "y"]), \
                patch.object(menu.subprocess, "Popen", return_value=viewer) as launch, \
                patch.object(menu, "run_foreground", return_value=0) as run, \
                patch.object(menu, "stop_viewer") as stop, contextlib.redirect_stdout(io.StringIO()):
            menu.replay(path, with_viewer=True)
        environment = launch.call_args.kwargs["env"]
        self.assertEqual(environment["ROS_DOMAIN_ID"], "97")
        self.assertTrue(environment["COMPOSE_PROJECT_NAME"].startswith("maritime-recording-view-"))
        self.assertIn("--start-paused", run.call_args.args[0])
        stop.assert_called_once_with(viewer, environment["COMPOSE_PROJECT_NAME"])

    def test_cleanup_filters_by_unique_project(self):
        viewer = MagicMock()
        with patch.object(menu.cli, "output", return_value="viewer-container\n") as query, \
                patch.object(menu.subprocess, "run") as stop:
            menu.stop_viewer(viewer, "maritime-recording-view-test")
        self.assertEqual(query.call_args.args[0][-1],
                         "label=com.docker.compose.project=maritime-recording-view-test")
        self.assertEqual(stop.call_args.args[0], ["docker", "stop", "--timeout", "5", "viewer-container"])

    def test_benchmark_selects_method_rate_and_isolated_domain(self):
        path = self.dataset()
        with patch("builtins.input", side_effect=["2", "0.5", "0", "98"]), \
                patch.object(menu, "run_foreground", return_value=0) as run, \
                contextlib.redirect_stdout(io.StringIO()):
            menu.benchmark(path)
        args = run.call_args.args[0]
        self.assertEqual(args[-10:], ["--recording", "gate-pass", "--method", "triangulation",
                                      "--pose-time-offset", "0.0", "--rate", "0.5", "--domain", "98"])

    def test_rgb_map_selects_explicit_clock_offset(self):
        path = self.dataset()
        with patch("builtins.input", side_effect=["3", "-123.5", "1", "97"]), \
                patch.object(menu, "run_foreground", return_value=0) as run, \
                contextlib.redirect_stdout(io.StringIO()):
            menu.benchmark(path)
        args = run.call_args.args[0]
        self.assertEqual(args[args.index("--method")+1], "rgb_mapping")
        self.assertEqual(args[args.index("--pose-time-offset")+1], "-123.5")


class EntryPointTests(unittest.TestCase):
    def environment(self):
        environment = dict(os.environ)
        for name in ("NAME", "RECORDING", "DURATION", "RATE", "START_PAUSED", "REPLAY_DOMAIN_ID"):
            environment.pop(name, None)
        return environment

    def test_redirected_make_record_fails_without_prompting(self):
        result = subprocess.run(["make", "record"], cwd=SIMULATION, env=self.environment(),
                                input="", capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("menu needs a terminal", result.stderr)

    def test_make_record_opens_menu_and_quits_in_a_real_terminal(self):
        master, slave = pty.openpty()
        process = subprocess.Popen(["make", "record"], cwd=SIMULATION, env=self.environment(),
                                   stdin=slave, stdout=slave, stderr=slave)
        os.close(slave)
        transcript = bytearray()
        try:
            os.write(master, b"invalid\nq\n")
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if not select.select([master], [], [], .1)[0]:
                    continue
                try:
                    chunk = os.read(master, 65536)
                except OSError as error:
                    if error.errno == errno.EIO:
                        break
                    raise
                if not chunk:
                    break
                transcript.extend(chunk)
            self.assertEqual(process.wait(timeout=1), 0)
            self.assertIn("BlueBoat recording tools", transcript.decode())
            self.assertIn("Choose 1, 2, 3, 4", transcript.decode())
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            os.close(master)


if __name__ == "__main__":
    unittest.main()
