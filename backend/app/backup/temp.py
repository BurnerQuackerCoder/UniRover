import asyncio
import logging
import numpy as np
from python_tsp.exact import solve_tsp_dynamic_programming
from sqlalchemy.orm import Session
# from .ros_client import connection_established_event # Already imported in main, scheduler waits internally
from . import crud, models
from .core.config import settings
from .database import SessionLocal
# from .ros import ros_client # <--- DELETE THIS IMPORT
from .ros_client import ROSClient # <-- Import the Class type hint if needed

pickup_confirmation_events = {}
logger = logging.getLogger(__name__)

class Scheduler:
    def __init__(self):
        self._task = None
        self._is_running = False
        self.is_executing_tour = False
        self.current_tour = []
        self.current_tour_index = -1
        self.room_coordinates = {}
        self.abort_flag: asyncio.Event | None = None
        self.ros_client: Optional[ROSClient] = None # <-- ADD this instance variable

    # _run_scheduler_loop needs modification for battery check
    async def _run_scheduler_loop(self):
        logger.info("Scheduler is waiting for ROS connection/readiness signal...")
        await connection_established_event.wait() # Wait for signal from ros_client
        logger.info("ROS connection/readiness signal received. Scheduler is now active.")

        while self._is_running:
            try:
                if not self.is_executing_tour:
                    # --- CHANGE HERE: Use self.ros_client ---
                    # Use self.ros_client, check if it exists (for SIM_MODE), and check battery
                    client_available = self.ros_client is not None and self.ros_client.is_ready
                    battery_ok = not settings.ENFORCE_BATTERY_CHECK or (client_available and self.ros_client.current_battery >= settings.BATTERY_MIN_LEVEL)

                    if not battery_ok:
                         logger.warning(f"Robot not ready (Enforcing Battery Check: {settings.ENFORCE_BATTERY_CHECK}, Client Ready: {client_available}, Battery: {self.ros_client.current_battery if client_available else 'N/A'}%)")
                         await asyncio.sleep(30)
                         continue
                    # --- END CHANGE ---

                    db: Session = SessionLocal()
                    pending_deliveries = crud.get_deliveries_by_status(db, status=models.DeliveryStatus.PENDING)
                    db.close()

                    if len(pending_deliveries) >= settings.DELIVERY_BATCH_SIZE:
                        # Pass self.ros_client instance if needed by start_new_tour, though it's already a member
                        asyncio.create_task(self.start_new_tour(pending_deliveries))
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)
            await asyncio.sleep(15)

    # start_new_tour remains mostly the same, uses self.ros_client implicitly later

    # execute_next_goal_in_tour needs modification
    async def execute_next_goal_in_tour(self):
        # ... (abort check, index check remain same) ...
        delivery = self.current_tour[self.current_tour_index]
        coords = self.room_coordinates.get(delivery.destination)

        if not coords:
            await self.handle_failed_arrival(delivery, reason="Invalid Destination")
            return

        db: Session = SessionLocal()
        crud.update_delivery_status_in_db(db, delivery_id=delivery.id, new_status=models.DeliveryStatus.IN_PROGRESS)
        db.close()

        result = None
        # --- CHANGE HERE: Use self.ros_client ---
        if self.ros_client: # Check if client exists (important for SIM_MODE)
            try:
                goal_id = await self.ros_client.send_goal_action(coords)
                result = await self.ros_client.wait_for_goal_result(goal_id)
            except ConnectionError as e:
                logger.error(f"Cannot execute goal due to connection error: {e}")
                result = {"success": False, "error": f"Connection Error: {e}"}
            except Exception as e: # Catch other potential errors during goal send/wait
                logger.error(f"Error during goal execution for delivery {delivery.id}: {e}", exc_info=True)
                result = {"success": False, "error": f"Execution Error: {e}"}
        else:
             logger.error(f"Cannot execute goal for delivery {delivery.id}: ROS client is not available (Simulation Mode or Init Error?).")
             result = {"success": False, "error": "ROS Client Unavailable"}
        # --- END CHANGE ---

        if self.abort_flag and self.abort_flag.is_set():
            logger.warning("Abort detected after goal result/error. Halting tour.")
            return

        if result and result.get('success'):
            logger.info(f"✅ SUCCESS: Delivery #{delivery.id} (Item: '{delivery.item}') to dest '{delivery.destination}' reported success.")
            await self.handle_successful_arrival(delivery)
        else:
            reason = result.get("error", "Navigation Failed") if result else "Unknown ROS Client Error"
            logger.error(f"❌ FAILURE: Delivery #{delivery.id} (Item: '{delivery.item}') to dest '{delivery.destination}' failed. Reason: {reason}")
            await self.handle_failed_arrival(delivery, reason=reason)

    # handle_successful_arrival remains the same
    # handle_failed_arrival remains the same

    # finish_tour needs modification
    async def finish_tour(self):
        logger.info("Finishing tour and returning to base.")
        self.is_executing_tour = False
        self.current_tour = []
        self.current_tour_index = -1

        # --- CHANGE HERE: Use self.ros_client ---
        if self.ros_client: # Check if client exists
            try:
                goal_id = await self.ros_client.return_to_base()
                if goal_id:
                    logger.info(f"Waiting for robot to arrive at base (goal: {goal_id})...")
                    await self.ros_client.wait_for_goal_result(goal_id, timeout=120.0) # Longer timeout for base return
                    logger.info("Robot likely arrived at base station. Scheduler is now idle.")
                else:
                    logger.warning("Could not initiate return to base (no goal_id returned).")
            except ConnectionError as e:
                logger.error(f"Could not command return to base due to connection error: {e}")
            except Exception as e:
                logger.error(f"Error during return to base: {e}", exc_info=True)
        else:
             logger.warning("Cannot return robot to base: ROS client is not available.")
        # --- END CHANGE ---

    # abort_tour_and_return_to_base needs modification
    async def abort_tour_and_return_to_base(self):
        logger.warning("ABORTING CURRENT TOUR! Received emergency return to base command.")
        if self.abort_flag:
            self.abort_flag.set() # Signal other tasks to stop

        # --- CHANGE HERE: Use self.ros_client ---
        if self.ros_client: # Check if client exists
            try:
                await self.ros_client.cancel_all_goals()
            except ConnectionError as e:
                logger.error(f"Could not send cancel command while aborting: {e}")
            except Exception as e:
                logger.error(f"Error sending cancel command while aborting: {e}", exc_info=True)
        else:
             logger.warning("Cannot cancel goals: ROS client is not available.")
        # --- END CHANGE ---

        # Database reset logic remains the same
        db: Session = SessionLocal()
        try:
            # ... (query and reset logic) ...
        finally:
            db.close()

        # Call finish_tour to reset state and send home (it now uses self.ros_client)
        await self.finish_tour()

    # --- CHANGE start method signature ---
    def start(self, room_coords: dict, ros_client_instance: Optional[ROSClient]):
        logger.info("Starting scheduler...")
        self.room_coordinates = room_coords
        self.ros_client = ros_client_instance # <-- Assign the passed instance
        self._is_running = True
        # Abort flag creation needs careful handling if ros_client could be None
        if self.ros_client: # Only create event if we have a client to interact with
            self.abort_flag = asyncio.Event()
        else: # If no client (e.g., SIM_MODE without mock passed?), set flag to None
             self.abort_flag = None
             logger.warning("Scheduler started without a ROS client instance. Abort functionality might be limited.")
        self._task = asyncio.create_task(self._run_scheduler_loop())
    # --- END CHANGE ---

    def stop(self):
        # ... (remains the same) ...

scheduler = Scheduler() # Keep the instance creation