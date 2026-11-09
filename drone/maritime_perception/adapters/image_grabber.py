"""Bounded GStreamer capture, calibrated pixels and replayable image records.

Uses GStreamer GI directly: the pinned headless OpenCV wheel need not be rebuilt
with GStreamer support. No ROS or Jetson imports are needed for calibration/tests.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import time
import uuid

import cv2
import numpy as np

from ..replay import line, write_json
from ..validation import Unavailable, timestamp
from .camera_calibration import ImageProcessor, Intrinsics, builtin_calibration
from .camera_settings import parse_settings


def make_processor(settings):
    intrinsics = None
    if settings.calibration != "none":
        path = settings.calibration
        if path.startswith("builtin:"):
            name = path.split(":", 1)[1]
            if name not in ("arducam_info.yaml", "kalibr.yaml"):
                raise Unavailable("unknown_builtin_camera_calibration")
            path = builtin_calibration(name)
        intrinsics = Intrinsics.load(path).for_capture([settings.width, settings.height], settings.calibration_roi)
    elif settings.calibration_roi is not None:
        raise Unavailable("calibration_roi_without_calibration")
    return ImageProcessor(intrinsics, [settings.width, settings.height], settings.output_size,
                          rectify=settings.rectify, alpha=settings.rectify_alpha)


def packed_bgr(data, width, height, stride, offset=0):
    """Copy BGRx while respecting negotiated row padding and video-meta offset."""
    if min(width, height) <= 0 or stride < width*4 or offset < 0 or offset+(height-1)*stride+width*4 > len(data):
        raise Unavailable("invalid_camera_buffer_layout")
    return np.ndarray((height, width, 4), np.uint8, buffer=data, offset=offset,
                      strides=(stride, 4, 1))[:, :, :3].copy()


class GstCamera:
    def __init__(self, settings):
        settings.validate()
        try:
            import gi
            gi.require_version("Gst", "1.0")
            gi.require_version("GstVideo", "1.0")
            from gi.repository import Gst, GstVideo
        except (ImportError, ValueError) as exc:
            raise Unavailable("gstreamer_gi_unavailable: install host GStreamer/GI and use its compatible system Python") from exc
        self.gst, self.video, self.settings = Gst, GstVideo, settings
        self.pipeline, self.sink = None, None
        self.last_pts = -1
        Gst.init(None)
        required = ("nvarguscamerasrc", "nvvidconv", "appsink") if settings.adapter == "argus" else ("videotestsrc", "appsink")
        missing = [name for name in required if Gst.ElementFactory.find(name) is None]
        if missing:
            raise Unavailable("missing_gstreamer_elements:" + ",".join(missing))
        try:
            self.pipeline = Gst.parse_launch(settings.pipeline())
            self.sink = self.pipeline.get_by_name("capture")
            if self.sink is None:
                raise Unavailable("camera_appsink_unavailable")
            if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
                raise Unavailable("camera_start_failed")
            result, state, _ = self.pipeline.get_state(round(settings.startup_timeout_s*Gst.SECOND))
            self.check_bus()
            if result == Gst.StateChangeReturn.FAILURE or state != Gst.State.PLAYING:
                raise Unavailable("camera_start_timeout")
        except Exception:
            self.close()
            raise

    def check_bus(self):
        Gst = self.gst
        message = self.pipeline.get_bus().timed_pop_filtered(0, Gst.MessageType.ERROR | Gst.MessageType.EOS)
        if message is not None:
            if message.type == Gst.MessageType.ERROR:
                error, debug = message.parse_error()
                raise Unavailable(f"camera_gstreamer_error:{error}; {debug}")
            raise Unavailable("camera_end_of_stream")

    def read(self):
        if self.pipeline is None:
            raise Unavailable("camera_closed")
        self.check_bus()
        sample = self.sink.emit("try-pull-sample", round(self.settings.read_timeout_s*self.gst.SECOND))
        arrival_unix, arrival_monotonic = time.time_ns(), time.monotonic_ns()
        self.check_bus()
        if sample is None:
            raise Unavailable("camera_read_timeout")
        buffer, caps = sample.get_buffer(), sample.get_caps()
        info = self.video.VideoInfo.new_from_caps(caps)
        structure = caps.get_structure(0)
        rate = self.settings.fps_fraction
        if (info.width, info.height, info.fps_n, info.fps_d) != (self.settings.width, self.settings.height, rate.numerator, rate.denominator) or structure.get_string("format") != "BGRx":
            raise Unavailable("camera_negotiated_caps_mismatch")
        pts = buffer.pts
        if pts == self.gst.CLOCK_TIME_NONE:
            raise Unavailable("camera_timestamp_unavailable")
        running = sample.get_segment().to_running_time(self.gst.Format.TIME, pts)
        if running == self.gst.CLOCK_TIME_NONE:
            raise Unavailable("camera_running_timestamp_unavailable")
        running = timestamp(int(running))
        if running <= self.last_pts:
            raise Unavailable("camera_clock_reset_or_duplicate_requires_new_session")
        meta = self.video.buffer_get_video_meta(buffer)
        stride, offset = (meta.stride[0], meta.offset[0]) if meta is not None else (info.stride[0], info.offset[0])
        success, mapped = buffer.map(self.gst.MapFlags.READ)
        if not success:
            raise Unavailable("camera_buffer_map_failed")
        try:
            image = packed_bgr(mapped.data, info.width, info.height, stride, offset)
        finally:
            buffer.unmap(mapped)
        self.last_pts = running
        duration = None if buffer.duration == self.gst.CLOCK_TIME_NONE else int(buffer.duration)
        return image, dict(stamp_ns=running, buffer_pts_ns=int(pts), duration_ns=duration,
                           pipeline_base_time_ns=int(self.pipeline.get_base_time()),
                           arrival_unix_ns=arrival_unix, arrival_monotonic_ns=arrival_monotonic,
                           negotiated_size=[info.width, info.height], negotiated_fps=f"{info.fps_n}/{info.fps_d}")

    def close(self):
        if self.pipeline is not None:
            self.pipeline.set_state(self.gst.State.NULL)
            self.pipeline = None


@dataclass
class CapturedFrame:
    image: np.ndarray
    metadata: dict
    camera_info: dict

    def detection_frame(self, origin_id):
        """Use with the existing detector. Unverified PTS never claims exposure time."""
        if self.metadata["calibration_id"] is None:
            raise Unavailable("capture_calibration_unavailable")
        return dict(self.metadata, origin_id=origin_id, source_image_size=self.metadata["input_image_size"],
                    source_from_input=np.eye(3).tolist(), detections=[])


class CaptureSession:
    def __init__(self, settings, *, camera_factory=GstCamera):
        self.settings = settings.validate()
        self.processor = make_processor(settings)
        self.session_id = "capture_" + uuid.uuid4().hex
        self.clock_id = "gstreamer_" + self.session_id
        self.sequence = 0
        self.camera = camera_factory(settings)

    def read(self):
        image, timing = self.camera.read()
        image = self.processor.process(image)
        metadata = dict(timing, id=f"{self.session_id}_{self.sequence:08d}", capture_session_id=self.session_id,
                        clock_id=self.clock_id, stamp_semantics="gstreamer_running_time_unverified",
                        frame_id=self.settings.frame_id, input_image_size=self.settings.output_size,
                        calibration_id=None if self.processor.model is None else self.processor.model["calibration_id"],
                        image_domain="rectified" if self.settings.rectify else "raw", synthetic=self.settings.adapter == "videotest",
                        published_ns=time.time_ns(), requested_controls=asdict(self.settings),
                        actual_exposure_us=None, actual_analog_gain=None, actual_digital_gain=None,
                        rolling_shutter_readout_ns=None, exposure_time_verified=False)
        self.sequence += 1
        return CapturedFrame(image, metadata, self.processor.camera_info())

    def close(self):
        self.camera.close()


class CaptureRecorder:
    def __init__(self, session):
        self.settings = session.settings
        self.path = Path(self.settings.output)
        self.path.mkdir(parents=True, exist_ok=False)
        self.stream = None
        self.last_saved_ns = None
        self.saved = 0
        try:
            (self.path/"images").mkdir()
            write_json(self.path/"capture_config.json", dict(schema="maritime.camera_capture", version=1,
                       session_id=session.session_id, source_mode="synthetic" if self.settings.adapter == "videotest" else "hardware",
                       synthetic=self.settings.adapter == "videotest", settings=asdict(self.settings),
                       gstreamer_pipeline=self.settings.pipeline(), effective_camera_model=session.processor.model,
                       camera_info=session.processor.camera_info(), clock_id=session.clock_id,
                       timing_verified=False, actual_controls_verified=False))
            self.stream = (self.path/"frames.jsonl").open("x", buffering=1)
        except Exception:
            self.close()
            raise

    def handle(self, packet):
        stamp = packet.metadata["stamp_ns"]
        if self.last_saved_ns is not None and stamp-self.last_saved_ns < round(self.settings.save_interval_s*1e9):
            return False
        filename = f"images/{packet.metadata['id']}.{self.settings.image_format}"
        params = [cv2.IMWRITE_JPEG_QUALITY, self.settings.jpeg_quality] if self.settings.image_format == "jpg" else []
        success, encoded = cv2.imencode("."+self.settings.image_format, packet.image, params)
        if not success:
            raise Unavailable("camera_image_encode_failed")
        payload = encoded.tobytes()
        with (self.path/filename).open("xb") as output:
            output.write(payload)
        self.stream.write(line(dict(packet.metadata, image_file=filename,
                                    image_sha256=hashlib.sha256(payload).hexdigest(), camera_info=packet.camera_info)))
        self.last_saved_ns, self.saved = stamp, self.saved+1
        return True

    def close(self):
        if self.stream is not None:
            self.stream.close()
            self.stream = None


def main():
    settings, args, ros_args = parse_settings()
    if args.dry_run:
        processor = make_processor(settings)
        print(json.dumps(dict(settings=asdict(settings), pipeline=settings.pipeline(), effective_camera_model=processor.model), indent=2))
        return
    if args.ros:
        from .camera_ros import run_ros
        run_ros(settings, ros_args)
        return
    if not settings.output:
        raise SystemExit("Choose --output NEW_DIRECTORY for recording or --ros for image publication")
    if Path(settings.output).exists():
        raise FileExistsError(settings.output)
    session, recorder = None, None
    try:
        session = CaptureSession(settings)
        recorder = CaptureRecorder(session)
        started, last_poll = time.monotonic(), float("-inf")
        processed = 0
        while not settings.duration_s or time.monotonic()-started < settings.duration_s:
            remaining = 1/settings.publish_hz-(time.monotonic()-last_poll)
            if remaining > 0:
                time.sleep(min(remaining, 1.))
                continue
            packet = session.read()
            last_poll = time.monotonic()
            recorder.handle(packet)
            processed += 1
            if settings.max_frames and processed >= settings.max_frames:
                break
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if recorder is not None:
                recorder.close()
                print(f"Saved {recorder.saved} frames to {recorder.path}")
        finally:
            if session is not None:
                session.close()


if __name__ == "__main__":
    main()
