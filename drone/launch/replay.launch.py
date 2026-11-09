"""Desktop ROS replay bridge; session/config must be selected explicitly."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("session", description="Recorded session with config.json and measurements.jsonl"),
        DeclareLaunchArgument("output", description="Empty output directory"),
        Node(package="maritime_perception", executable="perception_ros", name="perception_replay",
             parameters=[{"adapter": "recorded", "session": LaunchConfiguration("session"),
                          "output": LaunchConfiguration("output")}], output="screen"),
    ])
