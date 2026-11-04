"""Validated JSON boundary, including correlated factors and fixed-ENU semantics."""
import json
from importlib.resources import files

import numpy as np
from jsonschema import Draft202012Validator, FormatChecker

from .uncertainty import ellipse
from .validation import Unavailable, covariance, factors_covariance, parse_utc, utc


class ReportEncoder:
    def __init__(self, settings, geodesy, water_height):
        self.settings = settings
        self.geodesy = geodesy
        self.water_height = water_height
        schema = json.loads(files("maritime_perception").joinpath("schemas/track_report_v1.schema.json").read_text())
        self.validator = Draft202012Validator(schema, format_checker=FormatChecker())

    def encode(self, tracker, stamp_ns, published_ns, revision, diagnostics):
        if published_ns < stamp_ns:
            raise Unavailable("publication_precedes_state")
        tracks = []
        for track in tracker.tracks:
            age = (stamp_ns-track.last_ns)*1e-9
            status = "stale" if age > tracker.stale_s else ("observed" if track.last_ns == stamp_ns else "predicted")
            absolute = track.covariance
            item = {"id": track.track_id, "class_id": track.class_id,
                    "position_enu_m": [float(track.mean[0]), float(track.mean[1]), self.water_height],
                    "position_wgs84": self.geodesy.to_wgs84([*track.mean, self.water_height]),
                    "position_reference": "horizontal_centre_at_water_plane",
                    "state_at": utc(stamp_ns), "last_observed_at": utc(track.last_ns),
                    "first_observed_at": utc(track.first_ns), "age_s": age, "estimate_status": status,
                    "association_status": "ambiguous" if track.ambiguous else ("confirmed" if track.count >= tracker.confirm_hits else "tentative"),
                    "observation_count": track.count, "motion_model": "static_random_walk",
                    "uncertainty": {"covariance_en_m2": absolute.tolist(),
                                    "independent_covariance_en_m2": track.independent_cov.tolist(),
                                    "shared_covariance_en_m2": factors_covariance(track.factors).tolist(),
                                    "shared_factors": {key: value.tolist() for key, value in sorted(track.factors.items())},
                                    "model_id": "linearized_correlated_factors_v1", "coverage_validated": False,
                                    "ellipse_en": ellipse(absolute)},
                    "quality": {"status": "synthetic_only" if self.settings["synthetic"] else "unvalidated",
                                "positioning_mode": "standalone_gnss"}}
            tracks.append(item)
        report = {"schema": "maritime.track_report", "schema_version": 1,
                  "survey_id": self.settings["survey_id"], "revision": revision,
                  "source_mode": self.settings["source_mode"], "synthetic": self.settings["synthetic"],
                  "frame": {"id": "survey_enu", "axes": ["east", "north", "up"], "units": "m",
                            "covariance_units": "m^2", "origin": self.settings["origin"]},
                  "state_at": utc(stamp_ns), "published_at": utc(published_ns),
                  "tracks": tracks, "diagnostics": diagnostics,
                  "processing": {"version": "0.1.0", "calibration_id": self.settings.get("calibration", {}).get("calibration_id") if self.settings.get("calibration") else None,
                                 "projection_backend": "opencv_analytic_plane", "geodesy": "PROJ_WGS84_ECEF_ENU"}}
        self.validate(report)
        return report

    def validate(self, report):
        self.validator.validate(report)
        json.dumps(report, allow_nan=False)
        epoch, published = parse_utc(report["state_at"]), parse_utc(report["published_at"])
        if epoch > published:
            raise Unavailable("publication_precedes_state")
        if len({track["id"] for track in report["tracks"]}) != len(report["tracks"]):
            raise Unavailable("duplicate_track_identity")
        for track in report["tracks"]:
            if track["state_at"] != report["state_at"]:
                raise Unavailable("inconsistent_state_epoch")
            uncertainty = track["uncertainty"]
            absolute = covariance(uncertainty["covariance_en_m2"], 2, positive=True)
            independent = covariance(uncertainty["independent_covariance_en_m2"], 2, positive=True)
            shared = covariance(uncertainty["shared_covariance_en_m2"], 2)
            factors = {key: np.asarray(value) for key, value in uncertainty["shared_factors"].items()}
            if not np.allclose(absolute, independent+shared) or not np.allclose(shared, factors_covariance(factors)):
                raise Unavailable("inconsistent_covariance_components")
            expected = ellipse(absolute)
            if uncertainty["ellipse_en"] != expected:
                raise Unavailable("inconsistent_ellipse")
            point = track["position_wgs84"]
            enu = self.geodesy.to_enu(point["latitude_deg"], point["longitude_deg"], point["ellipsoid_height_m"])
            if not np.allclose(enu, track["position_enu_m"], atol=1e-5, rtol=0):
                raise Unavailable("inconsistent_geodetic_position")
            first, last = parse_utc(track["first_observed_at"]), parse_utc(track["last_observed_at"])
            if not first <= last <= epoch <= published:
                raise Unavailable("inconsistent_report_times")
            if not np.isclose(track["age_s"], (epoch-last)*1e-9, atol=1e-9, rtol=0):
                raise Unavailable("inconsistent_observation_age")
