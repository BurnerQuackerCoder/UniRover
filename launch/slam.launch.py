import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    slam_params_file = LaunchConfiguration('slam_params_file')
    use_sim_time = LaunchConfiguration('use_sim_time')

    slam_params_file_arg = DeclareLaunchArgument(
        'slam_params_file',
        default_value=os.path.join(
            FindPackageShare("tutorial_pkg"), 'config', 'slam.yaml'
        ),
        description='Full path to the ROS2 parameters file to use for the slam_toolbox node',
    )

    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time', default_value='false', description='Use simulation/Gazebo clock'
    )

    slam_node = Node(
        package='slam_toolbox',
        executable='async_slam_toolbox_node',
        name='slam',
        parameters=[slam_params_file, {'use_sim_time': use_sim_time}],
    )

    ld = LaunchDescription()

    ld.add_action(use_sim_time_arg)
    ld.add_action(slam_params_file_arg)

    ld.add_action(slam_node)

    return ld
