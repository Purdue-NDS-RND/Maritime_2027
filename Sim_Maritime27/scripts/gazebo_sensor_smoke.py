#!/usr/bin/env python3
"""Check RGB-D source cadence and synchronization in Gazebo simulated time."""

from __future__ import annotations

import statistics
import threading
import time

from gz.msgs10.image_pb2 import Image
from gz.transport13 import Node


TARGET_SAMPLES = 120


def stamp_ns(message: Image) -> int:
    return message.header.stamp.sec * 1_000_000_000 + message.header.stamp.nsec


def main() -> None:
    lock = threading.Lock()
    stamps: dict[str, list[int]] = {"RGB": [], "depth": []}
    wall_times: dict[str, list[float]] = {"RGB": [], "depth": []}

    def callback(label: str):
        def receive(message: Image) -> None:
            with lock:
                if len(stamps[label]) < TARGET_SAMPLES:
                    stamps[label].append(stamp_ns(message))
                    wall_times[label].append(time.monotonic())

        return receive

    node = Node()
    node.subscribe(Image, "/blueboat/rgbd_camera/image", callback("RGB"))
    node.subscribe(Image, "/blueboat/rgbd_camera/depth_image", callback("depth"))
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        with lock:
            if all(len(values) >= TARGET_SAMPLES for values in stamps.values()):
                break
        time.sleep(0.05)

    for label in ("RGB", "depth"):
        values = stamps[label]
        if len(values) < 100:
            raise SystemExit(f"Gazebo {label} delivered only {len(values)} source samples")
        if values != sorted(values) or len(values) != len(set(values)):
            raise SystemExit(f"Gazebo {label} timestamps are not strictly monotonic")
        periods = [(b - a) / 1e9 for a, b in zip(values, values[1:])]
        simulated_rate = 1.0 / statistics.median(periods)
        wall_periods = [b - a for a, b in zip(wall_times[label], wall_times[label][1:])]
        wall_rate = 1.0 / statistics.median(wall_periods)
        if not 27.0 <= simulated_rate <= 33.0:
            raise SystemExit(f"Gazebo {label} simulated-time rate {simulated_rate:.2f} Hz is outside 27-33 Hz")
        print(
            f"Gazebo {label}: {simulated_rate:.2f} Hz in simulated time; "
            f"{wall_rate:.2f} Hz median callback cadence"
        )

    exact_pairs = set(stamps["RGB"]) & set(stamps["depth"])
    if len(exact_pairs) < 100:
        raise SystemExit(f"Gazebo produced only {len(exact_pairs)} exact RGB/depth source pairs")
    print(f"Gazebo RGB-D source PASS: {len(exact_pairs)} exact timestamp pairs")


if __name__ == "__main__":
    main()
