"""Deterministic bounded RGB-D matching and diagnostic evidence state."""

from collections import OrderedDict
from dataclasses import dataclass

from .camera_contract import (
    MAX_ACQUISITION_AGE_NS,
    MAX_ARRIVAL_SILENCE_NS,
    freshness,
    stamp_ns,
    validate_camera_info,
    validate_image,
)


@dataclass
class Record:
    stamp: int
    arrival: int
    message: object


class CameraReadinessModel:
    def __init__(self, queue_limit=64):
        self.queue_limit = queue_limit
        self.queues = {name: OrderedDict() for name in ("color", "depth", "info")}
        self.latest = {name: None for name in self.queues}
        self.last_seen_stamp = {name: 0 for name in self.queues}
        self.last_arrival = {name: 0 for name in self.queues}
        self.errors = {}
        self.last_triple = None
        self.observed_skew_ns = None
        self.rejected_count = 0
        self.unmatched_count = 0
        self.overflow_count = 0

    def ingest(self, stream, message, ros_now_ns, steady_now_ns):
        stamp = stamp_ns(message)
        if stamp <= 0 or stamp <= self.last_seen_stamp[stream]:
            return self._reject(stream, "nonmonotonic_header_stamp")
        if stamp > ros_now_ns:
            return self._reject(stream, "future_acquisition_stamp")
        if steady_now_ns < self.last_arrival[stream]:
            return self._reject(stream, "steady_clock_regression")
        error = validate_camera_info(message) if stream == "info" else validate_image(message, depth=stream == "depth")
        if error:
            return self._reject(stream, error)
        self.last_seen_stamp[stream] = stamp
        self.last_arrival[stream] = steady_now_ns
        record = Record(stamp, steady_now_ns, message)
        self.latest[stream] = record
        queue = self.queues[stream]
        queue[stamp] = record
        if len(queue) > self.queue_limit:
            queue.popitem(last=False)
            self.overflow_count += 1
            self.errors["synchronization"] = "queue_overflow"
        self._match(ros_now_ns)
        return True

    def _reject(self, component, reason):
        self.rejected_count += 1
        self.errors[component] = reason
        return False

    def _match(self, ros_now_ns):
        colors, depths, infos = self.queues["color"], self.queues["depth"], self.queues["info"]
        while colors:
            color_stamp = next(iter(colors))
            for queue in (depths, infos):
                while queue and next(iter(queue)) < color_stamp:
                    queue.popitem(last=False)
                    self.unmatched_count += 1
                    self.errors["synchronization"] = "unmatched_data"
            depth = depths.get(color_stamp)
            info = infos.get(color_stamp)
            if depth is None or info is None:
                depth_advanced = depths and next(reversed(depths)) > color_stamp
                info_advanced = infos and next(reversed(infos)) > color_stamp
                expired = ros_now_ns - color_stamp > MAX_ACQUISITION_AGE_NS
                if depth_advanced or info_advanced or expired:
                    colors.popitem(last=False)
                    self.unmatched_count += 1
                    self.errors["synchronization"] = "unmatched_data"
                    continue
                break
            color = colors[color_stamp]
            self.observed_skew_ns = abs(depth.stamp - color.stamp)
            same_dimensions = (
                color.message.width == depth.message.width == info.message.width
                and color.message.height == depth.message.height == info.message.height
            )
            if not same_dimensions:
                self._reject("registration", "invalid_dimensions")
            else:
                self.last_triple = (color, depth, info)
                # Recovery is evidence-driven: only a new conforming triple
                # clears prior content, matching, or overflow failures.
                self.errors.clear()
            del colors[color_stamp]
            del depths[color_stamp]
            del infos[color_stamp]

    def _stream_state(self, stream, ros_now_ns, steady_now_ns):
        if stream in self.errors:
            return "ERROR", self.errors[stream]
        record = self.latest[stream]
        if record is None:
            return "STALE", "unobserved"
        return freshness(record.stamp, record.arrival, ros_now_ns, steady_now_ns)

    def snapshot(self, ros_now_ns, steady_now_ns):
        self._match(ros_now_ns)
        states = {stream: self._stream_state(stream, ros_now_ns, steady_now_ns) for stream in self.queues}
        if "frames" in self.errors:
            frames = ("ERROR", self.errors["frames"])
        elif any(reason == "frame_mismatch" for reason in self.errors.values()):
            frames = ("ERROR", "frame_mismatch")
        else:
            frames = ("OK", "ready") if self.last_triple else ("STALE", "unobserved")
        calibration = states["info"]
        if "registration" in self.errors:
            registration = ("ERROR", self.errors["registration"])
        else:
            registration = ("OK", "ready") if self.last_triple else ("STALE", "unobserved")
        if "synchronization" in self.errors:
            synchronization = ("ERROR", self.errors["synchronization"])
        elif self.last_triple is None:
            synchronization = ("STALE", "unobserved")
        else:
            triple_state = freshness(self.last_triple[0].stamp, self.last_triple[0].arrival, ros_now_ns, steady_now_ns)
            synchronization = triple_state
        components = {
            "color": states["color"], "depth": states["depth"],
            "calibration": calibration, "registration": registration,
            "synchronization": synchronization, "frames": frames,
        }
        severity = {"OK": 0, "STALE": 1, "ERROR": 2}
        aggregate = max(components.values(), key=lambda item: severity[item[0]])
        components["source_readiness"] = aggregate
        evidence = {
            "color_header_stamp_ns": self.latest["color"].stamp if self.latest["color"] else "unobserved",
            "depth_header_stamp_ns": self.latest["depth"].stamp if self.latest["depth"] else "unobserved",
            "camera_info_header_stamp_ns": self.latest["info"].stamp if self.latest["info"] else "unobserved",
            "color_arrival_silence_ns": steady_now_ns - self.latest["color"].arrival if self.latest["color"] else "unobserved",
            "depth_arrival_silence_ns": steady_now_ns - self.latest["depth"].arrival if self.latest["depth"] else "unobserved",
            "camera_info_arrival_silence_ns": steady_now_ns - self.latest["info"].arrival if self.latest["info"] else "unobserved",
            "rgb_depth_skew_ns": self.observed_skew_ns if self.observed_skew_ns is not None else "unobserved",
            "rejected_count": self.rejected_count,
            "unmatched_count": self.unmatched_count,
            "overflow_count": self.overflow_count,
        }
        return components, evidence
