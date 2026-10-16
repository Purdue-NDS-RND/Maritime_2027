"""Host entry points for detector development and offline benchmark preparation."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[4]
SIMULATION = ROOT / "Simulation"
TOOLS = Path(__file__).resolve().parent
PERCEPTION = ROOT / "autonomy/ros_ws/src/maritime_perception"
CONFIG = PERCEPTION / "config/aruco.yaml"
IMAGE = "maritime-benchmark:jazzy"


def safe_name(name):
    if not name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name) or name in (".", ".."):
        raise ValueError("Use a name containing letters, numbers, '.', '_' or '-'")
    return name


def recording(name):
    path = SIMULATION / "logs/recordings" / safe_name(name)
    if path.is_symlink():
        raise ValueError("Recording must not be a symbolic link")
    metadata = json.loads((path / "dataset.json").read_text())
    if metadata["status"] != "complete":
        raise ValueError("Recording must be complete")
    return path, metadata


def foreground(command):
    # Let Docker forward Ctrl-C and wait for its container to finish cleanup.
    previous = signal.signal(signal.SIGINT, lambda *_: None)
    try:
        return subprocess.call(command)
    finally:
        signal.signal(signal.SIGINT, previous)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "test", "detect", "run"))
    parser.add_argument("--recording", default=os.environ.get("RECORDING"))
    parser.add_argument("--method", choices=("detections", "depth", "triangulation"),
                        default=os.environ.get("METHOD") or "detections")
    parser.add_argument("--domain", type=int, default=os.environ.get("REPLAY_DOMAIN_ID") or 97)
    parser.add_argument("--name", help="Unique output directory name; generated when omitted")
    args = parser.parse_args()
    try:
        if args.command == "build":
            subprocess.run(["docker", "build", "-t", "maritime-autonomy:jazzy", "-f",
                            str(ROOT / "autonomy/container/Dockerfile"), str(ROOT / "autonomy")], check=True)
            subprocess.run(["docker", "build", "-t", IMAGE, str(TOOLS)], check=True)
            return
        if args.command == "test":
            raise SystemExit(foreground([
                "docker", "run", "--rm", "--network", "none",
                "-e", "ROS_DOMAIN_ID=96", "-e", "PYTHONDONTWRITEBYTECODE=1",
                "-v", f"{TOOLS}:/opt/benchmark:ro",
                *[argument for package in ("maritime_perception", "maritime_localization")
                  for argument in ("-v", f"{ROOT / 'autonomy/ros_ws/src' / package}:/opt/autonomy_ws/src/{package}:ro")],
                "--entrypoint", "bash", IMAGE, "-c",
                'source /etc/maritime_autonomy_setup.bash && python3 -m unittest discover -s /opt/benchmark -p "test_*.py" -v',
            ]))
        if args.method != "detections":
            raise ValueError(f"{args.method} positioning is not implemented; use METHOD=detections")
        dataset, metadata = recording(args.recording)
        command = ["docker", "run", "--rm", "--init", "--user", f"{os.getuid()}:{os.getgid()}",
                   "-e", "PYTHONDONTWRITEBYTECODE=1"]
        # Source mounts let Python edits take effect without rebuilding images.
        for package in ("maritime_perception", "maritime_localization"):
            source = ROOT / "autonomy/ros_ws/src" / package
            command += ["-v", f"{source}:/opt/autonomy_ws/src/{package}:ro"]
        if args.command == "detect":
            if not 0 <= args.domain <= 232 or args.domain == metadata["capture_domain"]:
                raise ValueError("Choose a domain from 0 to 232 different from the live capture domain")
            command += ["--network", "host", "--ipc", "host",
                        "-e", f"ROS_DOMAIN_ID={args.domain}",
                        "-e", "FASTRTPS_DEFAULT_PROFILES_FILE=/dataset/transport.xml",
                        "-v", f"{dataset / 'transport.xml'}:/dataset/transport.xml:ro",
                        "--entrypoint", "bash", IMAGE, "-c",
                        "source /etc/maritime_autonomy_setup.bash && exec "
                        "/opt/autonomy_ws/install/maritime_perception/lib/maritime_perception/aruco_detector "
                        "--ros-args --params-file "
                        "/opt/autonomy_ws/src/maritime_perception/config/aruco.yaml "
                        "-r __ns:=/perception/camera_0 "
                        "-r image:=/sensors/camera_0/color/image_raw "
                        "-p use_sim_time:=true -p publish_debug_image:=true"]
            raise SystemExit(foreground(command))
        name = safe_name(args.name or datetime.now(timezone.utc).strftime("detections-%Y%m%dT%H%M%S%fZ"))
        parent = SIMULATION / "logs/benchmarks" / dataset.name
        if parent.is_symlink():
            raise ValueError("Benchmark output parent must not be a symbolic link")
        destination = parent / name
        if destination.exists() or destination.is_symlink():
            raise ValueError("Benchmark output already exists; choose a new name")
        parent.mkdir(parents=True, exist_ok=True)
        command += ["--network", "none", "-v", f"{dataset}:/dataset:ro",
                    "-v", f"{parent}:/results", "-v", f"{TOOLS}:/opt/benchmark:ro", IMAGE,
                    "--dataset", "/dataset", "--output", f"/results/{name}",
                    "--config", "/opt/autonomy_ws/src/maritime_perception/config/aruco.yaml"]
        # Resolve the exact local image before launch; record revision including dirty state.
        provenance = {
            "image_id": subprocess.check_output(["docker", "image", "inspect", "--format", "{{.Id}}", IMAGE], text=True).strip(),
            "repository_revision": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
            "repository_dirty": bool(subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True)),
            "source_sha256": {
                str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                for base in (PERCEPTION, ROOT / "autonomy/ros_ws/src/maritime_localization", TOOLS)
                for path in sorted(base.rglob("*")) if path.suffix in (".py", ".yaml")
            },
        }
        result = foreground(command)
        if destination.is_dir():
            (destination / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
        print(f"Results: {destination}", flush=True)
        raise SystemExit(result)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
