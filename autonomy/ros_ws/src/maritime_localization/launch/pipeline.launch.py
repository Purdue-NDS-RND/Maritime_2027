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
    cameras = [value('camera')]
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
