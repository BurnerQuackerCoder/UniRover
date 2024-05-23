from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

def generate_launch_description():
    config_file = LaunchConfiguration("config_file")

    config_file_arg = DeclareLaunchArgument(
        "config_file",
        default_value="",
        description="Name of file rviz configuration file inside tutorial_pkg/rviz folder.",
    )

    rviz_config_path = PathJoinSubstitution([
        FindPackageShare("tutorial_pkg"), "rviz", config_file
    ])

    rviz2_node = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        arguments=["-d", rviz_config_path],
    )

    return LaunchDescription([config_file_arg, rviz2_node])
