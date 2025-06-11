import asyncio
import websockets
import json
import logging
from .core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ROSClient:
    def __init__(self):
        self._connection = None
        self._is_running = False
        # --- Temporarily disabled for testing ---
        # self.goal_result_event = asyncio.Event()
        # self.last_goal_result = None
        self.current_battery = 100.0 # Assume full battery

    async def connect(self):
        """Establishes a simple connection to rosbridge without background listeners."""
        self._is_running = True
        logger.info(f"Attempting a simple connection to ROS at {settings.ROSBRIDGE_URL}...")
        try:
            # Try to connect with a timeout
            self._connection = await asyncio.wait_for(
                websockets.connect(settings.ROSBRIDGE_URL), 
                timeout=10.0
            )
            logger.info("Successfully connected to ROS.")
        except asyncio.TimeoutError:
            logger.error("Connection timed out. Is rosbridge running and the IP correct?")
        except Exception as e:
            logger.error(f"Failed to connect to ROS: {e}")
            self._connection = None

    async def disconnect(self):
        """Closes the WebSocket connection."""
        self._is_running = False
        if self._connection:
            logger.info("Disconnecting from ROS...")
            await self._connection.close()
            self._connection = None

    async def _send_json(self, data):
        """Sends a JSON object over the WebSocket if connected."""
        if self._connection:
            await self._connection.send(json.dumps(data))
        else:
            logger.warning("Cannot send message, not connected to ROS.")

    async def send_goal(self, goal_pose: dict):
        """Sends a navigation goal to move_base."""
        if not self._connection:
            logger.error("Cannot send goal, not connected.")
            return False
            
        logger.info(f"Sending goal to pose: {goal_pose}")
        goal_msg = {
            "op": "publish",
            "topic": "/move_base/simple/goal",
            "msg": {
                "header": {"frame_id": "map"},
                "pose": {
                    "position": {"x": goal_pose['x'], "y": goal_pose['y'], "z": 0.0},
                    "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": goal_pose['w']}
                }
            }
        }
        await self._send_json(goal_msg)
        return True

    # --- The following methods are temporarily disabled ---
    # async def wait_for_goal_result(self, timeout=60.0):
    #     logger.info("wait_for_goal_result is disabled in simple mode.")
    #     await asyncio.sleep(5) # Simulate a delay
    #     return {"success": True} # Always return success for now

# A single instance of the ROSClient
ros_client = ROSClient()