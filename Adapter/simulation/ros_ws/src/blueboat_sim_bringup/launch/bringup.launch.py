"""One fail-fast launch chain for every required Simulation Adapter process."""

import os
import tempfile
import yaml
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, Shutdown
from launch.substitutions import EnvironmentVariable, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

from blueboat_sim_bringup.manifest import load_manifest, truth_bridge_arguments


def required_node(**kwargs):
    name = kwargs.get("name", kwargs["executable"])
    return Node(**kwargs, on_exit=Shutdown(reason=f"required Adapter child exited: {name}"))


def static_transform(name, arguments, truth=False):
    remappings = [("/tf_static", "/blueboat/ground_truth/tf_static")] if truth else []
    return required_node(
        package="tf2_ros", executable="static_transform_publisher", name=name,
        output="screen", arguments=arguments, remappings=remappings,
    )


def camera_bridge_config(camera, stream, topic, suffix, message, gz_message, frame):
    # Unique launch-owned files keep explicit SENSOR_DATA QoS on large images.
    with tempfile.NamedTemporaryFile(mode="w", prefix=f"{camera}_{stream}_", suffix=".yaml", delete=False) as output:
        yaml.safe_dump([{
            "ros_topic_name": f"/adapter/private/{camera}/{stream}",
            "gz_topic_name": f"{topic}/{suffix}",
            "ros_type_name": f"sensor_msgs/msg/{message}", "gz_type_name": f"gz.msgs.{gz_message}",
            "direction": "GZ_TO_ROS", "qos_profile": "SENSOR_DATA", "frame_id": frame,
        }], output)
        return output.name


def generate_launch_description():
    package_share = Path(get_package_share_directory("blueboat_sim_bringup"))
    manifest_path = os.environ.get("SCENARIO_MANIFEST", "/scenario/active.manifest.json")
    manifest = load_manifest(manifest_path)
    fcu_url = LaunchConfiguration("fcu_url")
    actions = [
        DeclareLaunchArgument(
            "fcu_url", default_value=EnvironmentVariable("FCU_URL", default_value="udp://:14552@"),
            description="Simulation Adapter-owned SITL endpoint",
        ),
        required_node(
            package="ros_gz_bridge", executable="parameter_bridge", name="blueboat_gz_bridge", output="screen",
            parameters=[{"config_file": str(package_share / "config" / "bridge.yaml")}],
        ),
        required_node(
            package="blueboat_mavlink_monitor", executable="mavlink_v2_monitor", name="mavlink_v2_monitor", output="screen",
        ),
        required_node(
            # Keep the executable's three default owners unique: loader, router,
            # and UAS. A global name remap would rename all three to /mavros.
            package="mavros", executable="mavros_node", namespace="/", output="screen",
            parameters=[str(package_share / "config" / "mavros.yaml"), {"fcu_url": ParameterValue(fcu_url, value_type=str)}],
        ),
        required_node(
            package="blueboat_sim_bringup", executable="configure_mavros", name="mavros_configuration", output="screen",
            parameters=[{"configuration_file": str(package_share / "config" / "mavros.yaml")}],
        ),
        required_node(
            package="blueboat_sim_bringup", executable="diagnostics", name="simulation_adapter_diagnostics", output="screen",
            parameters=[{"use_sim_time": True}],
        ),
        static_transform(
            "world_to_odom",
            ["--x", "0", "--y", "0", "--z", "0", "--roll", "0", "--pitch", "0", "--yaw", "0", "--frame-id", "world", "--child-frame-id", "odom"],
            truth=True,
        ),
    ]
    model = manifest.get("boat_model", "single")
    cameras = ["camera_0", "camera_1"] if model == "dual" else ["camera_0"]
    actions.append(required_node(
        package="blueboat_sim_bringup", executable="camera_roster", name="camera_roster", output="screen",
        parameters=[{"enabled_cameras": cameras}],
    ))
    for index in range(len(cameras)):
        camera = f"camera_{index}"
        topic = "/blueboat/rgbd_camera" if index == 0 else "/blueboat/camera_1"
        private_frame = "zed2i_left_camera_optical_frame" if model == "single" else f"{camera}_optical_frame"
        for stream, suffix, message, gz_message in (
            ("color", "image", "Image", "Image"),
            ("depth", "depth_image", "Image", "Image"),
            ("camera_info", "camera_info", "CameraInfo", "CameraInfo"),
        ):
            actions.append(required_node(
                package="ros_gz_bridge", executable="parameter_bridge",
                name=f"{camera}_{stream}_bridge", output="screen",
                parameters=[{"config_file": camera_bridge_config(camera, stream, topic, suffix, message, gz_message, private_frame)}],
            ))
        actions.append(required_node(
            package="blueboat_camera_adapter", executable="camera_boundary",
            name=f"{camera}_boundary", output="screen", parameters=[{
                "use_sim_time": True, "camera_id": camera, "boat_model": model,
                "registration_mode": "color", "registration_evidence_ref": "simulation-rgbd-registration",
            }],
        ))
        y = 0.0 if model == "single" else (-0.1 if index == 0 else 0.1)
        yaw = 0.0 if model == "single" else (-0.7853981633974483 if index == 0 else 0.7853981633974483)
        actions.extend([
            static_transform(f"base_to_{camera}", [
                "--x", "0.35", "--y", str(y), "--z", "0.40", "--roll", "0", "--pitch", "0", "--yaw", str(yaw),
                "--frame-id", "base_link", "--child-frame-id", f"{camera}_link"]),
            static_transform(f"{camera}_to_optical", [
                "--x", "0", "--y", "0", "--z", "0", "--roll", "-1.5707963267948966", "--pitch", "0", "--yaw", "-1.5707963267948966",
                "--frame-id", f"{camera}_link", "--child-frame-id", f"{camera}_optical_frame"]),
        ])
    for key, ros_topic, bridge_argument in truth_bridge_arguments(manifest):
        gz_topic = bridge_argument.split("@")[0]
        actions.append(required_node(
            package="ros_gz_bridge", executable="parameter_bridge", name=f"truth_bridge_{key}", output="screen",
            arguments=[bridge_argument], remappings=[(gz_topic, ros_topic)],
        ))
    return LaunchDescription(actions)
