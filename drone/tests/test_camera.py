from dataclasses import asdict, replace
import hashlib
import json
from types import ModuleType, SimpleNamespace as NS
import sys

import cv2
import numpy as np
import pytest
import yaml

from maritime_perception.adapters.camera_calibration import ImageProcessor, Intrinsics, builtin_calibration
from maritime_perception.adapters.camera_ros import resized_camera_info
from maritime_perception.adapters.camera_settings import CaptureSettings, parse_settings
from maritime_perception.adapters.image_grabber import CaptureRecorder, CaptureSession, GstCamera, make_processor, packed_bgr
from maritime_perception.adapters.ros_conversion import detections_to_frame
from maritime_perception.geometry import CameraGeometry
from maritime_perception.pipeline import PerceptionPipeline
from maritime_perception.validation import Unavailable


def test_imported_calibrations_are_one_model_and_raw_projection_uses_k_not_p():
    ros = Intrinsics.load(builtin_calibration())
    kalibr = Intrinsics.load(builtin_calibration("kalibr.yaml"))
    assert [ros.width, ros.height] == [3840, 2160]
    np.testing.assert_array_equal(ros.k, kalibr.k)
    np.testing.assert_array_equal(ros.d, kalibr.d)
    assert ros.provenance["lens_mode_verified"] is False
    assert ros.k[0, 0] == 2334.99647 and ros.d[0] == -.233303
    info = ImageProcessor(ros, [3840, 2160], [3840, 2160]).camera_info()
    assert info["p"][0] == ros.k[0, 0]  # Historical P is rectified; raw pixels need K.


def test_resolution_changes_require_mode_mapping_and_output_resize_uses_pixel_centres():
    source = Intrinsics.load(builtin_calibration())
    with pytest.raises(Unavailable, match="mode_transform"):
        source.for_capture([1920, 1080])
    full = source.for_capture([1920, 1080], [0, 0, 3840, 2160])
    cropped = source.for_capture([1920, 1080], [100, 50, 3000, 1800])
    assert full.k[0, 2] == pytest.approx((source.k[0, 2]+.5)/2-.5)
    assert cropped.k[1, 2] == pytest.approx((source.k[1, 2]-50+.5)*.6-.5)
    processor = ImageProcessor(source, [3840, 2160], [1920, 1080])
    np.testing.assert_allclose(processor.model["camera_matrix"], full.k)
    assert processor.model["distortion"] == source.d.tolist()
    for roi in ([-1, 0, 100, 100], [0, 0, 5000, 100], [0, 0, 0, 100]):
        with pytest.raises(Unavailable):
            source.for_capture([1920, 1080], roi)


def small_intrinsics(tmp_path, distortion=True):
    path = tmp_path/"intrinsics.yaml"
    d = [-.1, .02, .001, -.002, 0.] if distortion else [0.]*5
    path.write_text(yaml.safe_dump(dict(image_width=64, image_height=48,
        camera_matrix=dict(data=[30., 0., 32., 0., 30., 24., 0., 0., 1.]),
        distortion_model="plumb_bob", distortion_coefficients=dict(data=d))))
    return Intrinsics.load(path), str(path)


@pytest.mark.parametrize("rectify", [False, True])
def test_rectification_resize_and_preview_describe_the_actual_rays(tmp_path, rectify):
    cal, _ = small_intrinsics(tmp_path)
    processor = ImageProcessor(cal, [64, 48], [32, 24], rectify=rectify, alpha=.5)
    optical = np.array([.2, -.1, 1.])
    raw, _ = cv2.projectPoints(optical.reshape(1, 3), np.zeros(3), np.zeros(3), cal.k, cal.d)
    raw = raw.reshape(2)
    image = np.zeros((48, 64, 3), dtype=np.uint8)
    output = processor.process(image)
    assert output.shape == (24, 32, 3)
    model = processor.model
    k = np.array(model["camera_matrix"])
    if rectify:
        delivered = (k @ optical)[:2]
        assert model["distortion"] == [0.]*5
        assert model["image_domain"] == "rectified"
    else:
        delivered = (raw+.5)/2-.5
    ray = CameraGeometry.ray(delivered, [k[0, 0], k[1, 1], k[0, 2], k[1, 2]], np.array(model["distortion"]), model["image_domain"])
    np.testing.assert_allclose(ray, optical/np.linalg.norm(optical), atol=1e-7)
    info = processor.camera_info()
    preview = resized_camera_info(info, [16, 12])
    assert [preview["width"], preview["height"]] == [16, 12]
    assert preview["k"][0] == pytest.approx(info["k"][0]/2)
    assert preview["k"][2] == pytest.approx((info["k"][2]+.5)/2-.5)
    assert preview["d"] == info["d"]
    assert make_processor(CaptureSettings(width=64, height=48, calibration="none")).camera_info()["k"][0] == 0
    with pytest.raises(Unavailable, match="requires_calibration"):
        make_processor(CaptureSettings(width=64, height=48, calibration="none", rectify=True))


def test_explicit_controls_units_ranges_and_cli_overrides(tmp_path):
    path = tmp_path/"capture.json"
    path.write_text(json.dumps(dict(fps="30000/1001", publish_hz=10., shutter_speed=500., gain=2., rectify=True)))
    settings, args, ros_args = parse_settings(["--config", str(path), "--no-rectify", "--gain", "3", "--wb-mode", "6", "--dry-run"])
    pipeline = settings.pipeline()
    assert 'exposuretimerange="2000000 2000000"' in pipeline
    assert 'gainrange="3 3"' in pipeline and "framerate=30000/1001" in pipeline and "wbmode=6" in pipeline
    assert "max-buffers=1" in pipeline and "drop=true" in pipeline and "wait-on-eos=false" in pipeline
    assert not settings.rectify and args.dry_run and ros_args == []
    exposure, _, _ = parse_settings(["--exposure-min-us", "200", "--exposure-max-us", "1000",
        "--gain-min", "1", "--gain-max", "4", "--digital-gain", "1", "--sensor-mode", "2", "--ae-lock"])
    text = exposure.pipeline()
    assert 'exposuretimerange="200000 1000000"' in text and 'gainrange="1 4"' in text
    assert 'ispdigitalgainrange="1 1"' in text and "sensor-mode=2" in text and "aelock=true" in text
    with pytest.raises(SystemExit):
        parse_settings(["--shuter-speed", "1000"])


@pytest.mark.parametrize("change", [dict(width=0), dict(fps="0"), dict(fps="1/0"), dict(fps="30 ! fakesink"),
    dict(publish_hz=100), dict(shutter_speed=1000, exposure_us=100), dict(exposure_us=100, exposure_max_us=500, exposure_min_us=100),
    dict(exposure_min_us=100), dict(exposure_min_us=500, exposure_max_us=100), dict(exposure_us=1e6),
    dict(gain=.5), dict(digital_gain=257), dict(wb_mode=20), dict(ee_strength=2), dict(sensor_mode=-2),
    dict(output_width=960), dict(preview_width=960), dict(read_timeout_s=0), dict(fps="nan"),
    dict(exposure_us=float("inf")), dict(ae_lock="false"), dict(width=True), dict(adapter="videotest", gain=2)])
def test_invalid_or_ambiguous_controls_fail_before_hardware(change):
    with pytest.raises(Unavailable):
        replace(CaptureSettings(), **change).validate()


def test_padded_bgrx_buffer_and_map_lifetime():
    raw = bytearray(48)
    expected = np.arange(18, dtype=np.uint8).reshape(2, 3, 3)
    for row in range(2):
        for col in range(3):
            start = 4+row*20+col*4
            raw[start:start+3] = expected[row, col].tobytes()
    image = packed_bgr(raw, 3, 2, 20, 4)
    raw[:] = bytes(len(raw))
    np.testing.assert_array_equal(image, expected)  # Independent of the unmapped buffer.
    with pytest.raises(Unavailable):
        packed_bgr(b"short", 3, 2, 12)


@pytest.fixture
def fake_gst(monkeypatch):
    state = NS(missing=False, startup_failure=False, startup_timeout=False, bus_error=False,
        eos=False, no_sample=False, bad_caps=False, pts=5_000_000, null_count=0, unmapped=0)
    Gst = NS(SECOND=10**9, CLOCK_TIME_NONE=2**64-1, State=NS(PLAYING=1, NULL=0),
        StateChangeReturn=NS(FAILURE=-1, SUCCESS=1), MessageType=NS(ERROR=1, EOS=2), Format=NS(TIME=1), MapFlags=NS(READ=1), init=lambda _: None)
    class Buffer:
        duration = 1_000_000
        @property
        def pts(self):
            return state.pts
        def map(self, flags):
            return True, NS(data=bytes(64*48*4))
        def unmap(self, mapped):
            state.unmapped += 1
    class Sink:
        def emit(self, name, timeout):
            assert name == "try-pull-sample" and timeout > 0
            if state.no_sample:
                return None
            return NS(get_buffer=lambda: Buffer(), get_caps=lambda: NS(get_structure=lambda index: NS(get_string=lambda key: "BGRx")),
                      get_segment=lambda: NS(to_running_time=lambda format, pts: pts))
    class Pipeline:
        def get_by_name(self, name):
            return Sink()
        def set_state(self, value):
            if value == Gst.State.NULL:
                state.null_count += 1
            return -1 if state.startup_failure and value else 1
        def get_state(self, timeout):
            return 1, (0 if state.startup_timeout else 1), 0
        def get_base_time(self):
            return 999
        def get_bus(self):
            def pop(timeout, types):
                if state.bus_error:
                    return NS(type=1, parse_error=lambda: ("driver error", "debug"))
                if state.eos:
                    return NS(type=2)
            return NS(timed_pop_filtered=pop)
    Gst.parse_launch = lambda text: Pipeline()
    Gst.ElementFactory = NS(find=lambda name: None if state.missing else object())
    GstVideo = NS(VideoInfo=NS(new_from_caps=lambda caps: NS(width=63 if state.bad_caps else 64, height=48,
                  fps_n=17, fps_d=1, stride=[64*4], offset=[0])), buffer_get_video_meta=lambda buffer: None)
    gi = ModuleType("gi")
    gi.require_version = lambda *args: None
    monkeypatch.setitem(sys.modules, "gi", gi)
    monkeypatch.setitem(sys.modules, "gi.repository", NS(Gst=Gst, GstVideo=GstVideo))
    return state, Gst


def test_gstreamer_sample_timestamps_cleanup_and_no_camera_fallback(fake_gst):
    state, Gst = fake_gst
    settings = CaptureSettings(width=64, height=48, calibration="none")
    camera = GstCamera(settings)
    image, metadata = camera.read()
    assert image.shape == (48, 64, 3) and metadata["stamp_ns"] == state.pts and state.unmapped == 1
    assert metadata["arrival_unix_ns"] > metadata["stamp_ns"]
    with pytest.raises(Unavailable, match="reset_or_duplicate"):
        camera.read()
    camera.close()
    camera.close()
    assert state.null_count == 1
    with pytest.raises(Unavailable, match="closed"):
        camera.read()


@pytest.mark.parametrize("failure,reason", [("missing", "missing_gstreamer"), ("startup_failure", "start_failed"),
    ("startup_timeout", "start_timeout"), ("bus_error", "gstreamer_error"), ("eos", "end_of_stream"),
    ("no_sample", "read_timeout"), ("bad_caps", "negotiated_caps"), ("no_pts", "timestamp_unavailable")])
def test_camera_failures_are_explicit(fake_gst, failure, reason):
    state, Gst = fake_gst
    settings = CaptureSettings(width=64, height=48, calibration="none")
    if failure in ("missing", "startup_failure", "startup_timeout", "bus_error", "eos"):
        setattr(state, failure, True)
        with pytest.raises(Unavailable, match=reason):
            GstCamera(settings)
        assert state.null_count == (0 if failure == "missing" else 1)
    else:
        camera = GstCamera(settings)
        if failure == "no_pts":
            state.pts = Gst.CLOCK_TIME_NONE
        else:
            setattr(state, failure, True)
        try:
            with pytest.raises(Unavailable, match=reason):
                camera.read()
        finally:
            camera.close()


def test_capture_recording_metadata_roundtrip_and_write_failure(tmp_path, fake_gst, monkeypatch):
    _, calibration = small_intrinsics(tmp_path)
    settings = CaptureSettings(width=64, height=48, output_width=32, output_height=24,
        calibration=calibration, rectify=True, output=str(tmp_path/"recording"), save_interval_s=1.)
    session = CaptureSession(settings)
    recorder = CaptureRecorder(session)
    try:
        packet = session.read()
        assert packet.metadata["stamp_semantics"] == "gstreamer_running_time_unverified"
        assert packet.metadata["actual_exposure_us"] is None
        assert packet.detection_frame("origin")["source_image_size"] == [32, 24]
        assert packet.camera_info["d"] == [0.]*5
        assert recorder.handle(packet)
        assert not recorder.handle(packet)
        record = json.loads((tmp_path/"recording/frames.jsonl").read_text())
        payload = (tmp_path/"recording"/record["image_file"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == record["image_sha256"]
        decoded = cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR)
        np.testing.assert_array_equal(decoded, packet.image)
        with pytest.raises(FileExistsError):
            CaptureRecorder(session)
        monkeypatch.setattr(cv2, "imencode", lambda *args: (False, None))
        packet.metadata["stamp_ns"] += 2*10**9
        with pytest.raises(Unavailable, match="encode_failed"):
            recorder.handle(packet)
    finally:
        recorder.close()
        session.close()


def test_detection_conversion_pairs_capture_metadata_and_keeps_source_pts(tmp_path, fake_gst):
    _, path = small_intrinsics(tmp_path)
    session = CaptureSession(CaptureSettings(width=64, height=48, calibration=path))
    packet = session.read()
    session.close()
    metadata = packet.detection_frame("origin")
    metadata["ros_header_stamp_ns"] = packet.metadata["arrival_unix_ns"]
    sec, ns = divmod(metadata["ros_header_stamp_ns"], 10**9)
    message = NS(header=NS(frame_id=metadata["frame_id"], stamp=NS(sec=sec, nanosec=ns)), detections=[])
    frame = detections_to_frame(message, metadata, pixel_sigma_px=1., reference_method="bbox_centre_unvalidated")
    assert frame["stamp_ns"] == packet.metadata["stamp_ns"]
    assert frame["stamp_ns"] != metadata["ros_header_stamp_ns"]
    message.header.stamp.nanosec += 1
    with pytest.raises(Unavailable, match="metadata_mismatch"):
        detections_to_frame(message, metadata, pixel_sigma_px=1., reference_method="bbox_centre_unvalidated")


def test_captured_metadata_enters_existing_pipeline_and_unverified_time_is_rejected(tmp_path, fake_gst, settings, events):
    _, path = small_intrinsics(tmp_path, distortion=False)
    capture = CaptureSession(CaptureSettings(width=64, height=48, output_width=32, output_height=24, calibration=path))
    packet = capture.read()
    capture.close()
    model = packet.camera_info
    settings["calibration"].update(calibration_id=packet.metadata["calibration_id"], width=32, height=24,
        fx_fy_cx_cy=[model["k"][0], model["k"][4], model["k"][2], model["k"][5]], distortion=model["d"])
    frame = packet.detection_frame(settings["origin"]["origin_id"])
    original_frame = next(e["data"] for e in events if e["kind"] == "frame")
    frame.update(stamp_ns=original_frame["stamp_ns"], published_ns=original_frame["published_ns"], clock_id="survey_utc")
    frame["detections"] = [dict(id="manual", class_id="buoy", pixel_uv=[model["k"][2]+3., model["k"][5]],
                               pixel_covariance=[[.25, 0.], [0., .25]], reference_method="water_centre")]
    def process(data):
        pipeline = PerceptionPipeline(settings)
        for event in events:
            if event["kind"] != "vehicle_state":
                break
            pipeline.add_state(event["data"])
        return pipeline.process_frame(data)
    report, ledger = process(frame)
    assert not ledger and not report["tracks"]
    assert "exposure_time_unavailable" in {item.get("reason") for item in report["diagnostics"]}
    # Only this fixture knows the exposure time. Production capture does not assert it.
    frame["stamp_semantics"] = "exposure_midpoint"
    report, ledger = process(frame)
    np.testing.assert_allclose(ledger[0]["mean_en_m"], [0., -.8], atol=1e-12)
    assert len(report["tracks"]) == 1


@pytest.mark.parametrize("read_failure", [False, True])
def test_ros_image_info_metadata_preview_and_shutdown(tmp_path, fake_gst, monkeypatch, read_failure):
    from maritime_perception.adapters.camera_ros import run_ros
    state, _ = fake_gst
    state.no_sample = read_failure
    _, path = small_intrinsics(tmp_path)
    settings = CaptureSettings(width=64, height=48, output_width=32, output_height=24,
        preview_width=16, preview_height=12, calibration=path, rectify=True, max_frames=1)
    published, nodes = {}, []
    lifecycle = NS(shutdown=0, destroyed=0, errors=[])
    class CameraInfo:
        def __init__(self):
            self.header = NS(frame_id="", stamp=NS(sec=0, nanosec=0))
    class Image:
        pass
    class Node:
        def __init__(self, name):
            nodes.append(self)
        def create_publisher(self, message, topic, qos):
            assert qos.depth == 1 and qos.reliability == "best_effort"
            published[topic] = []
            return NS(publish=published[topic].append)
        def create_timer(self, interval, callback):
            return NS(cancel=lambda: None)
        def get_logger(self):
            return NS(info=lambda value: None, error=lifecycle.errors.append)
        def destroy_node(self):
            lifecycle.destroyed += 1
    rclpy = ModuleType("rclpy")
    rclpy.init = lambda **kw: None
    rclpy.ok = lambda: True
    rclpy.spin_once = lambda node: node.tick()
    rclpy.shutdown = lambda: setattr(lifecycle, "shutdown", lifecycle.shutdown+1)
    modules = {"rclpy": rclpy, "rclpy.node": NS(Node=Node),
        "rclpy.qos": NS(QoSProfile=lambda **kw: NS(**kw), ReliabilityPolicy=NS(BEST_EFFORT="best_effort"), HistoryPolicy=NS(KEEP_LAST="keep_last")),
        "sensor_msgs": ModuleType("sensor_msgs"), "sensor_msgs.msg": NS(Image=Image, CameraInfo=CameraInfo),
        "std_msgs": ModuleType("std_msgs"), "std_msgs.msg": NS(String=lambda **kw: NS(**kw))}
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    if read_failure:
        with pytest.raises(Unavailable, match="read_timeout"):
            run_ros(settings, [])
        assert lifecycle.errors and not any(published.values())
    else:
        run_ros(settings, [])
        image = published["/camera/image_rect"][0]
        info = published["/camera/camera_info"][0]
        preview = published["/camera/preview/camera_info"][0]
        metadata = json.loads(published["/camera/frame_metadata"][0].data)
        assert (image.width, image.height, image.step, len(image.data)) == (32, 24, 96, 32*24*3)
        assert image.header.frame_id == "arducam_optical_frame" and info.d == [0.]*5
        assert preview.width == 16 and preview.k[0] == pytest.approx(info.k[0]/2)
        assert metadata["stamp_ns"] == state.pts
        assert metadata["ros_header_stamp_ns"] == image.header.stamp.sec*10**9+image.header.stamp.nanosec
        assert metadata["ros_header_stamp_semantics"] == "host_arrival_unverified"
    assert state.null_count == lifecycle.destroyed == lifecycle.shutdown == 1
