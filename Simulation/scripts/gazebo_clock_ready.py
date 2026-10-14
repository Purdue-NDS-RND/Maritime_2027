#!/usr/bin/env python3
"""Probe two live Gazebo clock samples; a paused clock is never ready."""

import argparse
import re
import subprocess


def advancing_clock(output):
    samples = []
    for body in re.findall(r"sim\s*\{([^}]*)\}", output):
        seconds = re.search(r"\bsec:\s*(\d+)", body)
        nanoseconds = re.search(r"\bnsec:\s*(\d+)", body)
        samples.append((int(seconds.group(1)) if seconds else 0) * 1_000_000_000
                       + (int(nanoseconds.group(1)) if nanoseconds else 0))
    return len(samples) >= 2 and samples[-1] > samples[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topic")
    args = parser.parse_args()
    try:
        result = subprocess.run(
            ["gz", "topic", "-e", "-t", args.topic, "-n", "2"],
            capture_output=True, text=True, timeout=4, check=False,
        )
    except subprocess.TimeoutExpired:
        raise SystemExit("Gazebo clock readiness: two live samples timed out") from None
    if result.returncode or not advancing_clock(result.stdout):
        raise SystemExit("Gazebo clock readiness: simulation time is not advancing")


if __name__ == "__main__":
    main()
