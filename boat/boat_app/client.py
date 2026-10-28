"""Local command client: exit zero only when the service confirms success."""

import argparse
import json
import time

import rclpy
from std_srvs.srv import Trigger


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("upload", "start", "stop", "disarm"))
    args = parser.parse_args()
    rclpy.init(args=[])
    node = rclpy.create_node("boat_mission_command")
    try:
        client = node.create_client(Trigger, f"/boat_mission/{args.command}")
        if not client.wait_for_service(timeout_sec=10):
            raise RuntimeError("boat service unavailable after 10 seconds")
        future = client.call_async(Trigger.Request())
        deadline = time.monotonic() + 180
        while not future.done() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        if not future.done():
            raise RuntimeError("service response timed out; inspect boat status before issuing another command")
        response = future.result()
        print(json.dumps({"success": response.success, "message": response.message}), flush=True)
        return 0 if response.success else 1
    except Exception as error:
        print(json.dumps({"success": False, "message": str(error)}), flush=True)
        return 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
