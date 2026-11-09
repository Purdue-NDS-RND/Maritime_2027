from copy import deepcopy
import csv
import json
from types import ModuleType, SimpleNamespace as NS
import sys

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from maritime_perception.adapters.imu_formatter import ImuSample, from_imu_msg
from maritime_perception.adapters.imu_input import PipelineImuSink
from maritime_perception.adapters.imu_output import ImuOutput
from maritime_perception.adapters.imu_session import integrate_session
from maritime_perception.adapters.ros_conversion import imu_to_state
from maritime_perception.pipeline import PerceptionPipeline
from maritime_perception.replay import line, replay_session, write_json
from maritime_perception.validation import Unavailable


def message(stamp=1_793_804_400_000_000_007, yaw=90):
    q = Rotation.from_euler("z", yaw, degrees=True).as_quat()
    return NS(header=NS(stamp=NS(sec=stamp//10**9, nanosec=stamp%10**9), frame_id="base_link"),
              orientation=NS(**dict(zip("xyzw", q))),
              linear_acceleration=NS(x=0., y=0., z=9.81), angular_velocity=NS(x=1., y=0., z=0.),
              orientation_covariance=(np.eye(3)*.01).reshape(-1).tolist(),
              angular_velocity_covariance=(np.eye(3)*.02).reshape(-1).tolist(),
              linear_acceleration_covariance=(np.eye(3)*.03).reshape(-1).tolist())


@pytest.fixture
def contract():
    # Test fixture assertions, never an assertion about the physical FCU.
    return dict(expected_frame_id="base_link", orientation_covariance_frame="body",
                conventions_verified=True, clock_verified=True, covariance_decomposition_verified=True)


def navigation(events, stamp):
    data = deepcopy(next(e["data"] for e in events if e["kind"] == "vehicle_state"))
    data["stamp_ns"] = stamp
    data["sample_pose_covariance"] = np.diag([.1]*3 + [.01]*3).tolist()
    data["shared_pose_covariance"] = np.diag([2.25, 2.25, 0., 0., 0., .04]).tolist()
    return data


def test_exact_roundtrip_and_human_csv_keep_quaternion_covariance_and_ns(tmp_path):
    sample = from_imu_msg(message())
    assert sample.stamp_ns % 10**9 == 7
    assert sample.yaw == pytest.approx(90)
    assert ImuSample.from_record(json.loads(line(sample.to_record()))) == sample
    seen, printed = [], []
    output = ImuOutput(tmp_path/"imu.csv", 0., printed.append, jsonl_path=tmp_path/"imu.jsonl", on_sample=seen.append)
    output.handle(sample)
    output.close()
    output.close()
    assert seen == [sample] and not printed
    with (tmp_path/"imu.csv").open() as stream:
        row = next(csv.DictReader(stream))
    assert int(row["stamp_ns"]) == sample.stamp_ns
    assert json.loads(row["quaternion_xyzw"]) == list(sample.quaternion_xyzw)
    assert ImuSample.from_record(json.loads((tmp_path/"imu.jsonl").read_text())) == sample
    with pytest.raises(FileExistsError):
        ImuOutput(tmp_path/"imu.csv")
    with pytest.raises(ValueError, match="closed"):
        output.handle(sample)


@pytest.mark.parametrize("field", ["orientation", "angular_velocity", "linear_acceleration"])
def test_ros_unreported_and_unknown_covariance_semantics(field):
    msg = message()
    setattr(msg, field + "_covariance", [-1.] + [0.]*8)
    setattr(msg, field, NS(x=float("nan"), y=0., z=0., w=0.))
    sample = from_imu_msg(msg)
    key = "quaternion_xyzw" if field == "orientation" else field
    assert getattr(sample, key) is None
    assert ImuSample.from_record(json.loads(line(sample.to_record()))) == sample
    msg = message()
    setattr(msg, field + "_covariance", [0.]*9)
    sample = from_imu_msg(msg)
    assert getattr(sample, field + "_covariance") is None
    assert getattr(sample, key) is not None


@pytest.mark.parametrize("bad", ["zero_quaternion", "nan_quaternion", "bad_norm", "nan_rate", "bad_stamp", "negative_stamp", "float_stamp", "missing_frame", "negative_covariance", "asymmetric_covariance"])
def test_corrupt_measurements_are_rejected(bad):
    msg = message()
    if bad == "zero_quaternion":
        msg.orientation = NS(x=0., y=0., z=0., w=0.)
    elif bad == "nan_quaternion":
        msg.orientation.w = float("nan")
    elif bad == "bad_norm":
        msg.orientation.w = 2.
    elif bad == "nan_rate":
        msg.angular_velocity.x = float("inf")
    elif bad == "bad_stamp":
        msg.header.stamp.nanosec = 10**9
    elif bad == "negative_stamp":
        msg.header.stamp.sec = -1
    elif bad == "float_stamp":
        msg.header.stamp.nanosec = 1.5
    elif bad == "missing_frame":
        msg.header.frame_id = ""
    elif bad == "negative_covariance":
        msg.orientation_covariance[4] = -.2
    else:
        msg.orientation_covariance[1] = .1
    with pytest.raises(Unavailable):
        from_imu_msg(msg)


def test_enu_rotation_and_preserved_shared_error_no_second_ned_conversion(events, contract):
    sample = from_imu_msg(message())
    nav = navigation(events, sample.stamp_ns)
    result = imu_to_state(sample, nav, **contract)
    np.testing.assert_allclose(result["angular_velocity_enu_rad_s"], [0., 1., 0.], atol=1e-12)
    assert result["quaternion_xyzw"] == list(sample.quaternion_xyzw)
    assert result["position_enu_m"] == nav["position_enu_m"]
    assert result["shared_pose_covariance"] == nav["shared_pose_covariance"]
    assert result["shared_model_id"] == nav["shared_model_id"]
    # An anisotropic body covariance rotates into the ENU tangent frame.
    msg = message()
    msg.orientation_covariance = np.diag([.01, .02, .03]).reshape(-1).tolist()
    nav["sample_pose_covariance"] = np.diag([.1]*3 + [.02, .01, .03]).tolist()
    imu_to_state(from_imu_msg(msg), nav, **contract)
    nav["sample_pose_covariance"][3][3] = .01
    with pytest.raises(Unavailable, match="covariance_margin"):
        imu_to_state(from_imu_msg(msg), nav, **contract)


@pytest.mark.parametrize("bad", ["frame", "clock", "decomposition", "time", "heading", "height", "position", "unknown_covariance", "unreported_orientation", "covariance_frame", "body_frame", "small_model_covariance"])
def test_bridge_rejects_unusable_navigation_and_never_makes_positions(events, contract, bad):
    msg = message()
    nav = navigation(events, from_imu_msg(msg).stamp_ns)
    if bad == "frame":
        contract["expected_frame_id"] = "imu_link"
    elif bad == "clock":
        contract["clock_verified"] = False
    elif bad == "decomposition":
        contract["covariance_decomposition_verified"] = False
    elif bad == "time":
        nav["stamp_ns"] += 1
    elif bad in ("heading", "height", "position"):
        nav["quality"][bad + "_valid"] = False
    elif bad == "unknown_covariance":
        msg.orientation_covariance = [0.]*9
    elif bad == "unreported_orientation":
        msg.orientation_covariance[0] = -1.
    elif bad == "covariance_frame":
        contract["orientation_covariance_frame"] = "guess"
    elif bad == "body_frame":
        nav["body_frame"] = "FRD"
    else:
        nav["sample_pose_covariance"] = np.zeros((6, 6)).tolist()
    with pytest.raises(Unavailable):
        imu_to_state(from_imu_msg(msg), nav, **contract)


def test_pipeline_callback_and_recorded_replay_reach_analytic_gps(tmp_path, settings, events, contract):
    session = tmp_path/"navigation"
    session.mkdir()
    write_json(session/"config.json", settings)
    imu_file, contract_file = tmp_path/"imu.jsonl", tmp_path/"contract.json"
    write_json(contract_file, contract)
    pipeline = PerceptionPipeline(settings)
    expected = PerceptionPipeline(settings)
    adapted_events, raw_samples = [], []
    for event in events:
        if event["kind"] == "vehicle_state":
            stamp = event["data"]["stamp_ns"]
            sample = from_imu_msg(message(stamp))
            nav = navigation(events, stamp)
            adapted_events.append(dict(kind="vehicle_state", data=nav))
            raw_samples.append(line(sample.to_record()))
            PipelineImuSink(pipeline, lambda requested: nav, contract)(sample)
            expected.add_state(imu_to_state(sample, nav, **contract))
        else:
            frame = deepcopy(event["data"])
            frame["detections"] = [dict(id=frame["id"]+"_manual", class_id="buoy",
                pixel_uv=[700., 480.], pixel_covariance=[[.25, 0.], [0., .25]], reference_method="water_centre")]
            adapted_events.append(dict(kind="frame", data=frame))
            report, ledger = pipeline.process_frame(frame)
            reference, _ = expected.process_frame(frame)
            assert line(report) == line(reference)
            assert not report["diagnostics"] or all(d.get("status") != "rejected" for d in report["diagnostics"])
            np.testing.assert_allclose(ledger[0]["mean_en_m"], [.4, 0.], atol=1e-12)
            assert np.linalg.eigvalsh(report["tracks"][0]["uncertainty"]["shared_covariance_en_m2"])[0] >= 2.25-1e-10
    (session/"measurements.jsonl").write_text("".join(line(e) for e in adapted_events))
    imu_file.write_text("".join(raw_samples))
    assert integrate_session(session, imu_file, contract_file, tmp_path/"joined") == len(raw_samples)
    assert not (tmp_path/"joined/truth.json").exists()
    assert (tmp_path/"joined/imu_samples.jsonl").read_bytes() == imu_file.read_bytes()
    replay_session(tmp_path/"joined", tmp_path/"result")
    replay_session(tmp_path/"joined", tmp_path/"again")
    for name in ("reports.jsonl", "observations.jsonl", "replay_errors.jsonl"):
        assert (tmp_path/"result"/name).read_bytes() == (tmp_path/"again"/name).read_bytes()
    final = json.loads((tmp_path/"result/reports.jsonl").read_text().splitlines()[-1])
    assert line(final) == line(report)
    assert (tmp_path/"result/replay_errors.jsonl").read_text() == ""
    # One nanosecond of mismatch fails; no partial session becomes usable.
    imu_file.write_text("".join(line(dict(json.loads(raw), stamp_ns=json.loads(raw)["stamp_ns"]+1)) for raw in raw_samples))
    with pytest.raises(Unavailable, match="time_mismatch"):
        integrate_session(session, imu_file, contract_file, tmp_path/"mismatched")
    assert not (tmp_path/"mismatched").exists()


def test_invalid_imu_is_diagnostic_not_a_fresh_pose(settings, events, contract):
    pipeline = PerceptionPipeline(settings)
    sample = from_imu_msg(message())
    nav = navigation(events, sample.stamp_ns)
    contract["clock_verified"] = False
    pipeline.add_imu_state(dict(imu=sample.to_record(), navigation=nav, contract=contract))
    frame = next(e["data"] for e in events if e["kind"] == "frame")
    report, ledger = pipeline.process_frame(frame)
    assert not ledger and not report["tracks"]
    assert "imu_clock_contract_unverified" in {d.get("reason") for d in report["diagnostics"]}


def test_ros_listener_callback_qos_and_shutdown_without_ros(monkeypatch, tmp_path):
    from maritime_perception.adapters import imu_listener
    state = NS(destroyed=0, shutdown=0, warnings=[], qos=None)
    class Node:
        def __init__(self, name):
            self.parameters = {}
        def declare_parameter(self, name, value):
            self.parameters[name] = str(tmp_path/"record.jsonl") if name == "jsonl_path" else value
        def get_parameter(self, name):
            return NS(value=self.parameters[name])
        def get_logger(self):
            return NS(info=lambda value: None, warning=lambda value, **kw: state.warnings.append(value))
        def create_subscription(self, kind, topic, callback, qos):
            state.qos, self.callback = qos, callback
        def destroy_node(self):
            state.destroyed += 1
    sentinel = object()
    rclpy = ModuleType("rclpy")
    rclpy.init = lambda: None
    rclpy.ok = lambda: True
    rclpy.shutdown = lambda: setattr(state, "shutdown", state.shutdown+1)
    def spin(node):
        node.callback(message())
        bad = message()
        bad.orientation.w = 99.
        node.callback(bad)
        raise KeyboardInterrupt
    rclpy.spin = spin
    for name, module in {"rclpy": rclpy, "rclpy.node": NS(Node=Node),
                         "rclpy.qos": NS(qos_profile_sensor_data=sentinel),
                         "sensor_msgs": ModuleType("sensor_msgs"), "sensor_msgs.msg": NS(Imu=object)}.items():
        monkeypatch.setitem(sys.modules, name, module)
    imu_listener.main()
    assert state.qos is sentinel and state.destroyed == state.shutdown == 1
    assert len(state.warnings) == 1
    assert len((tmp_path/"record.jsonl").read_text().splitlines()) == 1
    # Startup failure also destroys the node and shuts ROS down.
    with pytest.raises(FileExistsError):
        imu_listener.main()
    assert state.destroyed == state.shutdown == 2
