"""Local mission input. This is deliberately separate from an object map."""

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path


def number(value, name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be finite and in [{minimum}, {maximum}]")
    return float(value)


def fields(value, names, label):
    if not isinstance(value, dict) or set(value) != set(names):
        raise ValueError(f"{label} requires exactly: {', '.join(names)}")


@dataclass(frozen=True)
class Point:
    latitude: float
    longitude: float

    @classmethod
    def parse(cls, data):
        fields(data, ("latitude", "longitude"), "waypoint")
        return cls(number(data["latitude"], "latitude", -90, 90),
                   number(data["longitude"], "longitude", -180, 180))


def distance_m(first, second):
    lat1, lat2 = map(math.radians, (first.latitude, second.latitude))
    dlon = math.radians(second.longitude - first.longitude)
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, a))))


@dataclass(frozen=True)
class Mission:
    mission_id: str
    speed_m_s: float
    waypoints: tuple
    finish_radius_m: float
    finish_speed_m_s: float
    finish_settle_s: float
    timeout_s: float
    max_start_distance_m: float

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text())
        return cls.parse(data)

    @classmethod
    def parse(cls, data):
        names = tuple(cls.__dataclass_fields__)
        fields(data, names, "mission")
        if not isinstance(data["mission_id"], str) or not data["mission_id"].strip():
            raise ValueError("mission_id must be a nonempty string")
        points = data["waypoints"]
        if not isinstance(points, list) or not 1 <= len(points) <= 500:
            raise ValueError("waypoints must contain 1..500 GPS positions")
        return cls(
            data["mission_id"], number(data["speed_m_s"], "speed_m_s", 0.1, 5),
            tuple(Point.parse(point) for point in points),
            number(data["finish_radius_m"], "finish_radius_m", 0.1, 100),
            number(data["finish_speed_m_s"], "finish_speed_m_s", 0.01, 1),
            number(data["finish_settle_s"], "finish_settle_s", 1, 120),
            number(data["timeout_s"], "timeout_s", 10, 7200),
            number(data["max_start_distance_m"], "max_start_distance_m", 0.1, 100),
        )

    def as_dict(self):
        data = asdict(self)
        data["waypoints"] = list(data["waypoints"])
        return data

    @property
    def sha256(self):
        return hashlib.sha256(json.dumps(self.as_dict(), sort_keys=True).encode()).hexdigest()
