"""Environment-neutral Nav2 servers; no simulator or vehicle transport ownership."""
from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    share = Path(get_package_share_directory('maritime_navigation'))
    config = str(share/'config/nav2.yaml')
    servers = [('nav2_planner', 'planner_server'), ('nav2_controller', 'controller_server'),
               ('nav2_bt_navigator', 'bt_navigator')]
    nodes = [Node(package=p, executable=e, name=e, output='screen', parameters=[config, LaunchConfiguration('nav2_overrides'), *(
                  [{'default_nav_to_pose_bt_xml': str(share/'behavior_trees/replan.xml')}]
                  if e == 'bt_navigator' else
                  [{'GridBased.lattice_filepath': str(share/'config/lattice_diff_10cm.json')}]
                  if e == 'planner_server' else [])],
                  remappings=[('cmd_vel', '/navigation/cmd_vel')]) for p, e in servers]
    nodes += [Node(package='nav2_lifecycle_manager', executable='lifecycle_manager',
                   name='navigation_lifecycle', output='screen', parameters=[{
                       'autostart': True, 'node_names': [e for _, e in servers]}]),
              Node(package='maritime_navigation', executable='navigator', output='screen',
                   parameters=[{'task': LaunchConfiguration('task'),
                       'uncertainty_mode': LaunchConfiguration('uncertainty_mode'),
                       'operating_bounds': ParameterValue(LaunchConfiguration('operating_bounds'), value_type=str),
                       'assume_bounded_water': ParameterValue(LaunchConfiguration('assume_bounded_water'), value_type=bool),
                       'bootstrap_clear_start': ParameterValue(LaunchConfiguration('bootstrap_clear_start'), value_type=bool),
                       'goal_x': ParameterValue(LaunchConfiguration('goal_x'), value_type=float),
                       'goal_y': ParameterValue(LaunchConfiguration('goal_y'), value_type=float),
                       'goal_yaw': ParameterValue(LaunchConfiguration('goal_yaw'), value_type=float),
                       'behavior_tree': str(share/'behavior_trees/replan.xml')}],
                   remappings=[('vessel/odometry', LaunchConfiguration('pose_topic'))])]
    return LaunchDescription([
        DeclareLaunchArgument('nav2_overrides', default_value=config),
        DeclareLaunchArgument('task', default_value='goal', choices=['goal', 'gate', 'slalom']),
        DeclareLaunchArgument('uncertainty_mode', default_value='graded', choices=['graded', 'hard']),
        DeclareLaunchArgument('pose_topic', default_value='/vessel/odometry'),
        DeclareLaunchArgument('operating_bounds', default_value='[-5,-12,45,12]'),
        DeclareLaunchArgument('assume_bounded_water', default_value='false'),
        DeclareLaunchArgument('bootstrap_clear_start', default_value='false'),
        DeclareLaunchArgument('goal_x', default_value='10.0'),
        DeclareLaunchArgument('goal_y', default_value='0.0'),
        DeclareLaunchArgument('goal_yaw', default_value='0.0'),
        RegisterEventHandler(OnProcessExit(on_exit=[EmitEvent(event=Shutdown(reason='Navigation process exited'))])),
        *nodes])
