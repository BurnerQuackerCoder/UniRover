import asyncio
import logging

logger = logging.getLogger(__name__)

class MockROSClient:
    """A mock client that simulates a ROS robot for UI/logic testing."""
    def __init__(self):
        self._connection = None
        self.goal_result_event = asyncio.Event()
        self.last_goal_result = None
        self.current_battery = 100.0 # Always has full battery

    async def connect(self):
        """Simulates connecting to ROS."""
        logger.info("RUNNING IN SIMULATION MODE. MockROSClient is active.")
        self._connection = True # Simulate a successful connection
        logger.info("Mock ROS Client 'connected'.")

    async def disconnect(self):
        """Simulates disconnecting."""
        self._connection = None
        logger.info("Mock ROS Client 'disconnected'.")

    async def send_goal(self, goal_pose: dict):
        """Simulates sending a goal and a successful arrival after a delay."""
        logger.info(f"[SIM] Received goal: {goal_pose}. Simulating 5-second travel time...")
        self.goal_result_event.clear()
        self.last_goal_result = None

        # Run the result simulation in the background
        asyncio.create_task(self._simulate_arrival())
        return True

    async def _simulate_arrival(self):
        """Internal task to simulate a robot arriving at a destination."""
        await asyncio.sleep(5) # Simulate travel time
        self.last_goal_result = {"success": True, "status_code": 3}
        logger.info(f"[SIM] Robot 'arrived' at destination. Sending result.")
        self.goal_result_event.set()

    async def wait_for_goal_result(self, timeout=60.0):
        """Waits for the simulated goal result."""
        try:
            await asyncio.wait_for(self.goal_result_event.wait(), timeout=timeout)
            return self.last_goal_result
        except asyncio.TimeoutError:
            logger.warning("[SIM] Timeout waiting for goal result.")
            return {"success": False, "status_code": -1, "error": "timeout"}

    async def cancel_all_goals(self):
        """Simulates canceling goals."""
        logger.info("[SIM] All goals have been 'canceled'.")

    async def return_to_base(self):
        """Simulates returning to base."""
        logger.info("[SIM] Robot is 'returning to base'. Simulating 5-second travel time...")
        await self.send_goal({"x": 0, "y": 0, "w": 1})

# A single instance for consistency, though we'll select it in another file.
mock_ros_client = MockROSClient()