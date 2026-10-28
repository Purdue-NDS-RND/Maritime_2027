"""Protocol failure and lifecycle tests using actual pymavlink message definitions."""

from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
import unittest

from pymavlink import mavutil

from boat_app.executor import Executor, MissionError
from boat_app.mission import Mission, Point


class Message(SimpleNamespace):
    def get_type(self):
        return self.kind

    def get_srcSystem(self):
        return getattr(self, "source_system", 1)

    def get_srcComponent(self):
        return 1


class Link:
    source_system, source_component = 245, 191

    def __init__(self):
        self.messages, self.stored, self.commands = [], [], []
        self.mav = self
        self.count = 0
        self.reject = False
        self.corrupt = False
        self.repeat_request = False
        self.time = 100.0
        self.armed, self.mode, self.done_behavior = False, 4, 1
        self.reject_speed = False

    def mode_mapping(self):
        return {"MANUAL": 0, "AUTO": 10, "HOLD": 4}

    def put(self, kind, **values):
        self.messages.append(Message(kind=kind, **values))

    def recv_match(self, **kwargs):
        self.time += 0.01
        return self.messages.pop(0) if self.messages else None

    def heartbeat_send(self, *args):
        pass

    def command_long_send(self, system, component, command, confirmation, *params):
        self.commands.append((command, params))
        self.put("COMMAND_ACK", command=command,
                 result=4 if self.reject_speed and command == mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED else 0)
        if command == mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE:
            self.put("HOME_POSITION", latitude=515661510, longitude=-40343450, altitude=0)
        elif command == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM:
            self.armed = bool(params[0])
            self.put("HEARTBEAT", custom_mode=self.mode, base_mode=128 if self.armed else 0,
                     autopilot=3, type=11)

    def param_request_read_send(self, system, component, name, index):
        self.put("PARAM_VALUE", param_id=name.decode(), param_value=self.done_behavior)

    def mission_set_current_send(self, system, component, seq):
        self.put("MISSION_CURRENT", seq=1)

    def mission_count_send(self, system, component, count):
        self.count, self.stored = count, [None] * count
        self.put("MISSION_REQUEST_INT", seq=0)

    def mission_item_int_send(self, system, component, seq, frame, command,
                              current, autocontinue, p1, p2, p3, p4, x, y, z):
        self.stored[seq] = dict(seq=seq, frame=frame, command=command,
                                param1=p1, param2=p2, param3=p3, param4=p4, x=x, y=y, z=z)
        if self.repeat_request:
            self.repeat_request = False
            self.put("MISSION_REQUEST_INT", seq=seq)
        elif seq + 1 < self.count:
            self.put("MISSION_REQUEST_INT", seq=seq + 1)
        else:
            self.put("MISSION_ACK", type=1 if self.reject else 0)

    def mission_request_list_send(self, *args):
        self.put("MISSION_COUNT", count=self.count)

    def mission_request_int_send(self, system, component, seq):
        item = dict(self.stored[seq])
        if item["frame"] == 6:
            item["frame"] = 3
        if self.corrupt and seq == 1:
            item["x"] += 100
        self.put("MISSION_ITEM_INT", **item)

    def mission_ack_send(self, *args):
        pass

    def set_mode_send(self, system, flags, mode):
        self.mode = mode
        self.commands.append(("mode", mode))
        self.put("HEARTBEAT", custom_mode=mode, base_mode=128 if self.armed else 0,
                 autopilot=3, type=11)


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.link = Link()
        self.events = []
        self.executor = Executor(self.link, self.events.append, lambda: self.link.time)
        self.link.put("HEARTBEAT", custom_mode=4, base_mode=0, autopilot=3, type=11)
        self.executor.receive()
        self.executor.position = Point(51.566151, -4.034345)
        self.executor.speed, self.executor.fix = 0, 3
        self.executor.last_position = self.executor.last_gps = self.link.time
        self.mission = Mission.load(Path(__file__).resolve().parents[1] / "examples/mission.json")

    def test_upload_acceptance_and_duplicate_request(self):
        self.link.repeat_request = True
        self.executor.upload(self.mission)
        self.assertEqual(self.executor.state, "uploaded")
        self.assertEqual(len(self.link.stored), 2)
        self.assertEqual(self.link.stored[1]["x"], 515662590)
        self.assertFalse(any(command == "mode" for command, _ in self.link.commands))

    def test_rejected_or_altered_upload_cannot_start(self):
        for setting in ("reject", "corrupt"):
            with self.subTest(setting=setting):
                self.setUp()
                setattr(self.link, setting, True)
                with self.assertRaises(MissionError):
                    self.executor.upload(self.mission)
                self.assertEqual(self.executor.state, "failed")
                with self.assertRaises(MissionError):
                    self.executor.start()

    def test_armed_vehicle_cannot_upload(self):
        self.executor.armed = True
        with self.assertRaises(MissionError):
            self.executor.upload(self.mission)
        self.assertFalse(self.link.stored)

    def running(self):
        self.executor.mission = self.mission
        self.executor.items = [None] * 3
        self.executor.state = "executing"
        self.executor.mode, self.executor.armed = 10, True
        self.executor.started = self.link.time
        self.link.armed = True

    def test_explicit_start_confirms_arm_and_auto(self):
        self.executor.upload(self.mission)
        self.executor.start()
        self.assertEqual(self.executor.state, "executing")
        self.assertTrue(self.executor.armed)
        self.assertEqual(self.executor.mode, 10)
        commands = [command for command, _ in self.link.commands]
        self.assertLess(commands.index(mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED),
                        commands.index(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM))
        with self.assertRaises(MissionError):
            self.executor.start()

    def test_rejects_manual_firmware_end_behavior_before_arming(self):
        self.executor.upload(self.mission)
        self.link.done_behavior = 3
        with self.assertRaises(MissionError):
            self.executor.start()
        self.assertFalse(self.executor.armed)
        self.assertEqual(self.executor.state, "failed")

    def test_cancellation_during_speed_ack_prevents_arming(self):
        self.executor.upload(self.mission)
        def cancelled():
            if any(command == mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED for command, _ in self.link.commands):
                raise MissionError("operation cancelled by STOP")
        self.executor.cancel_check = cancelled
        with self.assertRaisesRegex(MissionError, "cancelled"):
            self.executor.start()
        self.assertFalse(any(command == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM
                             for command, _ in self.link.commands))
        self.assertEqual(self.executor.state, "failed")

    def test_speed_rejection_prevents_arming(self):
        self.executor.upload(self.mission)
        self.link.reject_speed = True
        with self.assertRaises(MissionError):
            self.executor.start()
        self.assertFalse(self.executor.armed)
        self.assertFalse(any(command == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM
                             for command, _ in self.link.commands))
        self.assertEqual(self.executor.mode, 4)

    def test_multiple_waypoints_preserve_order_and_final_sequence(self):
        points = (Point(51.56620, -4.03434), Point(51.56625, -4.03436),
                  Point(51.56630, -4.03434))
        self.executor.upload(replace(self.mission, waypoints=points))
        self.assertEqual(self.executor.final_nav_seq, 3)
        self.assertEqual([item['x'] for item in self.link.stored[1:]],
                         [round(point.latitude * 1e7) for point in points])

    def test_manual_takeover_does_not_send_hold_or_resume(self):
        self.running()
        self.link.put("HEARTBEAT", custom_mode=0, base_mode=128, autopilot=3, type=11)
        self.executor.tick()
        self.assertEqual(self.executor.state, "interrupted")
        self.assertFalse(self.link.commands)
        with self.assertRaises(MissionError):
            self.executor.start()

    def test_finish_requires_reached_position_speed_and_settle(self):
        self.running()
        self.executor.position = self.mission.waypoints[-1]
        self.executor.tick()
        self.assertEqual(self.executor.state, "executing")
        self.link.put("MISSION_ITEM_REACHED", seq=1)
        self.executor.tick()
        self.assertEqual(self.executor.state, "stopping")
        self.executor.speed = 1
        self.executor.tick()
        self.assertIsNone(self.executor.settled_since)
        self.executor.speed = 0
        self.executor.tick()
        self.assertIsNotNone(self.executor.settled_since)
        for _ in range(6):
            self.link.time += 1
            self.executor.last_position = self.executor.last_gps = self.executor.last_heartbeat = self.link.time
            self.executor.tick()
        self.assertEqual(self.executor.state, "complete")

    def test_stale_telemetry_fails_without_claiming_stop(self):
        self.running()
        self.link.time += 6
        self.executor.tick()
        self.assertEqual(self.executor.state, "failed")
        self.assertFalse(self.link.commands)

    def test_other_vehicle_cannot_change_progress(self):
        self.link.put("MISSION_ITEM_REACHED", seq=2, source_system=2)
        self.executor.receive()
        self.assertIsNone(self.executor.reached)

    def test_ignored_packets_do_not_stall_receive_queue(self):
        self.link.put("MISSION_ITEM_REACHED", seq=99, source_system=2)
        self.link.put("MISSION_CURRENT", seq=2)
        self.executor.drain()
        self.assertEqual(self.executor.current, 2)
        self.assertIsNone(self.executor.reached)


if __name__ == "__main__":
    unittest.main()
