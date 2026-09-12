from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import GroupAction, IncludeLaunchDescription
from launch.launch_description_sources import AnyLaunchDescriptionSource
from launch_ros.actions import Node, SetParameter


def generate_launch_description():
    package_share = Path(get_package_share_directory("blueboat_sim_bringup"))
    mavros_share = Path(get_package_share_directory("mavros"))

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
    # ArduPilot accepts RC override messages only from SYSID_MYGCS (255 by
    # default). Keep the stock MAVROS APM launch/configuration while assigning
    # MAVROS the conventional GCS source ID; target IDs remain FCU 1/1.
    mavros = GroupAction(
        actions=[
            SetParameter(name="system_id", value=255),
            IncludeLaunchDescription(
                AnyLaunchDescriptionSource(str(mavros_share / "launch" / "apm.launch")),
                launch_arguments={
                    "fcu_url": "udp://:14552@",
                    "gcs_url": "",
                    "tgt_system": "1",
                    "tgt_component": "1",
                    "fcu_protocol": "v2.0",
                    "namespace": "mavros",
                }.items(),
            ),
        ]
    )
    static_frames = [
        Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            name="world_to_odom",
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
    return LaunchDescription([bridge, rgb_bridge, depth_bridge, mavros, *static_frames])
