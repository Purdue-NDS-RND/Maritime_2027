#!/usr/bin/env python3
"""Keyboard teleoperation for a running BlueBoat SITL simulation.

Hold W/S for throttle and A/D for turn rate; simultaneous keys combine, and no
keys means neutral. Shift increases speed and turn rate. Q exits. The operator
must select ACRO and arm the vehicle in QGroundControl.
"""

from __future__ import annotations

import argparse
import glob
import os
import select
import struct
import sys
import termios
import time

from pymavlink import mavutil


CONNECTION = "udp:127.0.0.1:14551"
HEARTBEAT_TIMEOUT_S = 30.0
HEARTBEAT_LOSS_TIMEOUT_S = 3.0
SEND_RATE_HZ = 30.0
NEUTRAL_PWM = 1500
FORWARD_PWM = 1580
REVERSE_PWM = 1420
LEFT_PWM = 1400
RIGHT_PWM = 1600
FAST_FORWARD_PWM = 1700
FAST_REVERSE_PWM = 1300
FAST_LEFT_PWM = 1300
FAST_RIGHT_PWM = 1700
IGNORED_CHANNEL = 0xFFFF
KEY_EVENT = struct.Struct("llHHi")
EV_KEY = 1
KEY_CODES = {
    17: "w",
    30: "a",
    31: "s",
    32: "d",
    42: "left_shift",
    54: "right_shift",
    16: "q",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--connection",
        default=CONNECTION,
        help=f"MAVLink UDP endpoint (default: {CONNECTION})",
    )
    return parser.parse_args()


def is_acro_armed(heartbeat, acro_mode_id: int) -> bool:
    armed = bool(heartbeat.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
    return armed and heartbeat.custom_mode == acro_mode_id


def send_override(master, steering_pwm: int, throttle_pwm: int) -> None:
    channels = [IGNORED_CHANNEL] * 18
    channels[0] = steering_pwm
    channels[2] = throttle_pwm
    master.mav.rc_channels_override_send(
        master.target_system, master.target_component, *channels
    )


def send_neutral_and_release(master) -> None:
    """Neutralize the controlled axes, then release their overrides."""
    for _ in range(5):
        send_override(master, NEUTRAL_PWM, NEUTRAL_PWM)
        time.sleep(0.05)

    channels = [IGNORED_CHANNEL] * 18
    # MAVLink value 0 releases an override on channels 1-8.
    channels[0] = 0
    channels[2] = 0
    for _ in range(5):
        master.mav.rc_channels_override_send(
            master.target_system, master.target_component, *channels
        )
        time.sleep(0.05)


def open_keyboards() -> dict[int, str]:
    """Open host Linux input devices passed through by the Makefile target."""
    devices: dict[int, str] = {}
    for path in glob.glob("/dev/input/event*"):
        try:
            devices[os.open(path, os.O_RDONLY | os.O_NONBLOCK)] = path
        except OSError:
            continue
    if not devices:
        raise RuntimeError(
            "No readable keyboard input devices found. Run 'make teleop' from "
            "the host terminal so it can pass /dev/input devices into Docker."
        )
    return devices


def read_key_events(devices: dict[int, str], held: dict[str, int], order: list[int]) -> bool:
    """Update held keys from Linux key down/up events; return whether Q is down."""
    ready, _, _ = select.select(list(devices), [], [], 0)
    quit_requested = False
    for fd in ready:
        try:
            data = os.read(fd, KEY_EVENT.size * 32)
        except BlockingIOError:
            continue
        usable = len(data) - (len(data) % KEY_EVENT.size)
        for offset in range(0, usable, KEY_EVENT.size):
            _, _, event_type, code, value = KEY_EVENT.unpack_from(data, offset)
            if event_type != EV_KEY or code not in KEY_CODES or value == 2:
                continue
            key = KEY_CODES[code]
            if value == 1:
                order[0] += 1
                held[key] = order[0]
                quit_requested = quit_requested or key == "q"
            elif value == 0:
                held.pop(key, None)
    return quit_requested


def main() -> int:
    args = parse_args()
    master = mavutil.mavlink_connection(
        args.connection, source_system=255, autoreconnect=True
    )
    devices: dict[int, str] = {}
    terminal_fd = sys.stdin.fileno() if sys.stdin.isatty() else None
    old_terminal = termios.tcgetattr(terminal_fd) if terminal_fd is not None else None
    have_override = False
    try:
        if terminal_fd is not None and old_terminal is not None:
            quiet_terminal = termios.tcgetattr(terminal_fd)
            quiet_terminal[3] &= ~(termios.ECHO | termios.ICANON)
            quiet_terminal[6][termios.VMIN] = 0
            quiet_terminal[6][termios.VTIME] = 0
            termios.tcsetattr(terminal_fd, termios.TCSANOW, quiet_terminal)

        print(f"Waiting for the BlueBoat heartbeat on {args.connection}...")
        heartbeat = master.wait_heartbeat(timeout=HEARTBEAT_TIMEOUT_S)
        if heartbeat is None:
            raise RuntimeError(
                f"No heartbeat received within {HEARTBEAT_TIMEOUT_S:.0f}s. "
                "Start the simulator and check the student MAVLink output."
            )
        if heartbeat.autopilot != mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA:
            raise RuntimeError(f"Unexpected autopilot type {heartbeat.autopilot}.")
        if heartbeat.type != mavutil.mavlink.MAV_TYPE_SURFACE_BOAT:
            raise RuntimeError(f"Expected a surface boat, received MAV type {heartbeat.type}.")

        acro_mode_id = (master.mode_mapping() or {}).get("ACRO")
        if acro_mode_id is None:
            raise RuntimeError("The vehicle does not advertise an ACRO mode.")
        if not is_acro_armed(heartbeat, acro_mode_id):
            mode_name = next(
                (
                    name
                    for name, mode_id in (master.mode_mapping() or {}).items()
                    if mode_id == heartbeat.custom_mode
                ),
                f"unknown ({heartbeat.custom_mode})",
            )
            armed = bool(
                heartbeat.base_mode
                & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
            )
            raise RuntimeError(
                f"Teleop requires ACRO and armed; heartbeat reports "
                f"mode={mode_name}, armed={'yes' if armed else 'no'}. "
                "Set both in QGroundControl, then run make teleop again."
            )

        devices = open_keyboards()
        print(
            "Hold W/S to move forward/reverse and A/D to steer; combine keys "
            "for arcing turns. Hold Shift for higher speed and turn rate. No keys means "
            "neutral. Q quits; Ctrl+C also neutralizes."
        )
        held: dict[str, int] = {}
        key_order = [0]
        interval = 1.0 / SEND_RATE_HZ
        next_send = time.monotonic()
        last_heartbeat = time.monotonic()

        while True:
            if read_key_events(devices, held, key_order):
                break

            while True:
                heartbeat = master.recv_match(type="HEARTBEAT", blocking=False)
                if heartbeat is None:
                    break
                last_heartbeat = time.monotonic()
                if not is_acro_armed(heartbeat, acro_mode_id):
                    print("\nVehicle left ACRO/armed state; stopping control.")
                    return 1

            now = time.monotonic()
            if now - last_heartbeat > HEARTBEAT_LOSS_TIMEOUT_S:
                print("\nHeartbeat lost; stopping control.")
                return 1
            if now >= next_send:
                fast = "left_shift" in held or "right_shift" in held
                left_pressed = held.get("a", -1)
                right_pressed = held.get("d", -1)
                if left_pressed > right_pressed:
                    steering_pwm = FAST_LEFT_PWM if fast else LEFT_PWM
                elif right_pressed >= 0:
                    steering_pwm = FAST_RIGHT_PWM if fast else RIGHT_PWM
                else:
                    steering_pwm = NEUTRAL_PWM
                forward_pressed = held.get("w", -1)
                reverse_pressed = held.get("s", -1)
                if forward_pressed > reverse_pressed:
                    throttle_pwm = (
                        FAST_FORWARD_PWM if fast else FORWARD_PWM
                    )
                elif reverse_pressed >= 0:
                    throttle_pwm = (
                        FAST_REVERSE_PWM if fast else REVERSE_PWM
                    )
                else:
                    throttle_pwm = NEUTRAL_PWM
                send_override(master, steering_pwm, throttle_pwm)
                have_override = True
                next_send = now + interval
            time.sleep(0.005)

        return 0
    except KeyboardInterrupt:
        print("\nStopping teleoperation.")
        return 130
    except (OSError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    finally:
        if terminal_fd is not None and old_terminal is not None:
            termios.tcflush(terminal_fd, termios.TCIFLUSH)
            termios.tcsetattr(terminal_fd, termios.TCSADRAIN, old_terminal)
        for fd in devices:
            os.close(fd)
        if have_override:
            try:
                send_neutral_and_release(master)
            except Exception as error:  # best-effort cleanup if link is lost
                print(f"WARNING: could not release RC override: {error}", file=sys.stderr)
        master.close()


if __name__ == "__main__":
    raise SystemExit(main())
