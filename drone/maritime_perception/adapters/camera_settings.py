"""Validated startup settings for the Jetson Argus camera and capture CLI."""
import argparse
from dataclasses import asdict, dataclass, fields
from fractions import Fraction
import math

from ..validation import Unavailable, load_json


@dataclass(frozen=True)
class CaptureSettings:
    adapter: str = "argus"
    sensor_id: int = 0
    sensor_mode: int = -1
    width: int = 3840
    height: int = 2160
    output_width: int = 0
    output_height: int = 0
    fps: str = "17"
    publish_hz: float = 4.
    shutter_speed: float = 0.  # reciprocal seconds; 1000 means 1/1000 s
    exposure_us: float = 0.
    exposure_min_us: float = 0.
    exposure_max_us: float = 0.
    gain: float = 0.
    gain_min: float = 0.
    gain_max: float = 0.
    digital_gain: float = 0.
    digital_gain_min: float = 0.
    digital_gain_max: float = 0.
    wb_mode: int = 1
    ae_lock: bool = False
    awb_lock: bool = False
    exposure_compensation: float = 0.
    antibanding: int = 1
    tnr_mode: int = 1
    tnr_strength: float = -1.
    ee_mode: int = 1
    ee_strength: float = -1.
    calibration: str = "builtin:arducam_info.yaml"
    calibration_roi: tuple | None = None
    rectify: bool = False
    rectify_alpha: float = 0.
    frame_id: str = "arducam_optical_frame"
    ros_topic_profile: str = ""
    output: str = ""
    image_format: str = "png"
    jpeg_quality: int = 95
    save_interval_s: float = 1.
    preview_width: int = 0
    preview_height: int = 0
    read_timeout_s: float = 3.
    startup_timeout_s: float = 10.
    max_frames: int = 0
    duration_s: float = 0.

    @property
    def output_size(self):
        return [self.output_width or self.width, self.output_height or self.height]

    @property
    def fps_fraction(self):
        try:
            return Fraction(str(self.fps))
        except (ValueError, ZeroDivisionError) as exc:
            raise Unavailable("invalid_fps") from exc

    def validate(self):
        if self.adapter not in ("argus", "videotest"):
            raise Unavailable("unsupported_camera_adapter")
        for name in ("width", "height", "sensor_id", "output_width", "output_height", "preview_width",
                     "preview_height", "max_frames", "jpeg_quality", "sensor_mode", "wb_mode", "antibanding", "tnr_mode", "ee_mode"):
            if type(getattr(self, name)) is not int:
                raise Unavailable("invalid_" + name)
        if not (0 < self.width <= 4656 and 0 < self.height <= 3496) or self.sensor_id < 0 or self.sensor_mode < -1:
            raise Unavailable("invalid_sensor_configuration")
        if (self.output_width == 0) != (self.output_height == 0) or min(self.output_width, self.output_height) < 0:
            raise Unavailable("invalid_output_size")
        if (self.preview_width == 0) != (self.preview_height == 0) or min(self.preview_width, self.preview_height) < 0:
            raise Unavailable("invalid_preview_size")
        if max(self.output_size) > 8192 or max(self.preview_width, self.preview_height) > 8192:
            raise Unavailable("oversized_camera_output")
        rate = self.fps_fraction
        if not 0 < rate <= 240 or rate.numerator > 2**31-1 or rate.denominator > 2**31-1:
            raise Unavailable("invalid_fps")
        numeric = ("publish_hz", "shutter_speed", "exposure_us", "exposure_min_us", "exposure_max_us",
                   "gain", "gain_min", "gain_max", "digital_gain", "digital_gain_min", "digital_gain_max",
                   "save_interval_s", "read_timeout_s", "startup_timeout_s", "duration_s")
        for name in numeric:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise Unavailable("invalid_" + name)
        if not 0 < self.publish_hz <= float(rate) or min(self.read_timeout_s, self.startup_timeout_s) <= 0:
            raise Unavailable("invalid_capture_rates_or_timeouts")
        if self.max_frames < 0 or not 1 <= self.jpeg_quality <= 100 or self.image_format not in ("png", "jpg"):
            raise Unavailable("invalid_recording_settings")
        for name, low, high in (("wb_mode", 0, 9), ("antibanding", 0, 3), ("tnr_mode", 0, 2), ("ee_mode", 0, 2),
                                ("rectify_alpha", 0, 1), ("exposure_compensation", -2, 2),
                                ("tnr_strength", -1, 1), ("ee_strength", -1, 1)):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or not low <= value <= high:
                raise Unavailable("invalid_" + name)
        for name in ("ae_lock", "awb_lock", "rectify"):
            if type(getattr(self, name)) is not bool:
                raise Unavailable("invalid_" + name)
        if any(value < 0 and value != -1 for value in (self.tnr_strength, self.ee_strength)):
            raise Unavailable("invalid_image_processing_strength")
        if not isinstance(self.frame_id, str) or not self.frame_id or not isinstance(self.calibration, str):
            raise Unavailable("invalid_camera_frame_or_calibration")
        if not isinstance(self.ros_topic_profile, str):
            raise Unavailable("invalid_ros_topic_profile")
        for prefix, fixed in (("exposure", self.exposure_us), ("gain", self.gain), ("digital_gain", self.digital_gain)):
            suffix = "_us" if prefix == "exposure" else ""
            lower, upper = getattr(self, prefix+"_min"+suffix), getattr(self, prefix+"_max"+suffix)
            if bool(lower) != bool(upper) or lower > upper or (fixed and upper):
                raise Unavailable("conflicting_" + prefix + "_settings")
        if self.shutter_speed and (self.exposure_us or self.exposure_max_us):
            raise Unavailable("shutter_and_exposure_are_alternatives")
        longest = 1e6/self.shutter_speed if self.shutter_speed else (self.exposure_us or self.exposure_max_us)
        if longest > 1e6/float(rate):
            raise Unavailable("exposure_exceeds_frame_period")
        if any(value and round(value*1000) <= 0 for value in (longest, self.exposure_min_us)):
            raise Unavailable("invalid_exposure_nanoseconds")
        if any(value > 256 for value in (self.digital_gain, self.digital_gain_min, self.digital_gain_max)):
            raise Unavailable("invalid_digital_gain")
        for value in (self.gain, self.gain_min, self.gain_max, self.digital_gain, self.digital_gain_min, self.digital_gain_max):
            if value and value < 1:
                raise Unavailable("gain_must_be_at_least_one")
        if self.adapter == "videotest":
            hardware_keys = ("sensor_id", "sensor_mode", "shutter_speed", "exposure_us", "exposure_min_us", "exposure_max_us",
                             "gain", "gain_min", "gain_max", "digital_gain", "digital_gain_min", "digital_gain_max",
                             "wb_mode", "ae_lock", "awb_lock", "exposure_compensation", "antibanding", "tnr_mode",
                             "tnr_strength", "ee_mode", "ee_strength")
            defaults = CaptureSettings()
            if any(getattr(self, key) != getattr(defaults, key) for key in hardware_keys):
                raise Unavailable("hardware_controls_not_available_in_videotest")
        return self

    def pipeline(self):
        self.validate()
        rate = self.fps_fraction
        caps = f"width={self.width},height={self.height},framerate={rate.numerator}/{rate.denominator}"
        if self.adapter == "videotest":
            return f"videotestsrc is-live=true ! video/x-raw,format=BGRx,{caps} ! appsink name=capture max-buffers=1 drop=true sync=false wait-on-eos=false"
        props = [f"sensor-id={self.sensor_id}", f"wbmode={self.wb_mode}", f"aelock={str(self.ae_lock).lower()}",
                 f"awblock={str(self.awb_lock).lower()}", f"exposurecompensation={self.exposure_compensation:g}",
                 f"aeantibanding={self.antibanding}", f"tnr-mode={self.tnr_mode}", f"ee-mode={self.ee_mode}"]
        if self.sensor_mode >= 0:
            props.append(f"sensor-mode={self.sensor_mode}")
        exp = 1e6/self.shutter_speed if self.shutter_speed else self.exposure_us
        for prop, fixed, lower, upper, multiplier in (
                ("exposuretimerange", exp, self.exposure_min_us, self.exposure_max_us, 1000),
                ("gainrange", self.gain, self.gain_min, self.gain_max, 1),
                ("ispdigitalgainrange", self.digital_gain, self.digital_gain_min, self.digital_gain_max, 1)):
            if fixed or upper:
                low, high = (fixed, fixed) if fixed else (lower, upper)
                text = f"{round(low*multiplier)} {round(high*multiplier)}" if prop == "exposuretimerange" else f"{low:g} {high:g}"
                props.append(f'{prop}="{text}"')
        for name in ("tnr_strength", "ee_strength"):
            if getattr(self, name) >= 0:
                props.append(f"{name.replace('_', '-')}={getattr(self, name):g}")
        return ("nvarguscamerasrc " + " ".join(props) + f" ! video/x-raw(memory:NVMM),format=NV12,{caps} "
                "! nvvidconv ! video/x-raw,format=BGRx "
                "! appsink name=capture max-buffers=1 drop=true sync=false wait-on-eos=false")


def parse_settings(argv=None):
    parser = argparse.ArgumentParser(description="Configurable Jetson IMX519 image capture; no hardware fallback")
    parser.add_argument("--config", help="JSON CaptureSettings defaults; explicit CLI options override")
    parser.add_argument("--ros", action="store_true", help="Also publish ROS 2 images, CameraInfo and timing metadata")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print settings/pipeline without opening a camera")
    defaults = CaptureSettings()
    for field in fields(defaults):
        value = getattr(defaults, field.name)
        key = "--" + field.name.replace("_", "-")
        if field.name == "calibration_roi":
            parser.add_argument(key, nargs=4, type=float, default=None, metavar=("X", "Y", "WIDTH", "HEIGHT"))
        elif type(value) is bool:
            parser.add_argument(key, action=argparse.BooleanOptionalAction, default=None)
        else:
            parser.add_argument(key, type=type(value), default=None)
    args, ros_args = parser.parse_known_args(argv)
    if ros_args and (not args.ros or ros_args[0] != "--ros-args"):
        parser.error("unrecognized arguments: " + " ".join(ros_args))
    data = load_json(args.config) if args.config else {}
    if not isinstance(data, dict) or set(data) - set(asdict(defaults)):
        raise Unavailable("unknown_camera_configuration_fields")
    data.update({field.name: getattr(args, field.name) for field in fields(defaults) if getattr(args, field.name) is not None})
    return CaptureSettings(**data).validate(), args, ros_args
