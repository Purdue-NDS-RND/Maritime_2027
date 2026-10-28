"""One owner of a MAVLink connection; no simulator or GCS dependencies."""

import math
import time

from pymavlink import mavutil

from .mission import Point, distance_m


class MissionError(RuntimeError):
    pass


class Executor:
    def __init__(self, link, emit, clock=time.monotonic):
        self.link = link
        self.emit = emit
        self.clock = clock
        self.state = "disconnected"
        self.system = None
        self.component = None
        self.mode = None
        self.armed = False
        self.position = None
        self.speed = None
        self.fix = 0
        self.last_heartbeat = -math.inf
        self.last_position = -math.inf
        self.last_gps = -math.inf
        self.last_send = -math.inf
        self.home = None
        self.current = None
        self.reached = None
        self.mission = None
        self.items = []
        self.started = None
        self.settled_since = None
        self.final_reached = False
        self.detail = "waiting for ArduPilot surface-boat heartbeat"

    def transition(self, state, detail):
        self.state, self.detail = state, detail
        self.emit({"event": "state", **self.status()})

    def status(self):
        return {
            "state": self.state, "detail": self.detail,
            "mission_id": self.mission.mission_id if self.mission else None,
            "mission_sha256": self.mission.sha256 if self.mission else None,
            "system_id": self.system, "component_id": self.component,
            "mode": self.mode, "armed": self.armed,
            "position": vars(self.position) if self.position else None,
            "speed_m_s": self.speed, "gps_fix": self.fix,
            "heartbeat_age_s": self.age(self.last_heartbeat),
            "position_age_s": self.age(self.last_position),
            "current_item": self.current, "last_reached_item": self.reached,
            "route_waypoint_count": len(self.mission.waypoints) if self.mission else 0,
        }

    def age(self, timestamp):
        age = self.clock() - timestamp
        return age if math.isfinite(age) else None

    def receive(self, timeout=0):
        now = self.clock()
        if now - self.last_send >= 1:
            self.link.mav.heartbeat_send(
                mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
                mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0,
                mavutil.mavlink.MAV_STATE_ACTIVE,
            )
            self.last_send = now
        msg = self.link.recv_match(blocking=timeout > 0, timeout=timeout if timeout > 0 else None)
        if msg is None:
            return None
        kind = msg.get_type()
        if self.system is None:
            if not (kind == "HEARTBEAT"
                    and msg.autopilot == mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA
                    and msg.type == mavutil.mavlink.MAV_TYPE_SURFACE_BOAT):
                return False
            self.system, self.component = msg.get_srcSystem(), msg.get_srcComponent()
            self.link.target_system, self.link.target_component = self.system, self.component
        if (msg.get_srcSystem(), msg.get_srcComponent()) != (self.system, self.component):
            return False
        if kind == "HEARTBEAT":
            self.last_heartbeat = now
            self.mode = msg.custom_mode
            self.armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            if self.state == "disconnected":
                self.transition("ready", "connected; no mission authorized")
        elif kind == "GLOBAL_POSITION_INT":
            # Reject unavailable velocity and invalid GPS coordinates.
            if abs(msg.lat) <= 900000000 and abs(msg.lon) <= 1800000000 and abs(msg.vx) < 32767 and abs(msg.vy) < 32767:
                self.position = Point(msg.lat / 1e7, msg.lon / 1e7)
                self.speed = math.hypot(msg.vx, msg.vy) / 100
                self.last_position = now
        elif kind == "GPS_RAW_INT":
            self.fix, self.last_gps = msg.fix_type, now
        elif kind == "HOME_POSITION":
            self.home = (msg.latitude, msg.longitude, msg.altitude / 1000)
        elif kind == "MISSION_CURRENT":
            self.current = msg.seq
        elif kind == "MISSION_ITEM_REACHED":
            self.reached = msg.seq
            if self.mission and msg.seq == self.final_nav_seq and self.state in ("starting", "executing"):
                self.final_reached = True
            self.emit({"event": "item_reached", "seq": msg.seq})
        elif kind == "STATUSTEXT":
            self.emit({"event": "autopilot_text", "severity": msg.severity, "text": msg.text})
        return msg

    def wait(self, predicate, timeout=10):
        deadline = self.clock() + timeout
        while self.clock() < deadline:
            msg = self.receive(0.1)
            if msg and predicate(msg):
                return msg
        raise MissionError("timed out waiting for ArduPilot response")

    def drain(self):
        for _ in range(500):
            if self.receive() is None:
                break

    def fresh(self):
        now = self.clock()
        if now - self.last_heartbeat > 3:
            raise MissionError("ArduPilot heartbeat is stale")
        if now - self.last_position > 3 or self.position is None:
            raise MissionError("boat position/velocity is stale")
        if now - self.last_gps > 5 or self.fix < 3:
            raise MissionError("fresh 3D GPS fix required")

    def command(self, command, *params):
        self.drain()
        values = list(params) + [0] * (7 - len(params))
        self.link.mav.command_long_send(self.system, self.component, command, 0, *values)
        ack = self.wait(lambda m: m.get_type() == "COMMAND_ACK" and m.command == command)
        if ack.result != mavutil.mavlink.MAV_RESULT_ACCEPTED:
            raise MissionError(f"command {command} rejected: result={ack.result}")

    def set_mode(self, name):
        modes = self.link.mode_mapping() or {}
        if name not in modes:
            raise MissionError(f"ArduPilot mode {name} is unavailable")
        target = modes[name]
        self.link.mav.set_mode_send(self.system, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, target)
        self.wait(lambda m: m.get_type() == "HEARTBEAT" and m.custom_mode == target)

    def parameter(self, name):
        self.link.mav.param_request_read_send(self.system, self.component, name.encode(), -1)
        def matches(msg):
            if msg.get_type() != "PARAM_VALUE":
                return False
            received = msg.param_id
            if isinstance(received, bytes):
                received = received.decode()
            return received.rstrip("\x00") == name
        value = self.wait(matches).param_value
        self.emit({"event": "parameter_read", "name": name, "value": value})
        return value

    def upload(self, mission):
        self.drain()
        self.fresh()
        if self.armed or self.mode == (self.link.mode_mapping() or {}).get("AUTO"):
            raise MissionError("upload requires disarmed vehicle outside AUTO")
        # A failed replacement must invalidate the previous local authorization.
        self.mission, self.items = mission, []
        self.transition("uploading", "awaiting mission requests and final acceptance")
        try:
            self.home = None
            self.command(mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE, mavutil.mavlink.MAVLINK_MSG_ID_HOME_POSITION)
            if self.home is None:
                self.wait(lambda m: m.get_type() == "HOME_POSITION")
            home_lat, home_lon, home_alt = self.home
            # ArduPilot reserves item zero for home. Speed is applied and
            # acknowledged during start, in AUTO but before arming.
            self.items = [
                (mavutil.mavlink.MAV_FRAME_GLOBAL_INT, mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                 0, 0, 0, 0, home_lat, home_lon, home_alt),
            ]
            for point in mission.waypoints:
                self.items.append((mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                                   mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, 0, 0, 0, 0,
                                   round(point.latitude * 1e7), round(point.longitude * 1e7), 0))
            self.drain()
            self.link.mav.mission_count_send(self.system, self.component, len(self.items))
            sent = set()
            deadline = self.clock() + 45
            while self.clock() < deadline:
                msg = self.wait(lambda m: m.get_type() in ("MISSION_REQUEST_INT", "MISSION_REQUEST", "MISSION_ACK"), timeout=5)
                if not self.addressed(msg):
                    continue
                if msg.get_type() == "MISSION_ACK":
                    if msg.type != mavutil.mavlink.MAV_MISSION_ACCEPTED or len(sent) != len(self.items):
                        raise MissionError(f"mission not accepted in full: result={msg.type}, sent={len(sent)}")
                    break
                seq = msg.seq
                if not 0 <= seq < len(self.items):
                    raise MissionError(f"invalid requested mission sequence {seq}")
                frame, cmd, p1, p2, p3, p4, x, y, z = self.items[seq]
                self.link.mav.mission_item_int_send(
                    self.system, self.component, seq, frame, cmd, 0, 1,
                    p1, p2, p3, p4, x, y, z,
                )
                sent.add(seq)
            else:
                raise MissionError("mission upload deadline exceeded")
            self.verify_download()
            self.transition("uploaded", "ArduPilot accepted mission; stored items verified; start required")
        except Exception as error:
            self.transition("failed", str(error))
            raise

    def addressed(self, msg):
        return (getattr(msg, "target_system", self.link.source_system) == self.link.source_system
                and getattr(msg, "target_component", self.link.source_component) in (0, self.link.source_component)
                and getattr(msg, "mission_type", 0) == 0)

    def verify_download(self):
        deadline = self.clock() + 45
        self.drain()
        self.link.mav.mission_request_list_send(self.system, self.component)
        count = self.wait(lambda m: m.get_type() == "MISSION_COUNT" and self.addressed(m))
        if count.count != len(self.items):
            raise MissionError("stored mission count differs from supplied mission")
        downloaded = []
        try:
            for seq, expected in enumerate(self.items):
                remaining = deadline - self.clock()
                if remaining <= 0:
                    raise MissionError("mission readback deadline exceeded")
                self.link.mav.mission_request_int_send(self.system, self.component, seq)
                msg = self.wait(lambda m: m.get_type() == "MISSION_ITEM_INT" and m.seq == seq and self.addressed(m),
                                timeout=min(5, remaining))
                actual = (msg.frame, msg.command, msg.param1, msg.param2, msg.param3,
                          msg.param4, msg.x, msg.y, msg.z)
                # ArduPilot may normalize *_INT global frames to their equivalents.
                frame_pairs = ({0, 5}, {3, 6})
                if not any(actual[0] in pair and expected[0] in pair for pair in frame_pairs):
                    raise MissionError(f"stored mission frame differs at item {seq}")
                for i, (a, b) in enumerate(zip(actual[1:], expected[1:]), start=1):
                    tolerance = 1 if i in (6, 7) else 0.001
                    if not math.isfinite(a) or abs(a - b) > tolerance:
                        raise MissionError(f"stored mission differs at item {seq}, field {i}")
                downloaded.append(actual)
        except Exception:
            self.link.mav.mission_ack_send(self.system, self.component, mavutil.mavlink.MAV_MISSION_ERROR)
            raise
        self.link.mav.mission_ack_send(self.system, self.component, mavutil.mavlink.MAV_MISSION_ACCEPTED)
        self.emit({"event": "mission_readback_verified", "items": downloaded})

    def start(self):
        if self.state != "uploaded":
            raise MissionError("start requires a freshly uploaded and verified mission")
        self.drain()
        self.fresh()
        if self.armed:
            raise MissionError("start requires disarmed vehicle")
        if distance_m(self.position, self.mission.waypoints[0]) > self.mission.max_start_distance_m:
            raise MissionError("first waypoint exceeds max_start_distance_m")
        self.transition("starting", "checking stored mission and end behavior before arming")
        try:
            self.verify_download()
            done_behavior = self.parameter("MIS_DONE_BEHAVE")
            if done_behavior not in (0, 1):
                raise MissionError(f"MIS_DONE_BEHAVE={done_behavior} must be stop (0) or loiter (1); no parameter was changed")
            self.set_mode("HOLD")
            self.link.mav.mission_set_current_send(self.system, self.component, 1)
            self.wait(lambda m: m.get_type() == "MISSION_CURRENT" and m.seq == 1)
            self.fresh()
            self.current, self.reached = None, None
            self.final_reached = False
            self.set_mode("AUTO")
            self.command(mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED, 1, self.mission.speed_m_s, -1)
            self.emit({"event": "mission_speed_accepted", "speed_m_s": self.mission.speed_m_s})
            self.fresh()
            if self.mode != (self.link.mode_mapping() or {}).get("AUTO") or self.armed:
                raise MissionError("mode/arming changed during start; arming not requested")
            self.command(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)
            if not self.armed:
                self.wait(lambda m: m.get_type() == "HEARTBEAT" and self.armed)
            if self.mode != (self.link.mode_mapping() or {}).get("AUTO"):
                raise MissionError("mode changed during arming; autonomy not resumed")
            self.started = self.clock()
            self.settled_since = None
            self.transition("executing", "AUTO confirmed; ArduPilot follows uploaded waypoints")
        except Exception as error:
            self.fail(str(error))
            raise

    def hold_if_owned(self):
        # Never override an observed manual takeover, or act on a stale heartbeat.
        if (self.clock() - self.last_heartbeat <= 3
                and self.mode == (self.link.mode_mapping() or {}).get("AUTO")):
            self.set_mode("HOLD")

    @property
    def final_nav_seq(self):
        return len(self.mission.waypoints)

    def fail(self, detail):
        try:
            self.hold_if_owned()
        except Exception as error:
            detail += f"; HOLD unconfirmed: {error}"
        self.transition("failed", detail)

    def stop(self):
        if self.system is None or self.clock() - self.last_heartbeat > 3:
            raise MissionError("cannot confirm stop without a fresh ArduPilot heartbeat")
        self.set_mode("HOLD")
        self.transition("stopped", "operator requested HOLD, mode confirmed; disarm is separate")

    def disarm(self):
        self.drain()
        self.fresh()
        if self.mode != (self.link.mode_mapping() or {}).get("HOLD") or self.speed > 0.2:
            raise MissionError("disarm requires HOLD and reported speed <= 0.2 m/s")
        self.command(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0)
        if self.armed:
            self.wait(lambda m: m.get_type() == "HEARTBEAT" and not self.armed)
        self.transition("stopped", "disarm confirmed")

    def tick(self):
        self.drain()
        if self.state not in ("executing", "stopping"):
            return
        expected = "AUTO" if self.state == "executing" else "HOLD"
        if self.mode != (self.link.mode_mapping() or {}).get(expected) or not self.armed:
            self.transition("interrupted", "mode changed or vehicle disarmed; explicit new upload/start required")
            return
        try:
            self.fresh()
            if self.clock() - self.started > self.mission.timeout_s:
                raise MissionError("mission execution/finish timeout")
            if self.state == "executing" and self.final_reached:
                self.set_mode("HOLD")
                self.transition("stopping", "final waypoint reported reached; verifying finish position and speed")
            if self.state == "stopping":
                inside = distance_m(self.position, self.mission.waypoints[-1]) <= self.mission.finish_radius_m
                if inside and self.speed <= self.mission.finish_speed_m_s:
                    if self.settled_since is None:
                        self.settled_since = self.clock()
                    if self.clock() - self.settled_since >= self.mission.finish_settle_s:
                        self.transition("complete", "finish position/speed held for selected interval; HOLD confirmed")
                else:
                    self.settled_since = None
        except Exception as error:
            self.fail(str(error))
