import asyncio
import logging
import numpy as np
from python_tsp.exact import solve_tsp_dynamic_programming
from sqlalchemy.orm import Session
from typing import Optional 

from .ros_client import connection_established_event, ROSClient 
from . import crud, models
from .core.config import settings
from .database import SessionLocal

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
        self.ros_client: Optional[ROSClient] = None

    async def _run_scheduler_loop(self):
        logger.info("Scheduler waiting for ROS connection/readiness signal...")
        await connection_established_event.wait() 
        logger.info("ROS connection/readiness signal received. Scheduler is now active.")

        while self._is_running:
            try:
                # **CRITICAL CHECK**: Only look for new tours if NOT executing
                if not self.is_executing_tour:
                    client_available = self.ros_client is not None and self.ros_client.is_ready
                    battery_level = self.ros_client.current_battery if client_available else -1.0
                    battery_ok = not settings.ENFORCE_BATTERY_CHECK or (client_available and battery_level >= settings.BATTERY_MIN_LEVEL)

                    if not battery_ok:
                         logger.warning(f"Robot not ready to start tour (Enforce Battery Check: {settings.ENFORCE_BATTERY_CHECK}, ROS Client Ready: {client_available}, Battery: {battery_level:.1f}%)")
                         await asyncio.sleep(30)
                         continue

                    db: Session = SessionLocal()
                    try:
                        pending_deliveries = crud.get_deliveries_by_status(db, status=models.DeliveryStatus.PENDING)
                    finally:
                        db.close()

                    if len(pending_deliveries) >= settings.DELIVERY_BATCH_SIZE:
                        logger.info(f"Batch size ({settings.DELIVERY_BATCH_SIZE}) reached with {len(pending_deliveries)} pending deliveries. Starting new tour.")
                        asyncio.create_task(self.start_new_tour(pending_deliveries))

            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)

            # Sleep at the end of the loop
            await asyncio.sleep(15)

    async def start_new_tour(self, deliveries: list[models.Delivery]):
        if self.is_executing_tour:
            logger.warning("Attempted to start a new tour while one is already in progress.")
            return
        if self.abort_flag is None and self.ros_client is not None:
             logger.error("Scheduler started with ROS client but abort_flag is None. Cannot start tour.")
             return

        # Set the lock: We are now executing a tour
        self.is_executing_tour = True

        if self.abort_flag:
            self.abort_flag.clear()

        logger.info(f"Starting new tour creation with {len(deliveries)} potential deliveries.")

        db: Session = SessionLocal()
        try:
            valid_deliveries = []
            for d in deliveries:
                if d.destination in self.room_coordinates:
                    valid_deliveries.append(d)
                else:
                    logger.error(f"Destination '{d.destination}' for delivery #{d.id} not found in coordinates map. Marking as Failed.")
                    crud.update_delivery_status_in_db(db, delivery_id=d.id, new_status=models.DeliveryStatus.FAILED)

            if not valid_deliveries:
                logger.warning("No valid deliveries found after filtering. Aborting tour creation.")
                self.is_executing_tour = False # Release the lock
                return 

            logger.info(f"Optimizing path for {len(valid_deliveries)} valid deliveries.")
            locations = [d.destination for d in valid_deliveries]
            all_stops = ["Base Station"] + locations

            if "Base Station" not in self.room_coordinates:
                 logger.error("Cannot calculate TSP: 'Base Station' coordinates missing.")
                 raise ValueError("'Base Station' coordinates missing.")

            distance_matrix = np.array([
                [np.linalg.norm(np.array([self.room_coordinates[p1]['x'], self.room_coordinates[p1]['y']]) - np.array([self.room_coordinates[p2]['x'], self.room_coordinates[p2]['y']])) for p2 in all_stops]
                for p1 in all_stops
            ])

            permutation, _ = solve_tsp_dynamic_programming(distance_matrix)

            self.current_tour = []
            for i in permutation:
                 stop_name = all_stops[i]
                 if stop_name != "Base Station":
                      delivery_obj = next((d for d in valid_deliveries if d.destination == stop_name), None)
                      if delivery_obj:
                          self.current_tour.append(delivery_obj)

            route_str = ' -> '.join([d.destination for d in self.current_tour])
            logger.info(f"Optimized route: Base Station -> {route_str} -> Base Station (implicitly)")

            for delivery in self.current_tour:
                crud.update_delivery_status_in_db(db, delivery_id=delivery.id, new_status=models.DeliveryStatus.SCHEDULED)

            self.current_tour_index = 0
            await self.execute_next_goal_in_tour()

        except Exception as e:
            logger.error(f"Failed during tour creation or initial execution: {e}", exc_info=True)
            try:
                 ids_to_reset = [d.id for d in self.current_tour if d.status == models.DeliveryStatus.SCHEDULED]
                 if ids_to_reset:
                      crud.reset_deliveries_status(db, delivery_ids=ids_to_reset)
                      logger.info(f"Reset status for deliveries due to tour creation failure: {ids_to_reset}")
            except Exception as reset_e:
                 logger.error(f"Failed to reset delivery statuses after tour creation error: {reset_e}")

            # Call finish_tour to reset state and return home
            await self.finish_tour()
        finally:
            db.close()

    async def execute_next_goal_in_tour(self):
        if self.abort_flag and self.abort_flag.is_set():
            logger.warning("Abort detected before executing next goal. Halting tour.")
            # Do NOT proceed. The abort function will call finish_tour.
            return

        if self.current_tour_index >= len(self.current_tour):
            logger.info("Tour completed (all deliveries processed). Finishing up.")
            await self.finish_tour()
            return

        delivery = self.current_tour[self.current_tour_index]
        coords = self.room_coordinates.get(delivery.destination)

        if not coords:
            logger.error(f"Destination '{delivery.destination}' for delivery #{delivery.id} has invalid coordinates. Failing this step.")
            await self.handle_failed_arrival(delivery, reason="Invalid Destination Coordinates")
            return

        db: Session = SessionLocal()
        try:
            crud.update_delivery_status_in_db(db, delivery_id=delivery.id, new_status=models.DeliveryStatus.IN_PROGRESS)
        finally:
            db.close()

        result = None
        if self.ros_client:
            try:
                logger.info(f"Sending goal for delivery #{delivery.id} to {delivery.destination} ({coords})")
                goal_id = await self.ros_client.send_goal_action(coords)
                result = await self.ros_client.wait_for_goal_result(goal_id, timeout=settings.NAVIGATION_TIMEOUT_SECONDS)
            except ConnectionError as e:
                logger.error(f"Cannot execute goal for delivery #{delivery.id} due to connection error: {e}")
                result = {"success": False, "error": f"Connection Error: {e}"}
            except Exception as e:
                logger.error(f"Error during goal execution (send/wait) for delivery #{delivery.id}: {e}", exc_info=True)
                result = {"success": False, "error": f"Execution Error: {e}"}
        else:
             logger.error(f"Cannot execute goal for delivery #{delivery.id}: ROS client is not available.")
             result = {"success": False, "error": "ROS Client Unavailable"}

        if self.abort_flag and self.abort_flag.is_set():
            logger.warning("Abort detected after goal result/error. Halting tour processing.")
            return

        if result and result.get('success'):
            logger.info(f"✅ SUCCESS: Navigation goal for delivery #{delivery.id} (Item: '{delivery.item}') to '{delivery.destination}' reported success.")
            await self.handle_successful_arrival(delivery)
        else:
            reason = result.get("error", "Navigation Failed or Timed Out") if result else "Unknown ROS Client Error"
            logger.error(f"❌ FAILURE: Navigation goal for delivery #{delivery.id} (Item: '{delivery.item}') to '{delivery.destination}' failed. Reason: {reason}")
            await self.handle_failed_arrival(delivery, reason=reason)

    async def handle_successful_arrival(self, delivery: models.Delivery):
        if self.abort_flag and self.abort_flag.is_set():
             logger.warning(f"Abort detected upon arrival at {delivery.destination}. Skipping pickup wait.")
             return 

        logger.info(f"Arrived at {delivery.destination} for delivery #{delivery.id}. Awaiting pickup confirmation ({settings.PICKUP_TIMEOUT_SECONDS}s).")
        db: Session = SessionLocal()
        try:
            crud.update_delivery_status_in_db(db, delivery_id=delivery.id, new_status=models.DeliveryStatus.AWAITING_PICKUP)
        finally:
            db.close()

        pickup_event = asyncio.Event()
        pickup_confirmation_events[delivery.id] = pickup_event

        try:
            await asyncio.wait_for(pickup_event.wait(), timeout=settings.PICKUP_TIMEOUT_SECONDS)

            if self.abort_flag and self.abort_flag.is_set():
                 logger.warning(f"Abort detected after pickup confirmation for delivery {delivery.id}. Not marking as Delivered.")
                 return

            logger.info(f"Pickup confirmed for delivery #{delivery.id}.")
            db_session = SessionLocal()
            try:
                crud.update_delivery_status_in_db(db_session, delivery_id=delivery.id, new_status=models.DeliveryStatus.DELIVERED)
            finally:
                db_session.close()

            self.current_tour_index += 1
            await self.execute_next_goal_in_tour()

        except asyncio.TimeoutError:
            if self.abort_flag and self.abort_flag.is_set():
                 logger.warning(f"Abort detected after pickup timeout for delivery {delivery.id}.")
                 return

            logger.warning(f"Pickup confirmation timed out for delivery #{delivery.id}. Marking as Failed.")
            await self.handle_failed_arrival(delivery, reason="Pickup Timeout")

        finally:
            pickup_confirmation_events.pop(delivery.id, None)


    async def handle_failed_arrival(self, delivery: models.Delivery, reason="Unknown"):
        if self.abort_flag and self.abort_flag.is_set():
             logger.info(f"Abort detected during failed arrival handling for delivery #{delivery.id}. Abort logic will reset status.")
             return

        logger.error(f"Handling failed step for delivery #{delivery.id} to {delivery.destination}. Reason: {reason}. Marking as FAILED.")
        db: Session = SessionLocal()
        try:
            crud.update_delivery_status_in_db(db, delivery_id=delivery.id, new_status=models.DeliveryStatus.FAILED)
        finally:
            db.close()

        self.current_tour_index += 1
        logger.info(f"Moving to next step in tour after failure of delivery #{delivery.id}.")
        await self.execute_next_goal_in_tour()

    async def finish_tour(self):
        """
        Resets scheduler state AND returns robot to base.
        This function is the *only* place that should set is_executing_tour to False.
        """
        logger.info("Finishing current tour execution cycle.")

        logger.info("Attempting to command robot return to Base Station.")
        if self.ros_client:
            try:
                goal_id = await self.ros_client.return_to_base()
                if goal_id:
                    logger.info(f"Return to base goal ({goal_id}) sent. Waiting for completion...")
                    await self.ros_client.wait_for_goal_result(goal_id, timeout=settings.RETURN_TO_BASE_TIMEOUT_SECONDS)
                    logger.info(f"Return to base goal ({goal_id}) likely completed.")
                else:
                    logger.warning("Could not initiate return to base (return_to_base returned None). Base coords ok?")
            except ConnectionError as e:
                logger.error(f"Could not command return to base due to connection error: {e}")
            except Exception as e:
                logger.error(f"Error during return to base process: {e}", exc_info=True)
        else:
             logger.warning("Cannot return robot to base: ROS client is not available.")

        # --- *** THE FIX IS HERE *** ---
        # Reset state *after* the robot has returned (or failed to return) to base.
        # This releases the "lock" so the main loop can look for new tours.
        logger.info("Resetting scheduler state to idle.")
        self.is_executing_tour = False
        self.current_tour = []
        self.current_tour_index = -1
        if self.abort_flag:
            self.abort_flag.clear() # Clear the flag now that the abort is complete

        logger.info("Finished tour cleanup. Scheduler is now idle.")


    async def abort_tour_and_return_to_base(self):
        """
        Aborts active tour, resets DB, and calls finish_tour to return home.
        """
        logger.warning("!!! ABORTING CURRENT TOUR - Emergency Return to Base Command Received !!!")

        if self.abort_flag:
            if self.abort_flag.is_set():
                 logger.warning("Abort already in progress.")
                 return
            self.abort_flag.set()
            logger.info("Abort flag set.")
        else:
             logger.error("Cannot abort: Abort flag was not initialized.")
             # We should still try to reset the DB and go home

        # 1. Cancel active ROS goal
        if self.ros_client:
            try:
                logger.info("Attempting to cancel active ROS goals...")
                await self.ros_client.cancel_all_goals()
                logger.info("Cancel command sent to ROS goals.")
            except Exception as e:
                logger.error(f"Error sending cancel command while aborting: {e}", exc_info=True)
        else:
             logger.warning("Cannot cancel ROS goals: ROS client is not available.")

        # 2. Reset status of deliveries in DB
        logger.info("Resetting status of active deliveries in database...")
        db: Session = SessionLocal()
        try:
            deliveries_to_reset = db.query(models.Delivery).filter(
                models.Delivery.status.in_([
                    models.DeliveryStatus.SCHEDULED,
                    models.DeliveryStatus.IN_PROGRESS,
                    models.DeliveryStatus.AWAITING_PICKUP
                ])
            ).all()

            delivery_ids_to_reset = [d.id for d in deliveries_to_reset]

            if delivery_ids_to_reset:
                logger.info(f"Found active deliveries to reset to Pending: {delivery_ids_to_reset}")
                count = crud.reset_deliveries_status(db, delivery_ids=delivery_ids_to_reset)
                logger.info(f"Successfully reset status for {count} deliveries.")
            else:
                logger.info("No active deliveries found in the database to reset.")
        except Exception as e:
             logger.error(f"Error resetting delivery statuses during abort: {e}", exc_info=True)
        finally:
            db.close()

        # 3. Clear any pending pickup events
        for event in pickup_confirmation_events.values():
             event.set()
        pickup_confirmation_events.clear()
        logger.info("Cleared pending pickup confirmation events.")

        # --- *** THE FIX IS HERE *** ---
        # DO NOT reset the scheduler state here.
        # We are still "executing" the abort/return-to-base task.
        # self.is_executing_tour = False # <--- REMOVED
        # self.current_tour = [] # <--- REMOVED
        # self.current_tour_index = -1 # <--- REMOVED

        # 4. Call finish_tour. This function will now handle returning the
        #    robot AND THEN setting is_executing_tour to False.
        logger.info("Calling finish_tour to return to base and reset state...")
        await self.finish_tour()

        logger.warning("!!! Abort Tour and Return to Base sequence complete. !!!")


    def start(self, room_coords: dict, ros_client_instance: Optional[ROSClient]):
        if self._is_running:
             logger.warning("Scheduler start called, but it's already running.")
             return

        logger.info("Starting scheduler...")
        self.room_coordinates = room_coords
        self.ros_client = ros_client_instance
        self._is_running = True

        if self.ros_client:
            self.abort_flag = asyncio.Event()
            logger.info("Abort flag initialized.")
        else:
             self.abort_flag = None
             logger.warning("Scheduler started without a ROS client instance. Abort functionality may be unavailable.")

        self._task = asyncio.create_task(self._run_scheduler_loop())

    def stop(self):
        if not self._is_running:
             logger.info("Scheduler stop called, but it wasn't running.")
             return

        logger.info("Stopping scheduler...")
        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Scheduler task cancellation requested.")

        self.is_executing_tour = False
        self.current_tour = []
        self.current_tour_index = -1
        self.ros_client = None
        self.abort_flag = None

# Create the single instance
scheduler = Scheduler()