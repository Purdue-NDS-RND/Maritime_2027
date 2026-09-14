"""One fail-fast launch chain for every required Simulation Adapter process."""

import os
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
            package="ros_gz_bridge", executable="parameter_bridge", name="blueboat_rgb_bridge", output="screen",
            parameters=[{"config_file": str(package_share / "config" / "bridge_rgb.yaml")}],
        ),
        required_node(
            package="ros_gz_bridge", executable="parameter_bridge", name="blueboat_depth_bridge", output="screen",
            parameters=[{"config_file": str(package_share / "config" / "bridge_depth.yaml")}],
        ),
        required_node(
            package="blueboat_camera_adapter", executable="camera_boundary", name="camera_0_boundary", output="screen",
            parameters=[{
                "use_sim_time": True,
                "registration_mode": "color",
                "registration_evidence_ref": "simulation-rgbd-registration",
            }],
        ),
        required_node(
            package="mavros", executable="mavros_node", name="mavros", namespace="/", output="screen",
            parameters=[str(package_share / "config" / "mavros.yaml"), {"fcu_url": ParameterValue(fcu_url, value_type=str)}],
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
        static_transform(
            "base_to_camera_0",
            ["--x", "0.35", "--y", "0", "--z", "0.40", "--roll", "0", "--pitch", "0", "--yaw", "0", "--frame-id", "base_link", "--child-frame-id", "camera_0_link"],
        ),
        static_transform(
            "camera_0_to_optical",
            ["--x", "0", "--y", "0", "--z", "0", "--roll", "-1.5707963267948966", "--pitch", "0", "--yaw", "-1.5707963267948966", "--frame-id", "camera_0_link", "--child-frame-id", "camera_0_optical_frame"],
        ),
    ]
    for key, ros_topic, bridge_argument in truth_bridge_arguments(manifest):
        gz_topic = bridge_argument.split("@")[0]
        actions.append(required_node(
            package="ros_gz_bridge", executable="parameter_bridge", name=f"truth_bridge_{key}", output="screen",
            arguments=[bridge_argument], remappings=[(gz_topic, ros_topic)],
        ))
    return LaunchDescription(actions)
