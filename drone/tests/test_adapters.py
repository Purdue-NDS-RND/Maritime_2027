from types import SimpleNamespace as NS

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from maritime_perception.adapters.ros_conversion import detections_to_frame, odometry_to_state
from maritime_perception.adapters.ultralytics_detector import UltralyticsDetector
from maritime_perception.contracts import VehicleState
from maritime_perception.validation import Unavailable


def xyz(x=0., y=0., z=0.):
    return NS(x=x, y=y, z=z)


def test_odometry_message_contract_and_body_velocity_conversion():
    q = Rotation.from_euler("z", 90, degrees=True).as_quat()
    message = NS(header=NS(frame_id="survey_enu", stamp=NS(sec=10, nanosec=7)), child_frame_id="drone_base_link",
                 pose=NS(pose=NS(position=xyz(0, 0, 4), orientation=NS(x=q[0], y=q[1], z=q[2], w=q[3])), covariance=np.eye(6).reshape(-1)),
                 twist=NS(twist=NS(linear=xyz(1), angular=xyz(0, 0, .1))))
    kwargs = dict(origin_id="origin", epoch_id="epoch", shared_model_id="gps",
                  shared_covariance=np.eye(6)*.5, quality={"position_valid": True, "heading_valid": True, "height_valid": True})
    with pytest.raises(Unavailable, match="unverified"):
        odometry_to_state(message, **kwargs)
    with pytest.raises(Unavailable, match="decomposition_unverified"):
        odometry_to_state(message, **kwargs, conventions_verified=True)
    state = VehicleState.from_dict(odometry_to_state(message, **kwargs, conventions_verified=True, covariance_decomposition_verified=True))
    np.testing.assert_allclose(state.velocity, [0, 1, 0], atol=1e-12)
    np.testing.assert_allclose(state.sample_cov+state.shared_cov, np.eye(6))
    assert state.stamp_ns == 10_000_000_007 and state.position_reference == "body"


def test_detection_converter_preserves_exposure_stamp_and_reference_policy(events):
    frame = next(e["data"] for e in events if e["kind"] == "frame")
    detection = NS(results=[NS(hypothesis=NS(score=.9, class_id="buoy"))], bbox=NS(center=NS(position=NS(x=640., y=480.))))
    sec, ns = divmod(frame["stamp_ns"], 1_000_000_000)
    message = NS(header=NS(stamp=NS(sec=sec, nanosec=ns)), detections=[detection])
    result = detections_to_frame(message, frame, pixel_sigma_px=1., reference_method="bbox_centre_unvalidated")
    assert result["stamp_ns"] == frame["stamp_ns"]
    assert result["detections"][0]["reference_method"] == "bbox_centre_unvalidated"


def test_detector_missing_weights_is_unavailable_without_download_or_fallback(tmp_path):
    with pytest.raises(Unavailable, match="detector_weights_unavailable"):
        UltralyticsDetector(tmp_path/"not_available.pt", {0: "buoy"})
