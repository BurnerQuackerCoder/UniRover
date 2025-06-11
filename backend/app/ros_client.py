import asyncio
import websockets
import json
import logging
from .core.config import settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ROSClient:
    def __init__(self):
        self._connection = None
        self._is_running = False
        self.goal_result_event = asyncio.Event()
        self.last_goal_result = None
        self.current_battery = -1.0

    async def connect(self):
        """Establishes and maintains a connection to rosbridge."""
        self._is_running = True
        while self._is_running:
            try:
                logger.info(f"Connecting to ROS at {settings.ROSBRIDGE_URL}...")
                self._connection = await websockets.connect(settings.ROSBRIDGE_URL)
                logger.info("Successfully connected to ROS.")
                # After connecting, start listening and subscribe to topics
                asyncio.create_task(self._listener())
                await self._subscribe_to_topics()
                # Keep the connection alive
                await self._connection.wait_closed()
            except (websockets.exceptions.ConnectionClosedError, ConnectionRefusedError) as e:
                logger.error(f"ROS connection error: {e}. Retrying in 5 seconds...")
                self._connection = None
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"An unexpected error occurred in ROSClient.connect: {e}")
                await asyncio.sleep(5)

    async def disconnect(self):
        """Closes the WebSocket connection."""
        self._is_running = False
        if self._connection:
            logger.info("Disconnecting from ROS...")
            await self._connection.close()
            self._connection = None
            logger.info("Disconnected from ROS.")

    async def _listener(self):
        """Listens for incoming messages from rosbridge."""
        try:
            async for message in self._connection:
                data = json.loads(message)
                op = data.get("op")
                topic = data.get("topic")

                if op == "publish":
                    if topic == "/move_base/result":
                        self._handle_goal_result(data['msg'])
                    elif topic == "/battery_state": # NOTE: Change topic if yours is different
                        self._handle_battery_state(data['msg'])
        except websockets.exceptions.ConnectionClosed:
            logger.info("Listener task stopped: connection closed.")
        except Exception as e:
            logger.error(f"An error occurred in the listener task: {e}")

    def _handle_goal_result(self, msg):
        """Handles the result message from the move_base action."""
        status = msg['status']['status']
        # Status 3 = SUCCEEDED, Other statuses = various failures
        self.last_goal_result = {"success": status == 3, "status_code": status}
        logger.info(f"Received goal result: {self.last_goal_result}")
        self.goal_result_event.set() # Notify the waiting task that a result is in

    def _handle_battery_state(self, msg):
        """Handles battery state updates."""
        self.current_battery = msg.get('percentage', -1.0) * 100
        # logger.info(f"Received battery update: {self.current_battery:.2f}%")

    async def _send_json(self, data):
        """Sends a JSON object over the WebSocket if connected."""
        if self._connection:
            await self._connection.send(json.dumps(data))
        else:
            logger.warning("Cannot send message, not connected to ROS.")

    async def _subscribe_to_topics(self):
        """Subscribes to essential ROS topics."""
        logger.info("Subscribing to ROS topics...")
        # Subscribe to move_base result
        subscribe_goal_result = {
            "op": "subscribe",
            "topic": "/move_base/result",
            "type": "move_base_msgs/MoveBaseActionResult"
        }
        await self._send_json(subscribe_goal_result)

        # Subscribe to battery state
        subscribe_battery = {
            "op": "subscribe",
            "topic": "/battery_state", # NOTE: Change this topic name if yours is different
            "type": "sensor_msgs/BatteryState"
        }
        await self._send_json(subscribe_battery)

    async def send_goal(self, goal_pose: dict):
        """Sends a navigation goal to move_base."""
        if not self._connection:
            logger.error("Cannot send goal, not connected.")
            return False
            
        logger.info(f"Sending goal to pose: {goal_pose}")
        self.goal_result_event.clear()  # Reset the event before sending a new goal
        self.last_goal_result = None

        goal_msg = {
            "op": "publish",
            "topic": "/move_base/simple/goal", # Using simple goal for this example
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

    async def wait_for_goal_result(self, timeout=60.0):
        """Waits for the goal result event to be set."""
        try:
            await asyncio.wait_for(self.goal_result_event.wait(), timeout=timeout)
            return self.last_goal_result
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for goal result.")
            return {"success": False, "status_code": -1, "error": "timeout"}
        
    async def cancel_all_goals(self):
        """Publishes a message to cancel all active move_base goals."""
        if not self._connection:
            logger.error("Cannot cancel goals, not connected.")
            return

        logger.info("Sending cancel all goals command.")
        # The message to cancel goals is an empty message to the /move_base/cancel topic.
        # Note: For more advanced control, rosbridge's actionlib support would be used,
        # but this is a simple and effective way to stop the robot's current task.
        cancel_msg = {
            "op": "publish",
            "topic": "/move_base/cancel",
            "msg": {} # An empty GoalID message cancels all goals
        }
        await self._send_json(cancel_msg)

    async def return_to_base(self):
        """Sends the robot to its predefined base station."""
        # This reuses the send_goal method with the 'Base Station' coordinates.
        # We assume 'Base Station' exists in the coordinates map.
        from .scheduler import scheduler # Lazy import to avoid circular dependency
        base_coords = scheduler.room_coordinates.get("Base Station")
        if base_coords:
            logger.info("Sending robot to Base Station.")
            await self.send_goal(base_coords)
        else:
            logger.error("Could not return to base: 'Base Station' coordinates not found.")

# A single instance of the ROSClient to be used throughout the application
ros_client = ROSClient()