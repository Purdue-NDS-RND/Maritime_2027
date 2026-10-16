"""The same detector/localizer launch for live topics and recorded topics."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    camera = LaunchConfiguration("camera")
    use_sim_time = LaunchConfiguration("use_sim_time")
    return LaunchDescription([
        DeclareLaunchArgument("camera", default_value="camera_0"),
        DeclareLaunchArgument("method", default_value="depth", choices=["depth", "triangulation"]),
        DeclareLaunchArgument("use_sim_time", default_value="false"),
        DeclareLaunchArgument("pose_topic", default_value="/mavros/local_position/odom"),
        DeclareLaunchArgument("publish_debug_image", default_value="false"),
        RegisterEventHandler(OnProcessExit(on_exit=[EmitEvent(event=Shutdown(reason="Pipeline node exited"))])),
        Node(package="maritime_perception", executable="aruco_detector",
             namespace=["perception/", camera], output="screen",
             parameters=[PathJoinSubstitution([FindPackageShare("maritime_perception"), "config", "aruco.yaml"]),
                         {"use_sim_time": use_sim_time,
                          "publish_debug_image": LaunchConfiguration("publish_debug_image")}],
             remappings=[("image", ["/sensors/", camera, "/color/image_raw"])]),
        Node(package="maritime_localization", executable="buoy_localizer",
             namespace="localization", output="screen",
             parameters=[{"method": LaunchConfiguration("method"), "use_sim_time": use_sim_time}],
             remappings=[("detections", ["/perception/", camera, "/detections"]),
                         ("camera_info", ["/sensors/", camera, "/color/camera_info"]),
                         ("depth", ["/sensors/", camera, "/depth/image_rect_raw"]),
                         ("vessel/odometry", LaunchConfiguration("pose_topic"))]),
    ])
