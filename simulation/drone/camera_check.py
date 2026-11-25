"""Check or capture RGB images from the Gazebo Iris camera."""

import argparse
from contextlib import closing
from pathlib import Path
from queue import Empty, Full, Queue
import time

import cv2
from cv2 import aruco
from gz.msgs10.image_pb2 import Image, RGB_INT8
from gz.transport13 import Node
import numpy as np
from pymavlink import mavutil


IMAGE_TOPIC = "/iris/down_camera/image"


def frames(timeout):
    queue = Queue(maxsize=1)

    def receive(message):
        try:
            queue.put_nowait(message)
        except Full:
            pass

    node = Node()
    if not node.subscribe(Image, IMAGE_TOPIC, receive):
        raise SystemExit(f"Could not subscribe to {IMAGE_TOPIC}")
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                image = queue.get(timeout=max(0, deadline - time.monotonic()))
            except Empty:
                break
            if image.pixel_format_type != RGB_INT8:
                raise SystemExit(f"Unexpected camera pixel format {image.pixel_format_type}")
            timestamp = (image.header.stamp.sec, image.header.stamp.nsec)
            rgb = np.frombuffer(image.data, dtype=np.uint8).reshape(image.height, image.step)
            yield timestamp, rgb[:, :image.width * 3].reshape(image.height, image.width, 3)
    finally:
        node.unsubscribe(IMAGE_TOPIC)


def check_ready():
    first = None
    with closing(frames(45)) as images:
        for stamp, _ in images:
            if first is None:
                first = stamp
            elif stamp > first:
                break
        else:
            raise SystemExit(f"No advancing RGB frames on {IMAGE_TOPIC}; see gazebo.log")
    connection = mavutil.mavlink_connection("tcp:127.0.0.1:5760", retries=2)
    try:
        heartbeat = connection.wait_heartbeat(timeout=15)
        if heartbeat is None or heartbeat.type != mavutil.mavlink.MAV_TYPE_QUADROTOR:
            raise SystemExit("No ArduCopter heartbeat; see sitl.log")
    finally:
        connection.close()


def capture(expected):
    dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    if hasattr(aruco, "ArucoDetector"):
        detect = aruco.ArucoDetector(dictionary).detectMarkers
    else:
        detect = lambda gray: aruco.detectMarkers(gray, dictionary)
    with closing(frames(15)) as images:
        for stamp, rgb in images:
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            _, ids, _ = detect(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
            markers = [] if ids is None else sorted(ids.ravel().tolist())
            if expected is None or expected in markers:
                break
        else:
            raise SystemExit(f"No matching RGB frame within 15 seconds (expected marker: {expected})")

    seconds, nanos = stamp
    run_dir = Path("/sim") / Path("/sim/latest-run.txt").read_text().strip()
    output = run_dir / f"camera-{seconds}-{nanos:09d}.png"
    if not cv2.imwrite(str(output), bgr):
        raise SystemExit(f"Could not save {output}")
    print(f"Saved logs/drone-sitl/{run_dir.name}/{output.name}. Detected marker IDs: {markers}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--ready", action="store_true")
    mode.add_argument("--expect", type=int, choices=range(50), metavar="ID")
    args = parser.parse_args()
    if args.ready:
        check_ready()
    else:
        capture(args.expect)


if __name__ == "__main__":
    main()
