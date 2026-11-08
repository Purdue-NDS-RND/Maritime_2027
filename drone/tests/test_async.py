from copy import deepcopy
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace as NS
import sys

import pytest

from maritime_perception.async_test import AsyncRunner, run_replay
from maritime_perception.adapters.rosbag_audit import audit_bag
from maritime_perception.validation import Unavailable


def first_inputs(events):
    states = [e for e in events if e["kind"] == "vehicle_state"][:2]
    frame = deepcopy(next(e for e in events if e["kind"] == "frame"))
    return states, frame


def test_frame_before_pose_waits_then_projects_without_latest_fallback(settings, events):
    runner = AsyncRunner(settings, wait_s=.5, reorder_s=.01)
    states, frame = first_inputs(events)
    runner.submit(frame, 0)
    assert not runner.tick(20_000_000)
    runner.submit(states[0], 30_000_000)
    assert not runner.tick(50_000_000)
    runner.submit(states[1], 100_000_000)
    report, ledger = runner.tick(100_000_000)[0]
    assert len(ledger) == 3
    assert not [d for d in report["diagnostics"] if d.get("status") == "rejected"]
    assert runner.summary()["pending_frames"] == 0
    assert runner.summary()["maximum_queue_wait_s"] == pytest.approx(.1)


def test_missing_future_pose_times_out_with_no_fresh_locations(settings, events):
    runner = AsyncRunner(settings, wait_s=.1, reorder_s=0)
    states, frame = first_inputs(events)
    runner.submit(states[0], 0)
    runner.submit(frame, 1)
    assert not runner.tick(50_000_000)
    report, ledger = runner.tick(110_000_000)[0]
    assert not ledger and not report["tracks"]
    assert {"pose_not_bracketed", "async_pose_wait_timeout"} <= {d["reason"] for d in report["diagnostics"]}


def test_overflow_duplicate_and_late_frames_have_explicit_outcomes(settings, events):
    runner = AsyncRunner(settings, max_pending=1)
    states, frame = first_inputs(events)
    runner.submit(frame, 0)
    runner.submit(frame, 1)
    other = deepcopy(frame)
    other["data"]["id"] = "second"
    runner.submit(other, 2)
    for state in states:
        runner.submit(state, 3)
    assert len(runner.tick(100_000_000)) == 1
    runner.submit(frame, 200_000_000)
    counts = runner.summary()["counts"]
    assert counts["rejected:async_late_or_duplicate_frame"] == 2
    assert counts["rejected:async_frame_queue_full"] == 1


def test_frame_reordering_is_bounded_and_state_reordering_is_rejected(settings, events):
    runner = AsyncRunner(settings, reorder_s=.05)
    states, frame = first_inputs(events)
    later = deepcopy(frame)
    later["data"]["id"] = "later"
    later["data"]["stamp_ns"] += 1
    runner.submit(later, 0)
    runner.submit(frame, 10_000_000)
    runner.submit(states[0], 10_000_000)
    runner.submit(states[1], 20_000_000)
    reports = runner.tick(70_000_000)
    assert len(reports) == 2 and reports[0][0]["state_at"] < reports[1][0]["state_at"]
    runner.submit(states[0], 80_000_000)
    assert runner.summary()["counts"]["rejected:unordered_state"] == 1


@pytest.mark.parametrize("change", [dict(wait_s=-1), dict(reorder_s=1, wait_s=.5), dict(max_pending=0), dict(wait_s=30, reorder_s=0)])
def test_bad_async_limits_fail(settings, change):
    with pytest.raises(Unavailable):
        AsyncRunner(settings, **change)


def test_seeded_async_replay_is_deterministic_and_loss_is_visible(tmp_path, settings):
    session = tmp_path/"session"
    first = run_replay(session, tmp_path/"first", jitter_ms=8.)
    second = run_replay(session, tmp_path/"second", jitter_ms=8.)
    assert first == second and first["counts"]["observations"] == 12
    assert first["pending_frames"] == 0
    for name in ("reports.jsonl", "observations.jsonl", "arrivals.jsonl", "diagnostics.jsonl"):
        assert (tmp_path/"first"/name).read_bytes() == (tmp_path/"second"/name).read_bytes()
    missing = run_replay(session, tmp_path/"missing", drop_state_every=1)
    assert missing["counts"].get("observations", 0) == 0
    assert missing["counts"]["rejected:async_pose_wait_timeout"] == 4


def test_unknown_clock_and_bad_publication_time_are_not_replaced(settings, events):
    states, frame = first_inputs(events)
    runner = AsyncRunner(settings)
    bad = deepcopy(frame)
    bad["data"]["clock_id"] = "unmapped"
    runner.submit(bad, 0)
    assert runner.summary()["counts"]["rejected:unmapped_clock"] == 1
    for state in states:
        runner.submit(state, 0)
    frame["data"]["published_ns"] = "unknown"
    runner.submit(frame, 0)
    assert not runner.tick(100_000_000)
    assert runner.diagnostics[-1]["status"] == "rejected"


def test_rosbag_audit_counts_messages_and_separates_header_times(tmp_path, monkeypatch):
    (tmp_path/"metadata.yaml").write_text("rosbag2_bagfile_information:\n  storage_identifier: sqlite3\n")
    records = [("/camera/image_raw", b"a", 100), ("/camera/image_raw", b"b", 200), ("/imu", b"c", 300)]
    class Reader:
        def open(self, storage, conversion):
            assert storage.storage_id == "sqlite3"
        def get_all_topics_and_types(self):
            return [NS(name="/camera/image_raw", type="sensor_msgs/msg/Image"), NS(name="/imu", type="sensor_msgs/msg/Imu")]
        def has_next(self):
            return bool(records)
        def read_next(self):
            return records.pop(0)
    bag_module = NS(SequentialReader=Reader, StorageOptions=lambda **kw: NS(**kw), ConverterOptions=lambda *args: args)
    messages = {b"a": NS(header=NS(stamp=NS(sec=1, nanosec=0), frame_id="optical")),
                b"b": NS(header=NS(stamp=NS(sec=1, nanosec=0), frame_id="optical")),
                b"c": NS(header=NS(stamp=NS(sec=2, nanosec=0), frame_id="base_link"))}
    for name, value in {"rosbag2_py": bag_module, "rclpy": ModuleType("rclpy"),
        "rclpy.serialization": NS(deserialize_message=lambda raw, kind: messages[raw]),
        "rosidl_runtime_py": ModuleType("rosidl_runtime_py"), "rosidl_runtime_py.utilities": NS(get_message=lambda value: value)}.items():
        monkeypatch.setitem(sys.modules, name, value)
    report = audit_bag(tmp_path)
    camera = report["topics"]["/camera/image_raw"]
    assert camera["count"] == 2 and camera["header_duplicates"] == 1
    assert camera["first_receive_ns"] == 100 and camera["first_header_ns"] == 10**9
    assert not report["physical_accuracy_validated"]


@pytest.mark.parametrize("publish", [False, True])
def test_ros_async_endpoints_start_flow_and_close_without_ros(tmp_path, settings, events, monkeypatch, publish):
    from maritime_perception.adapters import async_ros
    now, lifecycle, outputs = NS(value=0), NS(shutdown=0, destroyed=0), []
    pending = list(events)
    class Node:
        def __init__(self, name):
            self.callback = None
        def create_publisher(self, kind, topic, qos):
            return NS(publish=outputs.append)
        def create_subscription(self, kind, topic, callback, qos):
            self.callback = callback
            return object()
        def create_timer(self, period, callback):
            return NS(cancel=lambda: None)
        def destroy_node(self):
            lifecycle.destroyed += 1
    rclpy = ModuleType("rclpy")
    rclpy.init = lambda **kw: None
    rclpy.ok = lambda: True
    rclpy.shutdown = lambda: setattr(lifecycle, "shutdown", lifecycle.shutdown+1)
    def spin_once(node):
        now.value += 10_000_000
        if not publish and pending:
            node.on_event(NS(data=json.dumps(pending.pop(0))))
        node.tick()
    rclpy.spin_once = spin_once
    monkeypatch.setattr(async_ros.time, "monotonic_ns", lambda: now.value)
    for name, module in {"rclpy": rclpy, "rclpy.node": NS(Node=Node),
        "rclpy.qos": NS(QoSProfile=lambda **kw: NS(**kw), ReliabilityPolicy=NS(BEST_EFFORT=1)),
        "std_msgs": ModuleType("std_msgs"), "std_msgs.msg": NS(String=lambda **kw: NS(**kw))}.items():
        monkeypatch.setitem(sys.modules, name, module)
    args = NS(ros_publish=publish, ros_live=not publish, duration_s=5., wait_s=.5, reorder_s=.05,
              max_pending=32, session=str(tmp_path/"session"), config=str(tmp_path/"session/config.json"), output=str(tmp_path/"live"))
    summary = async_ros.run(args, [], {})
    assert outputs and lifecycle.shutdown == lifecycle.destroyed == 1
    if publish:
        assert summary["published_input_events"] == len(events)
    else:
        assert summary["counts"]["observations"] == 12
        assert json.loads((tmp_path/"live/summary.json").read_text())["pending_frames"] == 0
