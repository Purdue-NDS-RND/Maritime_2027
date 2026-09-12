"""The same MAVROS node connects to SITL or a physical FCU; no Gazebo imports."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription
from launch.launch_description_sources import AnyLaunchDescriptionSource
from launch.substitutions import EnvironmentVariable, LaunchConfiguration
from launch_ros.actions import SetParameter


def generate_launch_description():
    mavros_share = Path(get_package_share_directory("mavros"))
    return LaunchDescription([
        DeclareLaunchArgument("fcu_url", default_value=EnvironmentVariable("FCU_URL")),
        GroupAction(actions=[
            # Preserve the existing ArduPilot SYSID_MYGCS source identity.
            SetParameter(name="system_id", value=255),
            IncludeLaunchDescription(
                AnyLaunchDescriptionSource(str(mavros_share / "launch" / "apm.launch")),
                launch_arguments={
                    "fcu_url": LaunchConfiguration("fcu_url"),
                    "gcs_url": "",
                    "tgt_system": "1",
                    "tgt_component": "1",
                    "fcu_protocol": "v2.0",
                    # MAVROS 2.15+ adds its node name to the topic namespace.
                    # A root launch namespace preserves /mavros/... interfaces.
                    "namespace": "",
                }.items(),
            ),
        ]),
    ])
