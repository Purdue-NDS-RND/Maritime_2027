#!/usr/bin/env python3
"""Host commands for simulation recordings. ROS runs in the Monitor image."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


SIMULATION = Path(__file__).resolve().parents[1]
DATASETS = SIMULATION / "logs" / "recordings"
TOOLS = Path(__file__).resolve().parent
TIMING_NOTE = (
    "Camera/truth headers use simulation time; MAVROS headers use Unix time. "
    "Original headers are preserved. Camera-to-state synchronization is unvalidated."
)


def positive_number(value):
    number = float(value)
    if not 0 < number < float("inf"):
        raise argparse.ArgumentTypeError("must be a finite number greater than zero")
    return number


def dataset_path(name):
    if not name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
        raise ValueError("provide a recording name using letters, numbers, '.', '_' or '-'")
    path = DATASETS / name
    if path.is_symlink():
        raise ValueError("recording paths must not be symbolic links")
    return path


def output(command):
    return subprocess.check_output(command, text=True).strip()


def prepare_recording(destination, image):
    """Copy provenance from the run actually owned by the running containers."""
    containers = json.loads(output([
        "docker", "inspect", "maritime-sim-adapter", "ardupilot-blueboat-sim",
    ]))
    environments = []
    for container in containers:
        if not container["State"]["Running"]:
            raise ValueError("start a buoy scenario with 'SCENARIO=gate make run' first")
        environments.append(dict(item.split("=", 1) for item in container["Config"]["Env"]))
    adapter, simulator = environments
    run_id = adapter.get("RUN_ID", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", run_id):
        raise ValueError("the running Adapter has no valid run identity")
    for field in ("RUN_ID", "RUN_CONFIG_SHA256"):
        if not adapter.get(field) or adapter[field] != simulator.get(field):
            raise ValueError(f"simulator and Adapter disagree on {field}")
    domain = int(os.environ.get("ROS_DOMAIN_ID", adapter.get("ROS_DOMAIN_ID", "0")))
    if domain != int(adapter.get("ROS_DOMAIN_ID", "0")):
        raise ValueError("ROS_DOMAIN_ID must match the running Adapter")
    run = SIMULATION / "logs" / "runs" / run_id
    compose = (run / "compose.yaml").read_bytes()
    if hashlib.sha256(compose).hexdigest() != adapter["RUN_CONFIG_SHA256"]:
        raise ValueError("archived run configuration does not match the running stack")
    manifest = (run / "scenario.manifest.json").read_bytes()
    scenario = json.loads(manifest)
    if scenario.get("schema_version") != 1 or not scenario.get("buoys"):
        raise ValueError("recording requires a version-1 buoy scenario manifest")
    # The Adapter loads this mounted manifest. Refuse a stale archived roster.
    mounts = containers[0]["Mounts"]
    mount = next(item for item in mounts if item["Destination"] == "/scenario")
    active = Path(mount["Source"]) / "active.manifest.json"
    if active.read_bytes() != manifest:
        raise ValueError("active scenario differs from the archived running scenario")
    identity = (run / "identity.txt").read_bytes()
    metadata = {
        "schema_version": 1,
        "name": destination.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "preparing",
        "run_id": run_id,
        "run_config_sha256": adapter["RUN_CONFIG_SHA256"],
        "capture_domain": domain,
        "repository_revision": output(["git", "-C", str(SIMULATION), "rev-parse", "HEAD"]),
        "repository_dirty": bool(output(["git", "-C", str(SIMULATION), "status", "--porcelain"])),
        "images": {item["Name"].lstrip("/"): item["Image"] for item in containers},
        "tools_image": output(["docker", "image", "inspect", "--format", "{{.Id}}", image]),
        "timing_note": TIMING_NOTE,
    }
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "dataset.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (destination / "compose.yaml").write_bytes(compose)
    (destination / "scenario.manifest.json").write_bytes(manifest)
    (destination / "identity.txt").write_bytes(identity)
    shutil.copyfile(TOOLS / "topics.yaml", destination / "topics.yaml")
    shutil.copyfile(SIMULATION.parent / "Adapter/simulation/config/fastdds.xml", destination / "transport.xml")
    return domain


def show_info(destination):
    metadata = json.loads((destination / "dataset.json").read_text())
    print(f"{metadata['name']}: {metadata['status']} (run {metadata['run_id']})")
    print(metadata["timing_note"])
    if metadata.get("error"):
        print(f"Capture error: {metadata['error']}")
    report_path = destination / "quality.json"
    if not report_path.exists():
        print("No completed dataset check. Recording may be active or incomplete.")
        return
    report = json.loads(report_path.read_text())
    print(f"Duration: {report['duration_s']:.2f} sim seconds; size: {report['size_bytes'] / 1e6:.1f} MB")
    print(f"Exact RGB-D triples: {report['rgbd']['matched']}; rate: {report['rgbd']['rate_hz']:.2f} Hz")
    print(f"Unmatched RGB/depth/info: {list(report['rgbd']['unmatched'].values())}")
    print(f"Boat displacement: {report['boat_displacement_m']:.3f} m")
    losses = report.get("reported_transport_losses", "not saved; see recorder.log")
    print(f"Recorder-reported transport losses: {losses}")
    print(f"Dataset checks: {'PASS' if report['passed'] else 'FAIL'}")
    for error in report["errors"]:
        print(f"  {error}")
    for topic, stats in sorted(report["topics"].items()):
        print(f"  {stats['count']:>7}  {topic} (largest gap {stats['max_gap_s']:.3f}s)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("menu", help="open the interactive recording tools")
    record = commands.add_parser("record", help="record a running buoy scenario; Ctrl-C finishes")
    record.add_argument("--name", default=os.environ.get("NAME"))
    record.add_argument("--duration", type=positive_number, default=os.environ.get("DURATION") or None,
                        help="optional duration in wall seconds; otherwise record until Ctrl-C")
    info = commands.add_parser("info", help="show provenance and saved dataset checks")
    replay = commands.add_parser("replay", help="play a dataset on a separate ROS domain")
    for command in (info, replay):
        command.add_argument("--recording", default=os.environ.get("RECORDING"))
    replay.add_argument("--rate", type=positive_number, default=os.environ.get("RATE") or "1")
    replay.add_argument("--domain", type=int, default=os.environ.get("REPLAY_DOMAIN_ID") or "97")
    replay.add_argument("--start-paused", action="store_true", default=os.environ.get("START_PAUSED") == "1")
    args = parser.parse_args()
    if args.command == "menu" or (args.command == "record" and not args.name):
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            parser.exit(1, "ERROR: the recording menu needs a terminal; use 'make record NAME=<name>' for automation.\n")
        from menu import main as recording_menu
        recording_menu()
        return
    try:
        destination = dataset_path(args.name if args.command == "record" else args.recording)
        if args.command == "info":
            show_info(destination)
            return
        image = os.environ.get("MONITOR_IMAGE", "maritime-monitor:jazzy")
        if args.command == "record":
            if destination.exists():
                raise ValueError(f"recording already exists: {destination}; choose another NAME")
            domain = prepare_recording(destination, image)
            worker_args = ["record"]
            if args.duration:
                worker_args += ["--duration", str(args.duration)]
        else:
            metadata = json.loads((destination / "dataset.json").read_text())
            if metadata["status"] != "complete":
                raise ValueError("recording is incomplete; inspect it with recording-info first")
            domain = args.domain
            if domain == metadata["capture_domain"]:
                raise ValueError("use a different replay domain to keep playback separate from live inputs")
            worker_args = ["replay", "--rate", str(args.rate)]
            if args.start_paused:
                worker_args.append("--start-paused")
        if not 0 <= domain <= 232:
            raise ValueError("ROS domain must be between 0 and 232")
        command = ["docker", "run", "--rm", "--init", "--network", "host", "--ipc", "host",
                   "--user", "0:0" if args.command == "record" else f"{os.getuid()}:{os.getgid()}",
                   "-e", f"ROS_DOMAIN_ID={domain}",
                   "-e", "FASTRTPS_DEFAULT_PROFILES_FILE=/recording/transport.xml",
                   "-v", f"{TOOLS}:/recording-tools:ro",
                   "-v", f"{destination}:/recording" + (":ro" if args.command == "replay" else "")]
        if args.command == "record":
            # Match the root Adapter's shared-memory ports. The worker restores
            # output ownership on exit; ordinary Monitor/replay stays host-user.
            command += ["-e", f"RECORDING_UID={os.getuid()}", "-e", f"RECORDING_GID={os.getgid()}"]
        if sys.stdin.isatty() and sys.stdout.isatty():
            command.append("-it")
        print(f"{args.command.capitalize()}: {destination} (ROS domain {domain})", flush=True)
        if args.command == "replay":
            print(f"View: make -C ../Monitor rviz-sim ROS_DOMAIN_ID={domain}", flush=True)
        command += [image, "python3", "/recording-tools/session.py", *worker_args]
        os.execvp(command[0], command)
    except (OSError, ValueError, KeyError, StopIteration, subprocess.CalledProcessError) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()
