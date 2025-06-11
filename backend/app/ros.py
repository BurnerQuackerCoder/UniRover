from .core.config import settings

if settings.SIMULATION_MODE:
    from .mock_ros_client import mock_ros_client as ros_client
else:
    from .ros_client import ros_client