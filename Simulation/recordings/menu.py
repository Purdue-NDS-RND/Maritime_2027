"""Interactive front end for the recording commands; no extra dependencies."""

import argparse
from datetime import datetime
import json
import os
import signal
import subprocess
import sys
import tempfile
import uuid

import recordings as cli


class Cancelled(Exception):
    """Return from the current menu or prompt without starting an action."""


def ask(prompt, default="", convert=str):
    while True:
        answer = input(prompt).strip()
        if answer.lower() in ("q", "b"):
            raise Cancelled
        try:
            return convert(answer or default)
        except (ValueError, argparse.ArgumentTypeError) as error:
            print(f"  {error}")


def choose(prompt, choices, default=""):
    def validate(answer):
        if answer.lower() not in choices:
            raise ValueError(f"Choose {', '.join(choices)}, or q to go back.")
        return answer.lower()
    return ask(prompt, default, validate)


def run_foreground(command, env=None):
    # Let the child handle Ctrl-C and finish its bag before showing the menu.
    # A callable handler (rather than SIG_IGN) resets to default in the child.
    previous = signal.signal(signal.SIGINT, lambda *_: None)
    try:
        return subprocess.call(command, env=env, cwd=cli.SIMULATION)
    finally:
        signal.signal(signal.SIGINT, previous)


def command(*arguments):
    return [sys.executable, str(cli.TOOLS / "recordings.py"), *arguments]


def saved_recordings():
    if not cli.DATASETS.exists():
        return []
    return sorted((path for path in cli.DATASETS.iterdir()
                   if path.is_dir() and not path.is_symlink() and (path / "dataset.json").is_file()),
                  key=lambda path: path.stat().st_mtime, reverse=True)


def summary(path):
    try:
        metadata = json.loads((path / "dataset.json").read_text())
        description = metadata["status"]
        report = path / "quality.json"
        if report.exists():
            quality = json.loads(report.read_text())
            result = "PASS" if quality["passed"] else "FAIL"
            description += f" | {result} | {quality['duration_s']:.1f}s | {quality['size_bytes'] / 1e9:.2f} GB"
        return description
    except (OSError, ValueError, KeyError, TypeError):
        return "metadata unavailable; inspect for details"


def select_recording():
    paths = saved_recordings()
    if not paths:
        print("\nNo recordings yet. Choose 'Record a new run' first.")
        return None
    print("\nSaved recordings (newest first)")
    for index, path in enumerate(paths, 1):
        print(f"  {index}) {path.name}\n     {summary(path)}")

    def select(answer):
        index = int(answer)
        if not 1 <= index <= len(paths):
            raise ValueError(f"Choose a recording from 1 to {len(paths)}.")
        return paths[index - 1]
    return ask("Recording number [q: back]: ", convert=select)


def record():
    default = datetime.now().strftime("run-%Y%m%d-%H%M%S")

    def available_name(name):
        path = cli.dataset_path(name)
        if path.exists():
            raise ValueError("That name already exists. Choose a new name.")
        return name

    name = ask(f"Recording name [{default}]: ", default, available_name)
    duration = ask("Duration in wall seconds [Enter: until Ctrl-C]: ",
                   convert=lambda value: cli.positive_number(value) if value else None)
    arguments = ["record", "--name", name]
    if duration is not None:
        arguments += ["--duration", str(duration)]
    # Explicit arguments should not inherit an unrelated duration from Make.
    environment = dict(os.environ, DURATION="")
    print("\nCapturing the running buoy scenario. Drive with teleop or QGroundControl.")
    print("Ctrl-C finishes this recording and returns here; it does not stop the boat.\n")
    run_foreground(command(*arguments), environment)
    path = cli.dataset_path(name)
    if path.exists():
        print(f"\n{name}: {summary(path)}")


def replay(path, with_viewer):
    metadata = json.loads((path / "dataset.json").read_text())
    if metadata["status"] != "complete":
        print("\nThis recording is incomplete. Inspect its details or recorder log first.")
        return
    rate = ask("Playback speed [1]: ", "1", cli.positive_number)

    def replay_domain(value):
        domain = int(value)
        if not 0 <= domain <= 232 or domain == metadata["capture_domain"]:
            raise ValueError("Choose a ROS domain from 0 to 232, different from the capture domain.")
        return domain

    domain = ask("Replay ROS domain [97]: ", "97", replay_domain)
    paused = choose("Start paused? [Y/n]: ", ("y", "n"), "y") == "y"
    arguments = ["replay", "--recording", path.name, "--rate", str(rate), "--domain", str(domain)]
    if paused:
        arguments.append("--start-paused")
    print("\nSpace: pause/resume. Ctrl-C: return to the menu.")
    environment = dict(os.environ, START_PAUSED="")
    if not with_viewer:
        run_foreground(command(*arguments), environment)
        return

    # Give this viewer its own Compose project so cleanup cannot stop an
    # existing Monitor window or the live simulation.
    project = "maritime-recording-view-" + uuid.uuid4().hex[:12]
    environment.update(ROS_DOMAIN_ID=str(domain), COMPOSE_PROJECT_NAME=project)
    monitor = cli.SIMULATION.parent / "Monitor" / "scripts" / "monitor"
    with tempfile.TemporaryFile(mode="w+t") as log:
        viewer = subprocess.Popen([str(monitor), "rviz-sim"], env=environment,
                                  stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                  start_new_session=True)
        try:
            try:
                viewer.wait(timeout=1)
            except subprocess.TimeoutExpired:
                run_foreground(command(*arguments), environment)
        finally:
            stop_viewer(viewer, project)
            log.seek(0)
            if viewer.returncode not in (0, -signal.SIGTERM, 130, 143):
                print(log.read())


def stop_viewer(viewer, project):
    """Stop only the disposable viewer launched for this replay."""
    try:
        identifiers = cli.output(["docker", "ps", "-q", "--filter",
                                  f"label=com.docker.compose.project={project}"]).split()
        if identifiers:
            subprocess.run(["docker", "stop", "--timeout", "5", *identifiers],
                           stdout=subprocess.DEVNULL, check=False, timeout=10)
        viewer.wait(timeout=5)
    except (OSError, subprocess.SubprocessError):
        if viewer.poll() is None:
            os.killpg(viewer.pid, signal.SIGTERM)
            try:
                viewer.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(viewer.pid, signal.SIGKILL)
                viewer.wait()


def benchmark(path):
    if json.loads((path / "dataset.json").read_text())["status"] != "complete":
        print("\nThis recording is incomplete. Inspect its details first.")
        return
    print("\nPositioning methods are placeholders: this verifies the ROS pipeline and saves outputs.")
    method = choose("Method [1: depth, 2: RGB triangulation]: ", ("1", "2"), "1")
    rate = ask("Playback speed [1]: ", "1", cli.positive_number)
    capture = json.loads((path / "dataset.json").read_text())["capture_domain"]
    def domain_number(value):
        domain = int(value)
        if not 0 <= domain <= 232 or domain == capture:
            raise ValueError("Choose a domain from 0 to 232 different from the capture domain.")
        return domain
    domain = ask("Replay ROS domain [97]: ", "97", domain_number)
    tool = cli.SIMULATION / "tests/evaluation/benchmarking/tools.py"
    run_foreground([sys.executable, str(tool), "run", "--recording", path.name,
                    "--method", "depth" if method == "1" else "triangulation",
                    "--rate", str(rate), "--domain", str(domain)])


def browse():
    path = select_recording()
    if path is None:
        return
    while True:
        print(f"\n{name_heading(path)}\n  1) Inspect quality and run details\n"
              "  2) Replay in this terminal\n  3) Replay with RViz\n"
              "  4) Show recorder log\n  5) Run ROS localization benchmark\n  q) Back")
        try:
            selection = choose("Choose [1]: ", ("1", "2", "3", "4", "5"), "1")
            if selection == "1":
                cli.show_info(path)
            elif selection in ("2", "3"):
                replay(path, with_viewer=selection == "3")
            elif selection == "5":
                benchmark(path)
            else:
                print("\n" + "\n".join((path / "recorder.log").read_text().splitlines()[-60:]))
            ask("\nPress Enter to return to this recording... ")
        except Cancelled:
            return
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            print(f"\nCould not complete that action: {error}")


def name_heading(path):
    return f"{path.name}\n  {summary(path)}"


def main():
    try:
        while True:
            print("\n  BlueBoat recording tools\n  ------------------------\n"
                  "  1) Record a new run\n  2) Browse recordings / replay / RViz\n"
                  "  3) Build or update recording tools\n  4) Help\n"
                  "  5) Build or update benchmark tools\n  q) Quit\n")
            try:
                selection = choose("Choose [1]: ", ("1", "2", "3", "4", "5"), "1")
            except Cancelled:
                return
            try:
                if selection == "1":
                    record()
                elif selection == "2":
                    browse()
                elif selection == "3":
                    run_foreground(["make", "-C", str(cli.SIMULATION.parent / "Monitor"), "build"])
                elif selection == "5":
                    run_foreground(["make", "benchmark-build"])
                else:
                    print("\nRecord a running buoy scenario while driving with teleop or QGroundControl.\n"
                          "Browse saved runs to inspect their quality, replay, or open replay with RViz.\n"
                          "Ctrl-C finishes an active capture/replay; q goes back at prompts.\n"
                          f"Datasets: {cli.DATASETS}\n"
                          f"Guide: {cli.SIMULATION / 'docs/RECORDING_AND_REPLAY.md'}")
                    ask("\nPress Enter to return... ")
            except Cancelled:
                continue
            except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
                print(f"\nCould not complete that action: {error}")
    except (EOFError, KeyboardInterrupt):
        print("\nRecording menu closed.")
