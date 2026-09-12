#!/usr/bin/env python3
"""End-to-end autonomous navigation check for the running BlueBoat SITL."""

from __future__ import annotations

import math
import sys
import time
from dataclasses import dataclass

from pymavlink import mavutil


CONNECTION = "udp:127.0.0.1:14551"
HEARTBEAT_TIMEOUT_S = 30
POSITION_TIMEOUT_S = 45
TRAVEL_TIMEOUT_S = 120
TARGET_DISTANCE_M = 12.0
MIN_MOVEMENT_M = 5.0
ARRIVAL_RADIUS_M = 3.0
RETURN_RADIUS_M = 4.0
HOLD_SPEED_M_S = 0.8
POSITION_ONLY_TYPE_MASK = 3576


class SmokeFailure(RuntimeError):
    """A stage-specific smoke-test failure."""


@dataclass(frozen=True)
class Position:
    lat: float
    lon: float
    relative_alt_m: float
    speed_m_s: float


def log(stage: str, message: str) -> None:
    print(f"[{stage}] {message}", flush=True)


def fail(stage: str, message: str) -> None:
    raise SmokeFailure(f"[{stage}] {message}")


def distance_m(first: Position, second: Position) -> float:
    radius_m = 6_371_000.0
    lat1 = math.radians(first.lat)
    lat2 = math.radians(second.lat)
    dlat = lat2 - lat1
    dlon = math.radians(second.lon - first.lon)
    value = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    )
    return radius_m * 2.0 * math.atan2(math.sqrt(value), math.sqrt(1.0 - value))


def offset_north(origin: Position, metres: float) -> Position:
    return Position(
        lat=origin.lat + math.degrees(metres / 6_371_000.0),
        lon=origin.lon,
        relative_alt_m=origin.relative_alt_m,
        speed_m_s=0.0,
    )


def receive_position(master: mavutil.mavfile, timeout_s: float) -> Position:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        message = master.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=1)
        if message is None:
            continue
        return Position(
            lat=message.lat / 1e7,
            lon=message.lon / 1e7,
            relative_alt_m=message.relative_alt / 1000.0,
            speed_m_s=math.hypot(message.vx, message.vy) / 100.0,
        )
    fail("position", f"no GLOBAL_POSITION_INT arrived within {timeout_s:.0f}s")


def read_parameter(master: mavutil.mavfile, name: str, timeout_s: float = 10) -> float:
    encoded_name = name.encode("ascii")
    master.mav.param_request_read_send(
        master.target_system, master.target_component, encoded_name, -1
    )
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        message = master.recv_match(type="PARAM_VALUE", blocking=True, timeout=1)
        if message is None:
            continue
        received_name = message.param_id
        if isinstance(received_name, bytes):
            received_name = received_name.decode("ascii", errors="replace")
        if received_name.rstrip("\x00") == name:
            return float(message.param_value)
    fail("parameters", f"parameter {name} was not returned")


def wait_mode(master: mavutil.mavfile, mode_id: int, timeout_s: float = 15) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        heartbeat = master.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
        if heartbeat is not None and heartbeat.custom_mode == mode_id:
            return
    fail("mode", f"vehicle did not enter custom mode {mode_id}")


def set_mode(master: mavutil.mavfile, name: str) -> None:
    mapping = master.mode_mapping() or {}
    if name not in mapping:
        fail("mode", f"{name} is unavailable; known modes: {sorted(mapping)}")
    mode_id = mapping[name]
    master.mav.set_mode_send(
        master.target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        mode_id,
    )
    wait_mode(master, mode_id)
    log("mode", f"entered {name}")


def wait_armed(master: mavutil.mavfile, armed: bool, timeout_s: float = 20) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        heartbeat = master.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
        if heartbeat is None:
            continue
        is_armed = bool(
            heartbeat.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
        )
        if is_armed == armed:
            return
    state = "arm" if armed else "disarm"
    fail(state, f"vehicle did not {state} within {timeout_s:.0f}s")


def command_arm(master: mavutil.mavfile, armed: bool) -> None:
    master.mav.command_long_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0,
        1 if armed else 0,
        0,
        0,
        0,
        0,
        0,
        0,
    )
    wait_armed(master, armed)
    log("arm" if armed else "disarm", "vehicle state confirmed")


def send_guided_target(master: mavutil.mavfile, target: Position) -> None:
    master.mav.set_position_target_global_int_send(
        0,
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
        POSITION_ONLY_TYPE_MASK,
        int(target.lat * 1e7),
        int(target.lon * 1e7),
        target.relative_alt_m,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )


def travel_to_target(
    master: mavutil.mavfile, origin: Position, target: Position
) -> None:
    deadline = time.monotonic() + TRAVEL_TIMEOUT_S
    max_movement = 0.0
    last_target_send = 0.0
    while time.monotonic() < deadline:
        now = time.monotonic()
        if now - last_target_send >= 1.0:
            send_guided_target(master, target)
            last_target_send = now
        current = receive_position(master, 3)
        moved = distance_m(origin, current)
        remaining = distance_m(current, target)
        max_movement = max(max_movement, moved)
        print(
            f"[travel] moved={moved:.1f}m remaining={remaining:.1f}m speed={current.speed_m_s:.2f}m/s",
            flush=True,
        )
        if max_movement >= MIN_MOVEMENT_M and remaining <= ARRIVAL_RADIUS_M:
            log("travel", "guided target reached")
            return
    fail(
        "travel",
        f"target not reached in {TRAVEL_TIMEOUT_S:.0f}s; maximum movement was {max_movement:.1f}m",
    )


def verify_hold(master: mavutil.mavfile) -> None:
    deadline = time.monotonic() + 30
    consecutive = 0
    while time.monotonic() < deadline:
        current = receive_position(master, 3)
        if current.speed_m_s <= HOLD_SPEED_M_S:
            consecutive += 1
            if consecutive >= 5:
                log("hold", f"speed remained at or below {HOLD_SPEED_M_S:.1f}m/s")
                return
        else:
            consecutive = 0
        time.sleep(0.5)
    fail("hold", f"speed did not settle below {HOLD_SPEED_M_S:.1f}m/s")


def verify_return(master: mavutil.mavfile, origin: Position) -> None:
    deadline = time.monotonic() + TRAVEL_TIMEOUT_S
    while time.monotonic() < deadline:
        current = receive_position(master, 3)
        remaining = distance_m(current, origin)
        print(f"[rtl] distance-from-home={remaining:.1f}m", flush=True)
        if remaining <= RETURN_RADIUS_M:
            log("rtl", "returned to the starting area")
            return
    fail("rtl", f"vehicle did not return within {RETURN_RADIUS_M:.1f}m of start")


def main() -> int:
    master = mavutil.mavlink_connection(CONNECTION, autoreconnect=True)
    armed_by_test = False
    try:
        log("heartbeat", f"waiting on {CONNECTION}")
        heartbeat = master.wait_heartbeat(timeout=HEARTBEAT_TIMEOUT_S)
        if heartbeat is None:
            fail("heartbeat", f"none received within {HEARTBEAT_TIMEOUT_S}s")
        if heartbeat.autopilot != mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA:
            fail("heartbeat", f"unexpected autopilot type {heartbeat.autopilot}")
        if heartbeat.type != mavutil.mavlink.MAV_TYPE_SURFACE_BOAT:
            fail("heartbeat", f"expected a surface boat, received MAV type {heartbeat.type}")
        log(
            "heartbeat",
            f"surface boat sysid={master.target_system} component={master.target_component}",
        )

        expected_parameters = {
            "FRAME_CLASS": 2.0,
            "CRUISE_SPEED": 2.0,
            "CRUISE_THROTTLE": 50.0,
            "WP_SPEED": 2.0,
        }
        for name, expected in expected_parameters.items():
            actual = read_parameter(master, name)
            if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=0.05):
                fail("parameters", f"{name}={actual}, expected {expected}")
            log("parameters", f"{name}={actual:g}")

        origin = receive_position(master, POSITION_TIMEOUT_S)
        log("position", f"start={origin.lat:.7f},{origin.lon:.7f}")
        target = offset_north(origin, TARGET_DISTANCE_M)

        set_mode(master, "GUIDED")
        command_arm(master, True)
        armed_by_test = True
        travel_to_target(master, origin, target)

        set_mode(master, "HOLD")
        verify_hold(master)

        set_mode(master, "RTL")
        verify_return(master, origin)
        command_arm(master, False)
        armed_by_test = False
        log("result", "PASS: autonomous BlueBoat smoke test completed")
        return 0
    except SmokeFailure as error:
        print(f"FAIL {error}", file=sys.stderr, flush=True)
        return 1
    finally:
        if armed_by_test:
            try:
                set_mode(master, "HOLD")
                command_arm(master, False)
            except Exception as cleanup_error:  # best-effort simulation cleanup
                print(f"WARNING: cleanup failed: {cleanup_error}", file=sys.stderr)
        master.close()


if __name__ == "__main__":
    raise SystemExit(main())
