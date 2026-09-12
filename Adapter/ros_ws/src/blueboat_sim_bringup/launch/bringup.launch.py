from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    package_share = Path(get_package_share_directory("blueboat_sim_bringup"))

    bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="blueboat_gz_bridge",
        output="screen",
        parameters=[{"config_file": str(package_share / "config" / "bridge.yaml")}],
    )
    rgb_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="blueboat_rgb_bridge",
        output="screen",
        parameters=[{"config_file": str(package_share / "config" / "bridge_rgb.yaml")}],
    )
    depth_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="blueboat_depth_bridge",
        output="screen",
        parameters=[{"config_file": str(package_share / "config" / "bridge_depth.yaml")}],
    )
    static_frames = [
        Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            name="world_to_odom",
            remappings=[("/tf_static", "/blueboat/ground_truth/tf_static")],
            arguments=["--x", "0", "--y", "0", "--z", "0", "--roll", "0", "--pitch", "0", "--yaw", "0", "--frame-id", "world", "--child-frame-id", "odom"],
        ),
        Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            name="base_to_zed2i",
            arguments=["--x", "0.35", "--y", "0", "--z", "0.40", "--roll", "0", "--pitch", "0", "--yaw", "0", "--frame-id", "base_link", "--child-frame-id", "zed2i_camera_link"],
        ),
        Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            name="zed2i_to_optical",
            arguments=["--x", "0", "--y", "0", "--z", "0", "--roll", "-1.5707963267948966", "--pitch", "0", "--yaw", "-1.5707963267948966", "--frame-id", "zed2i_camera_link", "--child-frame-id", "zed2i_left_camera_optical_frame"],
        ),
    ]
    # Duplicate camera extrinsics into the evaluation tree. Navigation sees only
    # camera extrinsics, never the perfect Gazebo world/odom/base_link pose.
    evaluation_frames = [
        Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            name="evaluation_base_to_camera",
            arguments=["--x", "0.35", "--y", "0", "--z", "0.40", "--frame-id", "base_link", "--child-frame-id", "zed2i_camera_link"],
            remappings=[("/tf_static", "/blueboat/ground_truth/tf_static")],
        ),
        Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            name="evaluation_camera_to_optical",
            arguments=["--roll", "-1.5707963267948966", "--pitch", "0", "--yaw", "-1.5707963267948966", "--frame-id", "zed2i_camera_link", "--child-frame-id", "zed2i_left_camera_optical_frame"],
            remappings=[("/tf_static", "/blueboat/ground_truth/tf_static")],
        ),
    ]
    return LaunchDescription([bridge, rgb_bridge, depth_bridge, *static_frames, *evaluation_frames])
