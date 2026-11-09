"""Startup-only transport settings, independent of mission planning state."""
from dataclasses import asdict, dataclass, field
import os
from urllib.parse import urlsplit

from .telemetry import TelemetryConfig


@dataclass(frozen=True)
class Connections:
    boat_url: str = 'http://127.0.0.1:8091'
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)

    def __post_init__(self):
        value = urlsplit(self.boat_url)
        if (value.scheme not in ('http', 'https') or not value.hostname
                or value.username is not None or value.password is not None
                or value.path not in ('', '/') or value.query or value.fragment
                or any(character.isspace() or ord(character) < 32 for character in self.boat_url)):
            raise ValueError('GCS_BOAT_URL must be an http(s)://HOST[:PORT] origin without credentials or a path')
        if value.port is not None and not 1 <= value.port <= 65535:
            raise ValueError('GCS_BOAT_URL port must be in 1..65535')
        object.__setattr__(self, 'boat_url', self.boat_url.rstrip('/'))

    @classmethod
    def from_env(cls):
        return cls(boat_url=os.getenv('GCS_BOAT_URL', cls.boat_url),
                   telemetry=TelemetryConfig.from_env())

    def snapshot(self):
        return asdict(self)
