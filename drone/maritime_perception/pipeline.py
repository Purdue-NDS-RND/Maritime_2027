"""Connect source-neutral measurement events to the actual numerical processing."""
import numpy as np

from .contracts import VehicleState
from .geodesy import GeodeticConverter
from .geometry import CameraCalibration, ImageTransform, PlaneProjector
from .reporting import ReportEncoder
from .timing import ClockMapper, PoseProvider
from .tracking import ObjectTracker
from .uncertainty import ProjectionUncertainty
from .validation import Unavailable, timestamp


class PerceptionPipeline:
    def __init__(self, settings):
        self.settings = settings
        if settings.get("source_mode") not in ("synthetic", "recorded", "hardware", "gazebo"):
            raise Unavailable("explicit_source_mode_required")
        if type(settings.get("synthetic")) is not bool:
            raise Unavailable("explicit_synthetic_provenance_required")
        if settings["source_mode"] in ("synthetic", "gazebo") and not settings["synthetic"]:
            raise Unavailable("synthetic_source_must_be_labeled")
        if settings["source_mode"] == "hardware" and settings["synthetic"]:
            raise Unavailable("synthetic_configuration_forbidden_in_hardware_mode")
        self.clock = ClockMapper(settings["clocks"])
        self.pose = PoseProvider(settings["origin"]["origin_id"], settings["max_pose_gap_s"], settings["pose_history_s"])
        self.tracker = ObjectTracker(settings["tracking"])
        self.geodesy = GeodeticConverter(settings["origin"])
        self.setup_error = None
        try:
            self.calibration = CameraCalibration.from_dict(settings.get("calibration"))
            if settings["source_mode"] == "hardware" and self.calibration.synthetic:
                raise Unavailable("synthetic_calibration_forbidden_in_hardware_mode")
            self.projector = PlaneProjector(self.calibration, settings.get("water_surface"), settings["projection_limits"])
            self.uncertainty = ProjectionUncertainty(self.projector)
        except Unavailable as exc:
            self.setup_error = str(exc)
        water_height = self.projector.height if self.setup_error is None else None
        self.encoder = ReportEncoder(settings, self.geodesy, water_height)
        self.last_frame_ns = -1
        self.revision = 0
        self.frame_ids = set()
        self.pending_diagnostics = []

    def add_state(self, data):
        try:
            state = VehicleState.from_dict(data)
            if state.clock_id != "survey_utc":
                raise Unavailable("state_clock_must_be_mapped_to_survey_utc")
            self.pose.add(state)
        except (Unavailable, KeyError, TypeError, ValueError) as exc:
            self.pending_diagnostics.append({"status": "rejected", "reason": str(exc), "kind": "vehicle_state"})

    def add_imu_state(self, data):
        """Same-time IMU + verified navigation, also supported by recorded replay."""
        from .adapters.imu_formatter import ImuSample
        from .adapters.ros_conversion import imu_to_state
        try:
            sample = ImuSample.from_record(data["imu"])
            self.add_state(imu_to_state(sample, data["navigation"], **data["contract"]))
        except (Unavailable, AttributeError, KeyError, TypeError, ValueError) as exc:
            self.pending_diagnostics.append({"status": "rejected", "reason": str(exc), "kind": "imu_state"})

    def process_frame(self, frame):
        if not isinstance(frame, dict) or not isinstance(frame.get("id"), str) or not frame["id"]:
            raise Unavailable("invalid_frame_id")
        if not isinstance(frame.get("detections"), list):
            raise Unavailable("invalid_detection_batch")
        diagnostics, self.pending_diagnostics = self.pending_diagnostics, []
        observations = []
        # Invalid event times cannot be assigned a plausible substitute epoch.
        stamp_ns, clock = self.clock.at(frame["stamp_ns"], frame["clock_id"])
        published_ns = timestamp(frame["published_ns"])
        if published_ns < stamp_ns:
            raise Unavailable("publication_precedes_exposure")
        if stamp_ns <= self.last_frame_ns or frame["id"] in self.frame_ids:
            raise Unavailable("duplicate_or_out_of_sequence_frame")
        self.last_frame_ns = stamp_ns
        self.frame_ids.add(frame["id"])
        try:
            if self.setup_error:
                raise Unavailable(self.setup_error)
            if frame.get("stamp_semantics") != "exposure_midpoint":
                raise Unavailable("exposure_time_unavailable")
            if frame.get("origin_id") != self.settings["origin"]["origin_id"]:
                raise Unavailable("frame_origin_mismatch")
            transform = ImageTransform(frame, self.calibration)
            pose = self.pose.at(stamp_ns)
            seen = set()
            for detection in frame["detections"]:
                if not isinstance(detection, dict):
                    diagnostics.append({"status": "rejected", "reason": "invalid_detection", "kind": "projection"})
                    continue
                try:
                    if not isinstance(detection.get("id"), str) or not detection["id"] or detection["id"] in seen:
                        raise Unavailable("invalid_or_duplicate_detection_id")
                    seen.add(detection["id"])
                    if not isinstance(detection.get("class_id"), str) or not detection["class_id"]:
                        raise Unavailable("invalid_class_id")
                    if detection.get("reference_method") != "water_centre":
                        raise Unavailable("unvalidated_target_reference")
                    pixel, cov = transform.to_source(detection["pixel_uv"], detection.get("pixel_covariance"))
                    if np.any(pixel < 0) or np.any(pixel >= [self.calibration.width, self.calibration.height]):
                        raise Unavailable("pixel_outside_calibrated_image")
                    observations.append(self.uncertainty.propagate(pixel, cov, pose, frame, detection, clock))
                except (Unavailable, KeyError, TypeError, ValueError) as exc:
                    diagnostics.append({"detection_id": detection.get("id", "unknown"), "status": "rejected", "reason": str(exc), "kind": "projection"})
        except (Unavailable, KeyError, TypeError, ValueError) as exc:
            diagnostics.append({"status": "rejected", "reason": str(exc), "kind": "frame", "frame_id": frame["id"]})
        decisions = self.tracker.step(stamp_ns, observations)
        diagnostics.extend(decisions)
        self.revision += 1
        report = self.encoder.encode(self.tracker, stamp_ns, published_ns, self.revision, diagnostics)
        ledger = [{"detection_id": observation.detection_id, "frame_id": observation.frame_id,
                   "stamp_ns": observation.stamp_ns, "mean_en_m": observation.mean.tolist(),
                   "independent_covariance_en_m2": observation.independent_cov.tolist(),
                   "absolute_covariance_en_m2": observation.covariance.tolist(),
                   "shared_factors": {key: factor.tolist() for key, factor in sorted(observation.factors.items())}}
                  for observation in observations]
        return report, ledger
