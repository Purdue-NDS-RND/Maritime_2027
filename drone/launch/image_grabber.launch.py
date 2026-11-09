"""Capture-only launch. All camera controls are supplied through the JSON config."""
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from pathlib import Path


def generate_launch_description():
    default_config = str(Path(get_package_share_directory("maritime_perception"))/"config/imx519_capture.json")
    return LaunchDescription([
        DeclareLaunchArgument("config", default_value=default_config),
        Node(package="maritime_perception", executable="image_grabber", output="screen",
             arguments=["--config", LaunchConfiguration("config"), "--ros"]),
    ])
