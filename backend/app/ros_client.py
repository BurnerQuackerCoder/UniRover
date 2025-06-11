import asyncio
import websockets
import json
import logging
import uuid
from .core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ROSClient:
    def __init__(self):
        self._connection = None
        self._is_running = False
        self.current_battery = -1.0
        # Dictionary to hold events for active goals, keyed by goal_id
        self.active_goals = {}

    async def connect(self):
        """Establishes and maintains a connection to rosbridge."""
        self._is_running = True
        logger.info(f"Connecting to ROS at {settings.ROSBRIDGE_URL}...")
        try:
            # Connect with a timeout
            self._connection = await asyncio.wait_for(websockets.connect(settings.ROSBRIDGE_URL), timeout=10.0)
            logger.info("Successfully connected to ROS.")
            # Start the background listener task
            asyncio.create_task(self._listener())
            await self._subscribe_to_topics()
        except Exception as e:
            logger.error(f"Failed to connect or subscribe: {e}")
            self._connection = None

    async def disconnect(self):
        """Closes the WebSocket connection."""
        if self._connection:
            logger.info("Disconnecting from ROS...")
            await self._connection.close()
        self._connection = None

    async def _listener(self):
        """Listens for incoming messages from rosbridge and routes them."""
        logger.info("ROS listener started.")
        try:
            async for message in self._connection:
                data = json.loads(message)
                op = data.get("op")

                if op == "publish":
                    topic = data.get("topic")
                    if topic == settings.ROS_BATTERY_TOPIC:
                        self._handle_battery_state(data['msg'])
                elif op == "result": # This is for the robust Action client
                    self._handle_action_result(data)
        except websockets.exceptions.ConnectionClosed:
            logger.warning("ROS connection closed. Listener stopped.")
            self._connection = None
        except Exception as e:
            logger.error(f"Error in ROS listener: {e}")
            self._connection = None

    def _handle_action_result(self, result_msg):
        """Handles the result message from an action call."""
        goal_id = result_msg.get("id")
        if goal_id in self.active_goals:
            event, _ = self.active_goals[goal_id]
            status = result_msg.get("values", {}).get("status", {}).get("status")
            logger.info(f"Goal {goal_id} completed with status: {status}")
            # Status 3 is SUCCEEDED in move_base actions
            self.active_goals[goal_id] = (event, {"success": status == 3})
            event.set() # Signal that the result has arrived

    def _handle_battery_state(self, msg):
        self.current_battery = msg.get('percentage', -1.0) * 100

    async def _send_json(self, data):
        if self._connection:
            await self._connection.send(json.dumps(data))
        else:
            raise ConnectionError("Not connected to ROS.")

    async def _subscribe_to_topics(self):
        """Subscribes to battery state topic."""
        subscribe_battery = {
            "op": "subscribe",
            "topic": settings.ROS_BATTERY_TOPIC,
            "type": "sensor_msgs/BatteryState"
        }
        await self._send_json(subscribe_battery)
        logger.info("Subscribed to {settings.ROS_BATTERY_TOPIC}.")

    async def send_goal_action(self, goal_pose: dict):
        """Sends a navigation goal as a ROS Action and returns its ID."""
        goal_id = f"goal_{uuid.uuid4()}"
        logger.info(f"Sending action goal '{goal_id}' to pose: {goal_pose}")
        
        action_goal_msg = {
            "op": "call_service",
            "service": "/move_base/goal", # This is how rosbridge handles action goals
            "id": goal_id,
            "args": {
                "goal": {
                    "target_pose": {
                        "header": {"frame_id": "map"},
                        "pose": {
                            "position": {"x": goal_pose['x'], "y": goal_pose['y'], "z": 0.0},
                            "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": goal_pose['w']}
                        }
                    }
                }
            }
        }
        
        # Create an event to wait for the result of this specific goal
        event = asyncio.Event()
        self.active_goals[goal_id] = (event, None) # Store the event and placeholder for the result
        
        await self._send_json(action_goal_msg)
        return goal_id

    async def wait_for_goal_result(self, goal_id: str, timeout=120.0):
        """Waits for a specific goal's result."""
        if goal_id not in self.active_goals:
            return {"success": False, "error": "invalid goal_id"}
            
        event, _ = self.active_goals[goal_id]
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            _, result = self.active_goals.pop(goal_id) # Get result and clean up
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for result of goal {goal_id}.")
            self.active_goals.pop(goal_id, None) # Clean up
            return {"success": False, "error": "timeout"}

    async def cancel_all_goals(self):
        # Implementation for canceling goals can be added here if needed
        logger.info("Cancel goals functionality to be implemented.")
        pass

    async def return_to_base(self):
        # This can be refactored to use the action system as well
        from .scheduler import scheduler
        base_coords = scheduler.room_coordinates.get("Base Station")
        if base_coords:
            logger.info("Sending robot to Base Station via action.")
            await self.send_goal_action(base_coords)
        else:
            logger.error("Could not return to base: 'Base Station' coordinates not found.")

ros_client = ROSClient()