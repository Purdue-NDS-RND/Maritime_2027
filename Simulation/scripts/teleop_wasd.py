#!/usr/bin/env python3
"""Keyboard teleoperation for a running BlueBoat SITL simulation.

Hold W/S for throttle and A/D for turn rate; simultaneous keys combine, and no
keys means neutral. Shift increases speed and turn rate. Q exits. The operator
can select ACRO, arm, disarm, and stop directly over pymavlink; QGC is optional.
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
COMMAND_TIMEOUT_S = 10.0
NEUTRAL_WARMUP_S = 0.5
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
    19: "r",
    45: "x",
    35: "h",
    50: "m",
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


def send_gcs_heartbeat(master) -> None:
    master.mav.heartbeat_send(
        mavutil.mavlink.MAV_TYPE_GCS,
        mavutil.mavlink.MAV_AUTOPILOT_INVALID,
        0, 0, mavutil.mavlink.MAV_STATE_ACTIVE,
    )


def is_vehicle_message(master, message) -> bool:
    # pymavlink may leave target_component at broadcast (0) after discovery.
    component = master.target_component or mavutil.mavlink.MAV_COMP_ID_AUTOPILOT1
    return (
        message.get_srcSystem() == master.target_system
        and message.get_srcComponent() == component
    )


def request_mode(master, mode_id: int) -> None:
    master.mav.set_mode_send(
        master.target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        mode_id,
    )


def request_arm(master, armed: bool) -> None:
    # Ordinary arm/disarm: keep the FCU's pre-arm checks enabled.
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0, int(armed), 0, 0, 0, 0, 0, 0,
    )


class TeleopControl:
    """Keep movement neutral until mode and arming changes are observed."""

    def __init__(self, master, heartbeat, modes):
        self.master = master
        self.heartbeat = heartbeat
        self.modes = modes
        self.pending = None
        self.deadline = 0.0
        self.arm_after_mode = False
        self.arm_at = None
        self.enabled = False
        self.last_state = None

    def select_mode(self, name: str, arm: bool = False) -> None:
        self.enabled = False
        self.arm_at = None
        self.arm_after_mode = arm
        self.pending = ("mode", self.modes[name])
        self.deadline = time.monotonic() + COMMAND_TIMEOUT_S
        send_override(self.master, NEUTRAL_PWM, NEUTRAL_PWM)
        request_mode(self.master, self.modes[name])
        print(f"\nRequesting {name}" + (", then arm..." if arm else "..."), flush=True)

    def disarm(self) -> None:
        self.enabled = False
        self.arm_at = None
        self.arm_after_mode = False
        self.pending = ("arm", False)
        self.deadline = time.monotonic() + COMMAND_TIMEOUT_S
        send_override(self.master, NEUTRAL_PWM, NEUTRAL_PWM)
        # Hold also cancels autonomous movement if the operator changed mode.
        request_mode(self.master, self.modes["HOLD"])
        request_arm(self.master, False)
        print("\nRequesting HOLD and disarm...", flush=True)

    def observe(self, heartbeat, held: dict[str, int]) -> None:
        self.heartbeat = heartbeat
        armed = bool(heartbeat.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        state = (heartbeat.custom_mode, armed)
        if state != self.last_state:
            name = next((name for name, mode in self.modes.items()
                         if mode == heartbeat.custom_mode), str(heartbeat.custom_mode))
            print(f"\nVehicle: {name}, {'armed' if armed else 'disarmed'}", flush=True)
            self.last_state = state
        if self.pending is not None:
            kind, target = self.pending
            confirmed = heartbeat.custom_mode == target if kind == "mode" else armed == target
            if confirmed:
                self.pending = None
                held.clear()
                if kind == "mode" and target == self.modes["ACRO"]:
                    if self.arm_after_mode and not armed:
                        self.arm_at = time.monotonic() + NEUTRAL_WARMUP_S
                    else:
                        self.enabled = True
                elif kind == "arm" and target:
                    self.enabled = heartbeat.custom_mode == self.modes["ACRO"]
                self.arm_after_mode = False
                print("State confirmed. Release movement keys before driving.", flush=True)
        elif self.enabled and not is_acro_armed(heartbeat, self.modes["ACRO"]):
            self.enabled = False
            held.clear()
            print("Control paused; R arms/resumes, M selects ACRO, X disarms.", flush=True)

    def update(self) -> None:
        now = time.monotonic()
        if self.arm_at is not None and now >= self.arm_at:
            self.arm_at = None
            if self.heartbeat.custom_mode != self.modes["ACRO"]:
                print("Arm cancelled: vehicle left ACRO.", flush=True)
                return
            self.pending = ("arm", True)
            self.deadline = now + COMMAND_TIMEOUT_S
            request_arm(self.master, True)
            print("Requesting arm...", flush=True)
        if self.pending is not None and now > self.deadline:
            self.pending = None
            self.arm_after_mode = False
            self.enabled = False
            print("Command timed out; control stays neutral. Check FCU messages and retry.", flush=True)

    def acknowledge(self, message) -> None:
        if (self.pending is not None and self.pending[0] == "arm"
                and message.command == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM
                and message.result not in (mavutil.mavlink.MAV_RESULT_ACCEPTED,
                                           mavutil.mavlink.MAV_RESULT_IN_PROGRESS)):
            self.pending = None
            self.enabled = False
            result = mavutil.mavlink.enums["MAV_RESULT"].get(message.result)
            print(f"Arm/disarm rejected: {result.name if result else message.result}. "
                  "Check FCU messages and retry with R or X.", flush=True)

    def can_drive(self) -> bool:
        return (self.enabled and self.pending is None and self.arm_at is None
                and is_acro_armed(self.heartbeat, self.modes["ACRO"]))


def stop_vehicle(master, hold_mode_id: int) -> None:
    """Request Hold/disarm and report whether the FCU confirms the stop state."""
    send_override(master, NEUTRAL_PWM, NEUTRAL_PWM)
    request_mode(master, hold_mode_id)
    request_arm(master, False)
    deadline = time.monotonic() + 5.0
    next_heartbeat = 0.0
    while time.monotonic() < deadline:
        now = time.monotonic()
        if now >= next_heartbeat:
            send_gcs_heartbeat(master)
            next_heartbeat = now + 1.0
        send_override(master, NEUTRAL_PWM, NEUTRAL_PWM)
        heartbeat = master.recv_match(type="HEARTBEAT", blocking=True, timeout=0.1)
        if heartbeat is not None and is_vehicle_message(master, heartbeat):
            armed = bool(heartbeat.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            if not armed and heartbeat.custom_mode == hold_mode_id:
                print("\nStopped: HOLD and disarmed confirmed.", flush=True)
                return
    print("WARNING: HOLD/disarm not confirmed; check the vehicle.", file=sys.stderr)


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


def read_key_events(devices: dict[int, str], held: dict[str, int], order: list[int]) -> list[str]:
    """Update held keys and return one-shot actions in arrival order."""
    ready, _, _ = select.select(list(devices), [], [], 0)
    actions: list[str] = []
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
                if key in ("q", "r", "x", "h", "m"):
                    actions.append(key)
            elif value == 0:
                held.pop(key, None)
    return actions


def main() -> int:
    args = parse_args()
    master = mavutil.mavlink_connection(
        args.connection, source_system=255, autoreconnect=True
    )
    devices: dict[int, str] = {}
    terminal_fd = sys.stdin.fileno() if sys.stdin.isatty() else None
    old_terminal = termios.tcgetattr(terminal_fd) if terminal_fd is not None else None
    have_override = False
    modes = {}
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
        master.target_component = heartbeat.get_srcComponent()

        modes = master.mode_mapping() or {}
        if not {"ACRO", "HOLD"}.issubset(modes):
            raise RuntimeError("The vehicle must advertise ACRO and HOLD modes.")

        devices = open_keyboards()
        print(
            "R: select ACRO and arm; X: disarm; H: HOLD/stop; M: resume ACRO.\n"
            "Hold W/S for forward/reverse, A/D to steer; Shift increases speed.\n"
            "No movement keys means neutral. Q or Ctrl+C stops in HOLD and disarms.\n"
            "QGroundControl is optional. Arming rejections appear below."
        )
        control = TeleopControl(master, heartbeat, modes)
        have_override = True
        control.select_mode("ACRO")
        held: dict[str, int] = {}
        key_order = [0]
        interval = 1.0 / SEND_RATE_HZ
        next_send = time.monotonic()
        last_heartbeat = time.monotonic()
        next_gcs_heartbeat = 0.0

        while True:
            actions = read_key_events(devices, held, key_order)
            if "q" in actions:
                break
            for action in actions:
                held.clear()
                if action == "r":
                    control.select_mode("ACRO", arm=True)
                elif action == "x":
                    control.disarm()
                elif action == "h":
                    control.select_mode("HOLD")
                elif action == "m":
                    control.select_mode("ACRO")

            # Ignore GCS/MAVROS heartbeats: only the selected FCU proves readiness.
            while True:
                message = master.recv_match(
                    type=["HEARTBEAT", "COMMAND_ACK", "STATUSTEXT"], blocking=False
                )
                if message is None:
                    break
                if not is_vehicle_message(master, message):
                    continue
                if message.get_type() == "HEARTBEAT":
                    last_heartbeat = time.monotonic()
                    control.observe(message, held)
                elif message.get_type() == "COMMAND_ACK":
                    control.acknowledge(message)
                else:
                    print(f"\nFCU: {message.text}", flush=True)

            now = time.monotonic()
            if now >= next_gcs_heartbeat:
                send_gcs_heartbeat(master)
                next_gcs_heartbeat = now + 1.0
            control.update()
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
                if not control.can_drive():
                    steering_pwm = throttle_pwm = NEUTRAL_PWM
                send_override(master, steering_pwm, throttle_pwm)
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
                try:
                    stop_vehicle(master, modes["HOLD"])
                finally:
                    send_neutral_and_release(master)
            except Exception as error:  # best-effort cleanup if link is lost
                print(f"WARNING: could not release RC override: {error}", file=sys.stderr)
        master.close()


if __name__ == "__main__":
    raise SystemExit(main())
