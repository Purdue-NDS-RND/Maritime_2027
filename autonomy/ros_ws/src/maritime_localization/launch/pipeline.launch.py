"""Shared live/replay pipeline. RGB mapping has one manager for all cameras."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, OpaqueFunction, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def nodes(context):
    def value(name):
        return LaunchConfiguration(name).perform(context)
    layout = value('camera_layout')
    cameras = [value('camera')]
    if layout == 'auto' and not value('second_camera') and value('camera') == 'camera_0':
        import json
        import re
        import time
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import DurabilityPolicy, QoSProfile
        from std_msgs.msg import String
        # Adapter metadata enumerates cameras even if an image stream is late.
        ros_context = rclpy.context.Context()
        rclpy.init(args=[], context=ros_context)
        probe = rclpy.create_node('mapping_camera_discovery', context=ros_context)
        executor = SingleThreadedExecutor(context=ros_context)
        executor.add_node(probe)
        rosters = []
        probe.create_subscription(String, '/sensors/camera_roster', lambda msg: rosters.append(msg.data),
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        try:
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                executor.spin_once(timeout_sec=0.1)
            if rosters:
                if len(set(rosters)) != 1:
                    raise ValueError('Conflicting camera rosters; isolate ROS domains')
                metadata = json.loads(rosters[0])
                if not isinstance(metadata, dict):
                    raise ValueError('Invalid Adapter camera roster')
                configured = metadata.get('enabled_cameras')
                if (metadata.get('schema_version') != 1 or not isinstance(configured, list)
                        or not configured or not all(isinstance(camera, str) and re.fullmatch(r'camera_\d+', camera) for camera in configured)
                        or len(set(configured)) != len(configured)):
                    raise ValueError('Invalid Adapter camera roster')
                cameras = configured
            # Legacy deployments without metadata retain the explicit camera
            # default; camera_layout/second_camera can override it.
        finally:
            executor.shutdown()
            probe.destroy_node()
            rclpy.shutdown(context=ros_context)
    elif layout == 'dual' and not value('second_camera'):
        cameras.append('camera_1')
    if value('second_camera'):
        if value('second_camera') in cameras:
            raise ValueError('second_camera requires a distinct camera name')
        cameras.append(value('second_camera'))
    use_sim_time = ParameterValue(LaunchConfiguration('use_sim_time'), value_type=bool)
    result = []
    for camera in cameras:
        result.append(Node(package='maritime_perception', executable='aruco_detector',
            namespace=f'perception/{camera}', output='screen',
            parameters=[PathJoinSubstitution([FindPackageShare('maritime_perception'), 'config', 'aruco.yaml']),
                        {'use_sim_time': use_sim_time, 'publish_debug_image': ParameterValue(
                            LaunchConfiguration('publish_debug_image'), value_type=bool)}],
            remappings=[('image', f'/sensors/{camera}/color/image_raw')]))
    parameters = [{'use_sim_time': use_sim_time}]
    if value('mapper_parameters'):
        parameters.append(value('mapper_parameters'))
    parameters.append({'cameras': cameras, 'pose_time_offset_s': ParameterValue(
        LaunchConfiguration('pose_time_offset_s'), value_type=float)})
    result.append(Node(package='maritime_localization', executable='buoy_mapper',
        namespace='localization', output='screen', parameters=parameters,
        remappings=[('vessel/odometry', value('pose_topic'))]))
    return result


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('camera_layout', default_value='auto', choices=['auto', 'single', 'dual']),
        DeclareLaunchArgument('camera', default_value='camera_0'),
        DeclareLaunchArgument('second_camera', default_value=''),
        DeclareLaunchArgument('method', default_value='bearing_ekf', choices=['bearing_ekf']),
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        DeclareLaunchArgument('pose_topic', default_value='/mavros/local_position/odom'),
        DeclareLaunchArgument('pose_time_offset_s', default_value='0.0'),
        DeclareLaunchArgument('mapper_parameters', default_value=''),
        DeclareLaunchArgument('publish_debug_image', default_value='false'),
        RegisterEventHandler(OnProcessExit(on_exit=[EmitEvent(event=Shutdown(reason='Pipeline node exited'))])),
        OpaqueFunction(function=nodes),
    ])
