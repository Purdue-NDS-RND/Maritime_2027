"""Boundary validation and first-order covariance factors."""
import json
import re
from datetime import datetime, timezone

import numpy as np
from scipy.spatial.transform import Rotation


class Unavailable(ValueError):
    """An explicit machine-readable reason a measurement cannot be used."""


def array(value, shape, name):
    try:
        result = np.asarray(value, dtype=float)
    except (ValueError, TypeError) as exc:
        raise Unavailable("invalid_" + name) from exc
    if result.shape != shape or not np.isfinite(result).all():
        raise Unavailable("invalid_" + name)
    return result.copy()


def covariance(value, size, name="covariance", positive=False):
    if value is None:
        raise Unavailable("unknown_" + name)
    result = array(value, (size, size), name)
    if not np.allclose(result, result.T, atol=1e-10, rtol=1e-10):
        raise Unavailable("asymmetric_" + name)
    eigenvalues = np.linalg.eigvalsh(result)
    if eigenvalues[0] < -1e-10 or (positive and eigenvalues[0] <= 0):
        raise Unavailable("nonpositive_" + name)
    return (result + result.T) / 2


def root_cov(value):
    """Fixed column basis: symmetric PSD square root, retaining zero columns."""
    values, vectors = np.linalg.eigh(value)
    return (vectors * np.sqrt(np.maximum(values, 0))) @ vectors.T


def rotation(quaternion):
    q = array(quaternion, (4,), "quaternion")
    if abs(np.linalg.norm(q) - 1) > 1e-5:
        raise Unavailable("invalid_quaternion")
    return Rotation.from_quat(q)


def timestamp(value):
    if type(value) is not int or not 0 <= value <= 8_000_000_000_000_000_000:
        raise Unavailable("invalid_timestamp")
    return value


def utc(stamp_ns):
    seconds, nanos = divmod(timestamp(stamp_ns), 1_000_000_000)
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + f".{nanos:09d}Z"


def parse_utc(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{9}Z", value):
        raise Unavailable("noncanonical_report_timestamp")
    try:
        seconds = int(datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp())
    except ValueError as exc:
        raise Unavailable("invalid_report_timestamp") from exc
    return timestamp(seconds*1_000_000_000+int(value[20:29]))


def finite_nonnegative(value, name):
    if isinstance(value, bool) or not np.isscalar(value) or not np.isfinite(value) or value < 0:
        raise Unavailable("invalid_" + name)
    return float(value)


def load_json(path):
    with open(path) as stream:
        return json.load(stream, parse_constant=lambda value: (_ for _ in ()).throw(Unavailable("nonfinite_json")))


def factors_covariance(factors):
    return sum((factors[key] @ factors[key].T for key in sorted(factors)), start=np.zeros((2, 2)))


def difference_factors(left, right):
    result = {}
    for key in sorted(left.keys() | right.keys()):
        template = left.get(key, right.get(key))
        result[key] = left.get(key, np.zeros_like(template))-right.get(key, np.zeros_like(template))
    return result
