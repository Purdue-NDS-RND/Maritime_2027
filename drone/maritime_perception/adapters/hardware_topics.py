"""Observed ROS source bindings; topic/frame names do not certify physical conventions."""
from pathlib import Path

from ..validation import Unavailable, load_json


ROLES = {"image", "camera_info", "frame_metadata", "odometry", "imu", "gnss", "gps_origin",
         "fcu_state", "system_status", "timesync", "time_reference", "tf", "tf_static"}
ROLE_TYPES = dict(image="sensor_msgs/msg/Image", camera_info="sensor_msgs/msg/CameraInfo",
    frame_metadata="std_msgs/msg/String", odometry="nav_msgs/msg/Odometry", imu="sensor_msgs/msg/Imu",
    gnss="sensor_msgs/msg/NavSatFix", gps_origin="geographic_msgs/msg/GeoPointStamped",
    fcu_state="mavros_msgs/msg/State", system_status="mavros_msgs/msg/SysStatus",
    timesync="mavros_msgs/msg/TimesyncStatus", time_reference="sensor_msgs/msg/TimeReference",
    tf="tf2_msgs/msg/TFMessage", tf_static="tf2_msgs/msg/TFMessage")


def load_profile(value="builtin:mavros_imx519"):
    if value.startswith("builtin:"):
        if value != "builtin:mavros_imx519":
            raise Unavailable("unknown_hardware_topic_profile")
        path = Path(__file__).parent.parent/"config/mavros_imx519_topics.json"
    else:
        path = Path(value)
    data = load_json(path)
    if (data.get("schema") != "maritime.sensor_topics" or data.get("version") != 1
        or data.get("source_mode") != "hardware" or set(data.get("roles", {})) != ROLES
        or not isinstance(data.get("name"), str) or not data["name"]):
        raise Unavailable("invalid_hardware_topic_profile")
    topics = []
    for role, item in data["roles"].items():
        topic, qos = item.get("topic"), item.get("qos", {})
        if (not isinstance(topic, str) or not topic.startswith("/") or any(c.isspace() for c in topic)
            or item.get("type") != ROLE_TYPES[role] or type(item.get("required")) is not bool
            or type(qos.get("depth")) is not int or not 1 <= qos["depth"] <= 512
            or qos.get("reliability") not in ("best_effort", "reliable")
            or qos.get("durability") not in ("volatile", "transient_local")):
            raise Unavailable("invalid_hardware_topic_binding:" + role)
        topics.append(topic)
    if len(topics) != len(set(topics)) or data["roles"]["image"].get("image_domain") not in ("raw", "rectified"):
        raise Unavailable("ambiguous_hardware_topic_bindings")
    for role in ("image", "camera_info", "odometry", "imu", "gnss", "gps_origin"):
        if not isinstance(data["roles"][role].get("frame_id"), str) or not data["roles"][role]["frame_id"]:
            raise Unavailable("missing_source_frame_label:" + role)
    if (data["roles"]["camera_info"]["frame_id"] != data["roles"]["image"]["frame_id"]
        or not isinstance(data["roles"]["odometry"].get("child_frame_id"), str)
        or not data["roles"]["odometry"]["child_frame_id"]):
        raise Unavailable("inconsistent_source_frame_labels")
    return data


def profile_assessment(profile, topics, *, decoded=True):
    bindings, issues = {}, []
    for role, expected in profile["roles"].items():
        actual = topics.get(expected["topic"], {})
        count = actual.get("count", 0)
        binding = dict(topic=expected["topic"], expected_type=expected["type"], count=count,
                       required=expected["required"], issues=[])
        if count == 0:
            binding["issues"].append("required_topic_empty" if expected["required"] else "optional_topic_empty")
        if actual and actual.get("type") != expected["type"]:
            binding["issues"].append("topic_type_mismatch")
        if decoded and count and expected.get("frame_id") and actual.get("frame_ids") != [expected["frame_id"]]:
            binding["issues"].append("source_frame_mismatch")
        if decoded and count and expected.get("child_frame_id") and actual.get("child_frame_ids") != [expected["child_frame_id"]]:
            binding["issues"].append("source_child_frame_mismatch")
        if actual.get("decode_errors", 0):
            binding["issues"].append("message_decode_or_validation_errors")
        bindings[role] = binding
        issues.extend(dict(role=role, reason=reason) for reason in binding["issues"])
    return dict(name=profile["name"], bindings=bindings, issues=issues, frame_labels_checked=decoded,
        all_required_topics_seen=all(b["count"] > 0 for b in bindings.values() if b["required"]),
        topic_contract_matches=not any(i["reason"] != "optional_topic_empty" for i in issues),
        physical_conventions_verified=False,
        limits="Source frame labels are checked as recorded; map is not automatically survey_enu. Presence/rates do not verify clock, origin/reset, heading, height, mount or covariance.")


def recorder_arguments(profile, output, qos_path=None):
    qos_path = qos_path or Path(__file__).parent.parent/"config/rosbag_qos.yaml"
    return ["ros2", "bag", "record", "-s", "sqlite3", "-o", str(output),
            "--qos-profile-overrides-path", str(qos_path),
            *[item["topic"] for item in profile["roles"].values()]]


def ros_qos(spec):
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
    return QoSProfile(depth=spec["depth"], history=HistoryPolicy.KEEP_LAST,
        reliability=ReliabilityPolicy.BEST_EFFORT if spec["reliability"] == "best_effort" else ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL if spec["durability"] == "transient_local" else DurabilityPolicy.VOLATILE)
