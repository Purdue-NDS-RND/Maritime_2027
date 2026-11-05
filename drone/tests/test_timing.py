from copy import deepcopy

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from maritime_perception.contracts import VehicleState
from maritime_perception.timing import ClockMapper, PoseProvider
from maritime_perception.validation import Unavailable


def states(events):
    return [VehicleState.from_dict(e["data"]) for e in events if e["kind"] == "vehicle_state"]


def test_pose_interpolation_and_shortest_yaw_path(settings, events):
    from dataclasses import replace
    a, b = states(events)[:2]
    a = replace(a, position=np.array([0., 0., 4.]), attitude=Rotation.from_euler("z", 179, degrees=True))
    b = replace(b, position=np.array([2., 0., 4.]), attitude=Rotation.from_euler("z", -179, degrees=True))
    provider = PoseProvider(a.origin_id, .2)
    provider.add(a)
    provider.add(b)
    middle = provider.at((a.stamp_ns+b.stamp_ns)//2)
    np.testing.assert_allclose(middle.position, [1, 0, 4])
    np.testing.assert_allclose(middle.attitude.apply([1, 0, 0]), [-1, 0, 0], atol=1e-12)


def test_missing_brackets_and_gap(events):
    samples = states(events)
    provider = PoseProvider(samples[0].origin_id, .05)
    with pytest.raises(Unavailable, match="pose_not_bracketed"):
        provider.at(samples[0].stamp_ns)
    provider.add(samples[0])
    provider.add(samples[1])
    with pytest.raises(Unavailable, match="pose_gap_exceeded"):
        provider.at((samples[0].stamp_ns+samples[1].stamp_ns)//2)
    with pytest.raises(Unavailable, match="pose_not_bracketed"):
        provider.at(samples[1].stamp_ns+1)


def test_origin_and_epoch_reset(events):
    from dataclasses import replace
    a, b = states(events)[:2]
    provider = PoseProvider(a.origin_id, .2)
    provider.add(a)
    with pytest.raises(Unavailable, match="pose_reset_requires_new_session"):
        provider.add(replace(b, epoch_id="reset"))
    provider.add(replace(b, origin_id="other_origin"))
    with pytest.raises(Unavailable, match="origin_mismatch"):
        provider.at(b.stamp_ns)


def test_shared_pose_covariance_cannot_change_under_same_id(events):
    from dataclasses import replace
    a, b = states(events)[:2]
    provider = PoseProvider(a.origin_id, .2)
    provider.add(a)
    with pytest.raises(Unavailable, match="shared_model_changed"):
        provider.add(replace(b, shared_cov=np.eye(6)))


def test_interpolation_preserves_shared_and_endpoint_error_factors(events):
    from dataclasses import replace
    a, b = states(events)[:2]
    sample = np.diag([.04, .04, .04, 1e-6, 1e-6, 1e-6])
    common = np.diag([4., 4., 0., 0., 0., 1e-6])
    a, b = replace(a, sample_cov=sample, shared_cov=common), replace(b, sample_cov=sample, shared_cov=common)
    provider = PoseProvider(a.origin_id, .2)
    provider.add(a)
    provider.add(b)
    estimate = provider.at((a.stamp_ns+b.stamp_ns)//2)
    shared_factor = estimate.factors["navigation:"+a.shared_id]
    np.testing.assert_allclose(shared_factor @ shared_factor.T, common, atol=1e-12)
    sampled = sum(factor @ factor.T for key, factor in estimate.factors.items() if key.startswith("pose_sample:"))
    np.testing.assert_allclose(sampled, sample*.5, atol=1e-12)


def test_clock_offset_drift_and_unknown(settings):
    mapping = settings["clocks"]["survey_utc"]
    mapping.update(offset_ns=10_000_000, drift_ppm=20)
    clock = ClockMapper(settings["clocks"])
    stamp = mapping["reference_ns"]+1_000_000_000
    assert clock.at(stamp, "survey_utc")[0] == stamp+10_020_000
    with pytest.raises(Unavailable, match="unmapped_clock"):
        clock.at(stamp, "camera_unknown")


@pytest.mark.parametrize("field,value,reason", [("quaternion_xyzw", [0, 0, 0, 0], "invalid_quaternion"),
    ("sample_pose_covariance", None, "unknown_pose_covariance"),
    ("position_enu_m", [float('nan'), 0, 4], "invalid_position")])
def test_invalid_state_input(events, field, value, reason):
    data = deepcopy(next(e["data"] for e in events if e["kind"] == "vehicle_state"))
    data[field] = value
    with pytest.raises(Unavailable, match=reason):
        VehicleState.from_dict(data)
