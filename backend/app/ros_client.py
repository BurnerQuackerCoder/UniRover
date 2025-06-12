import asyncio
import websockets
import json
import logging
import uuid
import math
from .core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the event object at the module level
connection_established_event = asyncio.Event()

def euler_to_quaternion(theta: float) -> dict:
    cy = math.cos(theta * 0.5)
    sy = math.sin(theta * 0.5)
    return {"x": 0.0, "y": 0.0, "z": sy, "w": cy}

class ROSClient:
    def __init__(self):
        self.connection: websockets.WebSocketClientProtocol | None = None
        self.active_goals: dict[str, tuple[asyncio.Event, dict | None]] = {}
        self._listener_task: asyncio.Task | None = None
        logger.info("[DEBUG] ROSClient initialized. Connection is None.")

    async def connect(self) -> bool:
        if self.connection:
            logger.info("[DEBUG] Connect called, but already connected.")
            return True
        try:
            logger.info(f"[DEBUG] Attempting to connect to {settings.ROSBRIDGE_URL}...")
            self.connection = await asyncio.wait_for(websockets.connect(settings.ROSBRIDGE_URL), timeout=5.0)
            logger.info(f"[DEBUG] Connection successful. self.connection is now an object.")
            connection_established_event.set() # Signal that the connection is ready
            if self._listener_task and not self._listener_task.done():
                self._listener_task.cancel()
            self._listener_task = asyncio.create_task(self._listener())
            await self._subscribe_to_topics()
            return True
        except Exception as e:
            logger.error(f"[DEBUG] connect() failed: {e}")
            self.connection = None
            return False

    async def disconnect(self):
        logger.warning("[DEBUG] Disconnect called.")
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
        if self.connection:
            await self.connection.close()
        self.connection = None
        logger.info("[DEBUG] ROS Client connection set to None.")

    async def _listener(self):
        logger.info("[DEBUG] ROS listener task started.")
        try:
            async for message in self.connection:
                pass # We don't need to process messages for this test
        except asyncio.CancelledError:
            logger.info("[DEBUG] Listener task was cancelled.")
        except websockets.exceptions.ConnectionClosed:
            logger.warning("[DEBUG] Listener detected connection closed by server.")
        except Exception as e:
            logger.error(f"[DEBUG] Unhandled error in listener: {e}", exc_info=True)
        finally:
            logger.critical("[DEBUG] LISTENER EXITED. Setting self.connection to None.")
            self.connection = None

    async def _send_json(self, data: dict):
        logger.info(f"[DEBUG] _send_json called. Connection state is: {'Connected' if self.connection else 'None'}")
        if not self.connection:
            raise ConnectionError("Not connected to ROS.")
        await self.connection.send(json.dumps(data))

    async def _subscribe_to_topics(self):
        logger.info("[DEBUG] Subscribing to topics...")
        # Simplified for debugging
        pass

    async def send_goal_action(self, goal_pose: dict) -> str:
        goal_id_str = f"goal_{uuid.uuid4()}"
        orientation = euler_to_quaternion(goal_pose['theta'])
        action_goal_message = {"header": {"frame_id": "map"},"goal_id": {"id": goal_id_str, "stamp": {"secs": 0, "nsecs": 0}},"goal": {"target_pose": {"header": {"frame_id": "map"}, "pose": {"position": {"x": goal_pose['x'], "y": goal_pose['y'], "z": 0.0}, "orientation": orientation}}}}
        rosbridge_msg = {"op": "publish", "id": goal_id_str, "topic": "/move_base/goal", "msg": action_goal_message}
        await self._send_json(rosbridge_msg)
        logger.info(f"[DEBUG] Goal '{goal_id_str}' sent via _send_json.")
        return goal_id_str
    
    # Other methods are simplified for this debugging test
    async def wait_for_goal_result(self, goal_id: str, timeout: float = 5.0): return {"success": True}
    async def cancel_all_goals(self): await self._send_json({"op": "publish", "topic": "/move_base/cancel", "msg": {}})
    # In ROSClient class in ros_client.py
    async def return_to_base(self):
        """Commands the robot to return to its base station."""
        from .scheduler import scheduler
        base_coords = scheduler.room_coordinates.get("Base Station")
        if base_coords and 'theta' in base_coords:
            logger.info("Commanding robot to return to Base Station.")
            # --- CHANGE THIS LINE ---
            return await self.send_goal_action(base_coords)
        else:
            logger.error("Could not return to base: 'Base Station' coordinates invalid.")
            # --- ADD THIS LINE ---
            return None

ros_client = ROSClient()