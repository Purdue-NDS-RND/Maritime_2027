"""Fail-closed MAVROS graph and telemetry contract checks."""

import math


PUBLIC_TOPICS = {
    "/mavros/state": "mavros_msgs/msg/State",
    "/mavros/imu/data": "sensor_msgs/msg/Imu",
    "/mavros/local_position/odom": "nav_msgs/msg/Odometry",
    "/mavros/global_position/global": "sensor_msgs/msg/NavSatFix",
    "/mavros/global_position/compass_hdg": "std_msgs/msg/Float64",
    "/mavros/battery": "sensor_msgs/msg/BatteryState",
    "/mavros/extended_state": "mavros_msgs/msg/ExtendedState",
    "/mavros/sys_status": "mavros_msgs/msg/SysStatus",
    "/mavros/statustext/recv": "mavros_msgs/msg/StatusText",
    "/mavros/status_event": "mavros_msgs/msg/StatusEvent",
    "/mavros/time_reference": "sensor_msgs/msg/TimeReference",
    "/mavros/timesync_status": "mavros_msgs/msg/TimesyncStatus",
}
PUBLIC_SERVICES = {
    "/mavros/cmd/arming": "mavros_msgs/srv/CommandBool",
    "/mavros/set_mode": "mavros_msgs/srv/SetMode",
    "/mavros/cmd/command": "mavros_msgs/srv/CommandLong",
    "/mavros/cmd/command_int": "mavros_msgs/srv/CommandInt",
}

PLUGIN_ALLOWLIST = [
    "adsb", "cam_imu_sync", "camera", "cellular_status", "command",
    "companion_process_status", "distance_sensor", "esc_status", "esc_telemetry",
    "fake_gps", "geofence", "gimbal_control", "global_position", "gps_input",
    "gps_rtk", "gps_status", "guided_target", "home_position", "imu",
    "landing_target", "local_position", "log_transfer", "mag_calibration_status",
    "manual_control", "mocap_pose_estimate", "mount_control", "nav_controller_output",
    "obstacle_distance", "obstacle_distance_3d", "odometry", "onboard_computer_status",
    "open_drone_id", "optical_flow", "param", "play_tune", "rallypoint",
    "rangefinder", "rc_io", "setpoint_accel", "setpoint_attitude", "setpoint_position",
    "setpoint_raw", "setpoint_trajectory", "setpoint_velocity", "sim_state",
    "sys_status", "sys_time", "tdr_radio", "terrain", "trajectory", "tunnel",
    "vfr_hud", "vision_pose", "vision_speed", "waypoint", "wind_estimation",
]
PLUGIN_DENYLIST = [
    "actuator_control", "altitude", "debug_value", "ftp", "hil", "px4flow",
    "vibration", "wheel_odometry",
]


def stamp_ns(message):
    return message.header.stamp.sec * 1_000_000_000 + message.header.stamp.nanosec


def finite(values):
    return all(math.isfinite(value) for value in values)


def validate_imu(message):
    if stamp_ns(message) <= 0 or message.header.frame_id != "base_link":
        return False
    vectors = (
        message.orientation.x, message.orientation.y, message.orientation.z, message.orientation.w,
        message.angular_velocity.x, message.angular_velocity.y, message.angular_velocity.z,
        message.linear_acceleration.x, message.linear_acceleration.y, message.linear_acceleration.z,
        *message.orientation_covariance, *message.angular_velocity_covariance,
        *message.linear_acceleration_covariance,
    )
    return finite(vectors) and all(covariance[0] >= 0 for covariance in (
        message.orientation_covariance, message.angular_velocity_covariance,
        message.linear_acceleration_covariance,
    ))


def validate_odom(message):
    if stamp_ns(message) <= 0 or message.header.frame_id != "map" or message.child_frame_id != "base_link":
        return False
    pose, twist = message.pose.pose, message.twist.twist
    values = (
        pose.position.x, pose.position.y, pose.position.z,
        pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w,
        twist.linear.x, twist.linear.y, twist.linear.z,
        twist.angular.x, twist.angular.y, twist.angular.z,
        *message.pose.covariance, *message.twist.covariance,
    )
    return finite(values) and message.pose.covariance[0] >= 0 and message.twist.covariance[0] >= 0


def validate_fix(message):
    return (
        stamp_ns(message) > 0
        and message.status.status >= 0
        and finite((message.latitude, message.longitude, message.altitude, *message.position_covariance))
        and message.position_covariance_type != 0
    )


def validate_graph(topic_names, service_names):
    for name, expected in PUBLIC_TOPICS.items():
        if topic_names.get(name) != [expected]:
            return False, f"topic_contract_mismatch:{name}"
    for name, expected in PUBLIC_SERVICES.items():
        if service_names.get(name) != [expected]:
            return False, f"service_contract_mismatch:{name}"
    return True, "ready"


def parameter_mismatches(expected, observed):
    return [name for name, value in expected.items() if observed.get(name) != value]
