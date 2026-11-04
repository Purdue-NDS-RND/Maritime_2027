"""ROS message conversion without ROS imports; callers verify source conventions."""
import numpy as np

from ..validation import Unavailable, covariance, rotation


def ros_stamp_ns(stamp):
    if not 0 <= stamp.nanosec < 1_000_000_000:
        raise Unavailable("invalid_ros_timestamp")
    return int(stamp.sec)*1_000_000_000+int(stamp.nanosec)


def xyz(value):
    return [float(value.x), float(value.y), float(value.z)]


def odometry_to_state(message, *, origin_id, epoch_id, shared_model_id,
                      shared_covariance, quality, conventions_verified=False,
                      covariance_decomposition_verified=False):
    if not conventions_verified or message.header.frame_id != "survey_enu" or message.child_frame_id != "drone_base_link":
        raise Unavailable("odometry_frame_contract_unverified")
    if not covariance_decomposition_verified:
        raise Unavailable("odometry_covariance_decomposition_unverified")
    total_cov = covariance(np.asarray(message.pose.covariance).reshape(6, 6), 6)
    if not np.any(total_cov):
        raise Unavailable("odometry_covariance_unknown")
    shared_cov = covariance(shared_covariance, 6)
    residual_cov = covariance(total_cov-shared_cov, 6, "residual_pose_covariance")
    pose, twist = message.pose.pose, message.twist.twist
    q = [pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w]
    attitude = rotation(q)
    return {"stamp_ns": ros_stamp_ns(message.header.stamp), "frame_id": "survey_enu", "body_frame": "FLU",
            "origin_id": origin_id, "epoch_id": epoch_id, "clock_id": "survey_utc", "position_reference": "body",
            "position_enu_m": xyz(pose.position), "quaternion_xyzw": q,
            "velocity_enu_m_s": attitude.apply(xyz(twist.linear)).tolist(),
            "angular_velocity_enu_rad_s": attitude.apply(xyz(twist.angular)).tolist(),
            "sample_pose_covariance": residual_cov.tolist(),
            "shared_pose_covariance": shared_cov.tolist(),
            "shared_model_id": shared_model_id, "quality": quality}


def detections_to_frame(message, metadata, *, pixel_sigma_px, reference_method):
    """Box centres are an unvalidated reference unless the caller proves otherwise."""
    if not np.isfinite(pixel_sigma_px) or pixel_sigma_px <= 0:
        raise Unavailable("pixel_uncertainty_required")
    stamp = ros_stamp_ns(message.header.stamp)
    frame = dict(metadata, stamp_ns=stamp)
    frame["detections"] = []
    for index, detection in enumerate(message.detections):
        if not detection.results:
            raise Unavailable("missing_detection_hypothesis")
        hypothesis = max(detection.results, key=lambda item: item.hypothesis.score).hypothesis
        frame["detections"].append({"id": f"{frame['id']}_d{index}", "class_id": str(hypothesis.class_id),
                                     "pixel_uv": [detection.bbox.center.position.x, detection.bbox.center.position.y],
                                     "pixel_covariance": (np.eye(2)*pixel_sigma_px**2).tolist(),
                                     "reference_method": reference_method})
    return frame
