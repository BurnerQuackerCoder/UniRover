import asyncio
import threading
import logging
import math
import uuid
from typing import Dict, Tuple, Optional

import rclpy
from rclpy.action import ActionClient
from action_msgs.msg import GoalStatus as RosGoalStatus
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from nav2_msgs.action import NavigateToPose
from geometry_msgs.msg import PoseStamped
from sensor_msgs.msg import BatteryState # Import BatteryState message
from action_msgs.msg import GoalStatus as RosGoalStatus

# Assume euler_to_quaternion exists (or define it)
def euler_to_quaternion(theta: float) -> Dict[str, float]:
    """Converts a yaw angle (theta) to a quaternion."""
    cy = math.cos(theta * 0.5)
    sy = math.sin(theta * 0.5)
    return {"x": 0.0, "y": 0.0, "z": sy, "w": cy}

# Event to signal when the ROS node is ready (spinning)
connection_established_event = asyncio.Event()

logger = logging.getLogger(__name__)

# --- Updated ROSClient using rclpy ---
class ROSClient(Node):
    """
    A ROS 2 node using rclpy to interact with Nav2 and other topics.
    Runs within the FastAPI application context but spins in a separate thread.
    """
    def __init__(self):
        # Initialize the ROS 2 node
        super().__init__('unirover_ros_client')
        logger.info("Initializing ROS 2 Node: unirover_ros_client...")

        # Action client for Nav2
        self._nav_action_client = ActionClient(self, NavigateToPose, '/navigate_to_pose')
        logger.info("Waiting for NavigateToPose action server...")
        if not self._nav_action_client.wait_for_server(timeout_sec=5.0):
             logger.error("NavigateToPose action server not available after 5s. Goals will fail.")
        else:
             logger.info("NavigateToPose action server found.")


        # Dictionary to store active action goal handles: {goal_id_str: goal_handle}
        self.active_goals: Dict[str, any] = {} # Using 'any' for goal_handle type hint flexibility

        # Battery state tracking
        self.current_battery: float = 100.0 # Default value
        # Define QoS profile for battery state (adjust if needed based on publisher)
        battery_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            depth=1
        )
        # --- FIX: Update topic name if necessary for ROSbot Humble ---
        self.battery_subscriber = self.create_subscription(
            BatteryState,
            '/battery_state', # Common topic for battery, check ROSbot config
            self._battery_callback,
            battery_qos
        )
        logger.info("Subscribed to /battery_state")

        # Flag to indicate connection readiness (node is spinning)
        self.is_ready = False
        self._spin_thread = None

    def start_spinning(self):
        """Starts the rclpy spinning in a separate thread."""
        if not self.is_ready:
            logger.info("Starting rclpy spin in a background thread...")
            # Use daemon=True so the thread exits when the main FastAPI process exits
            self._spin_thread = threading.Thread(target=rclpy.spin, args=(self,), daemon=True)
            self._spin_thread.start()
            self.is_ready = True
            connection_established_event.set() # Signal that the node is spinning
            logger.info("ROS 2 Node is spinning.")

    def _battery_callback(self, msg: BatteryState):
        """Callback function for the battery state subscriber."""
        # Update the battery percentage (assuming 'percentage' field exists)
        if hasattr(msg, 'percentage'):
            self.current_battery = msg.percentage * 100.0 # Convert fraction to percentage
            # logger.debug(f"Received battery update: {self.current_battery:.1f}%")
        else:
            # Fallback or alternative if 'percentage' is not available
            # Maybe use voltage and design voltage? Depends on the specific message content.
            # logger.warning("Received BatteryState message without 'percentage' field.")
            pass # Keep previous value for now

    async def connect(self) -> bool:
        """
        Placeholder connect method. The real connection is handled by rclpy.init()
        and the spinning thread. We just ensure spinning starts.
        """
        if not rclpy.ok():
             logger.error("rclpy has not been initialized before calling connect.")
             return False
        if not self.is_ready:
            self.start_spinning()
        return True # Indicate readiness

    async def disconnect(self):
        """Placeholder disconnect. Shutdown is handled externally by rclpy.shutdown()."""
        logger.info("ROS Client disconnect called (rclpy shutdown is external).")
        self.is_ready = False
        connection_established_event.clear()

    async def send_goal_action(self, goal_pose: dict) -> str:
        """Sends a navigation goal using the NavigateToPose action client."""

        server_ready = self._nav_action_client.server_is_ready()
        logger.info(f"send_goal_action: Checking status. self.is_ready={self.is_ready}, server_is_ready()={server_ready}")


        if not self.is_ready or not self._nav_action_client.server_is_ready():
             logger.error("Cannot send goal: Node not spinning or action server not ready.")
             raise ConnectionError("ROS 2 node or action server not ready.")

        goal_msg = NavigateToPose.Goal()
        goal_id_str = f"goal_{uuid.uuid4()}" # Use UUID for unique goal IDs

        # Create the PoseStamped message
        pose_stamped = PoseStamped()
        pose_stamped.header.stamp = self.get_clock().now().to_msg()
        pose_stamped.header.frame_id = 'map' # Standard frame for Nav2
        pose_stamped.pose.position.x = goal_pose['x']
        pose_stamped.pose.position.y = goal_pose['y']
        pose_stamped.pose.position.z = 0.0 # Assuming 2D navigation

        # Convert yaw to quaternion
        orientation_q = euler_to_quaternion(goal_pose.get('theta', 0.0)) # Use theta, default to 0 if not present
        pose_stamped.pose.orientation.x = orientation_q['x']
        pose_stamped.pose.orientation.y = orientation_q['y']
        pose_stamped.pose.orientation.z = orientation_q['z']
        pose_stamped.pose.orientation.w = orientation_q['w']

        goal_msg.pose = pose_stamped
        # goal_msg.behavior_tree = "" # Optional: specify a custom behavior tree

        logger.info(f"Sending NavigateToPose goal (ID: {goal_id_str}): {goal_pose}")

        send_goal_future = self._nav_action_client.send_goal_async(goal_msg)

        # Wait for the server to accept the goal
        try:
            #goal_handle = await asyncio.wrap_future(send_goal_future)
            goal_handle = await send_goal_future
        except Exception as e:
            #logger.error(f"Error sending goal: {e}", exc_info=True)
            logger.error(f"Error awaiting goal acceptance: {e}", exc_info=True)
            raise ConnectionError(f"Failed to get goal handle from action server: {e}")
            #raise ConnectionError(f"Failed to send goal to action server: {e}")

        if not goal_handle.accepted:
            logger.error(f"Goal {goal_id_str} rejected by server.")
            raise RuntimeError("Goal rejected by navigation server.")

        logger.info(f"Goal {goal_id_str} accepted by server.")
        self.active_goals[goal_id_str] = goal_handle # Store the handle

        return goal_id_str

    async def wait_for_goal_result(self, goal_id_str: str, timeout: float = 60.0):
        """Waits for the result of a specific navigation goal."""
        if goal_id_str not in self.active_goals:
            logger.error(f"Cannot wait for result: Goal ID {goal_id_str} not found in active goals.")
            return {"success": False, "status_code": -1, "error": "Goal ID not found"}

        goal_handle = self.active_goals[goal_id_str]
        logger.info(f"Waiting for result of goal {goal_id_str}...")

        get_result_future = goal_handle.get_result_async()
        try:
            # Wait for the result with a timeout
            #result_wrapper = await asyncio.wait_for(asyncio.wrap_future(get_result_future), timeout=timeout)
            result_wrapper = await asyncio.wait_for(get_result_future, timeout=timeout)
            status = result_wrapper.status
            # result = result_wrapper.result # The actual result message (NavigateToPose.Result)

            # Clean up the completed goal
            del self.active_goals[goal_id_str]

            if status == RosGoalStatus.STATUS_SUCCEEDED:
                logger.info(f"Goal {goal_id_str} succeeded.")
                return {"success": True, "status_code": status}
            elif status == RosGoalStatus.STATUS_CANCELED:
                 logger.warning(f"Goal {goal_id_str} was canceled.")
                 return {"success": False, "status_code": status, "error": "Canceled"}
            elif status == RosGoalStatus.STATUS_ABORTED:
                 logger.error(f"Goal {goal_id_str} aborted by server.")
                 return {"success": False, "status_code": status, "error": "Aborted"}
            else:
                 logger.error(f"Goal {goal_id_str} failed with status: {status}")
                 return {"success": False, "status_code": status, "error": f"Failed with status {status}"}

        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for result of goal {goal_id_str} after {timeout} seconds.")
             # Don't delete from active_goals here, it might still be running
            return {"success": False, "status_code": -1, "error": "timeout"}
        except Exception as e:
            logger.error(f"Error waiting for goal result {goal_id_str}: {e}", exc_info=True)
            # Attempt to clean up if something went wrong
            self.active_goals.pop(goal_id_str, None)
            return {"success": False, "status_code": -1, "error": f"Exception: {e}"}


    async def cancel_all_goals(self):
        """Cancels all active navigation goals."""
        if not self.active_goals:
            logger.info("Cancel all goals requested, but no active goals found.")
            return

        logger.warning(f"Canceling {len(self.active_goals)} active goal(s)...")
        # Create a list of goal handles to cancel
        goal_handles_to_cancel = list(self.active_goals.values())
        goal_ids_to_cancel = list(self.active_goals.keys())

        # Clear active goals immediately to prevent race conditions
        self.active_goals.clear()

        for goal_id, goal_handle in zip(goal_ids_to_cancel, goal_handles_to_cancel):
             if goal_handle:
                  logger.info(f"Requesting cancellation for goal {goal_id}...")
                  cancel_future = goal_handle.cancel_goal_async()
                  try:
                      # Wait briefly for acknowledgement, but don't block forever
                      #wait asyncio.wait_for(asyncio.wrap_future(cancel_future), timeout=2.0)
                      await asyncio.wait_for(cancel_future, timeout=2.0)
                      logger.info(f"Cancel request for goal {goal_id} sent.")
                  except asyncio.TimeoutError:
                      logger.warning(f"Timeout waiting for cancel confirmation for goal {goal_id}.")
                  except Exception as e:
                      logger.error(f"Error requesting cancel for goal {goal_id}: {e}")

    async def return_to_base(self) -> Optional[str]:
        """Commands the robot to return to its base station using Nav2."""
        # Need access to the scheduler's coordinates. This assumes `scheduler` instance
        # is available globally or passed in. A better approach might be needed.
        # For now, let's assume it's imported (circular import risk!).
        # A cleaner way: have main.py pass coords to ros_client upon init.
        from .scheduler import scheduler # Lazy import to mitigate issues
        base_coords = scheduler.room_coordinates.get("Base Station")
        if base_coords:
            logger.info("Commanding robot to return to Base Station via Nav2.")
            try:
                # Send goal and return the goal ID
                goal_id = await self.send_goal_action(base_coords)
                return goal_id
            except Exception as e:
                logger.error(f"Could not send return_to_base goal: {e}")
                return None
        else:
            logger.error("Could not return to base: 'Base Station' coordinates not found.")
            return None

# --- Global instance ---
# We initialize rclpy externally (in main.py lifespan) before creating this instance.
# If rclpy isn't initialized, creating the node will fail.
#ros_client: Optional[ROSClient] = None

'''def initialize_ros_client():
    """Initializes the global ros_client instance."""
    global ros_client
    if ros_client is None:
        if not rclpy.ok():
             # Initialize rclpy here if not already done (e.g., for testing)
             # In production, main.py's lifespan should handle this.
             rclpy.init()
             logger.warning("rclpy initialized within initialize_ros_client. Should be done in lifespan.")
        ros_client = ROSClient()
    return ros_client'''

# Note: The actual instantiation and spinning will happen in main.py