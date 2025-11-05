import asyncio
import logging
import numpy as np
from python_tsp.exact import solve_tsp_dynamic_programming
from sqlalchemy.orm import Session
from typing import Optional # Added for type hinting

# This event is signaled by ros_client when it's ready (spinning)
from .ros_client import connection_established_event, ROSClient # Import class for type hint
from . import crud, models
from .core.config import settings
from .database import SessionLocal
# REMOVED: from .ros import ros_client

# Dictionary for pickup confirmation events remains the same
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
        # ADDED: Instance variable to hold the ROSClient
        self.ros_client: Optional[ROSClient] = None

    async def _run_scheduler_loop(self):
        """
        The main loop for the scheduler. Waits for ROS readiness, then checks for
        deliveries based on robot status and batch size.
        """
        logger.info("Scheduler waiting for ROS connection/readiness signal...")
        await connection_established_event.wait() # Wait for signal from ros_client spin thread
        logger.info("ROS connection/readiness signal received. Scheduler is now active.")

        while self._is_running:
            try:
                if not self.is_executing_tour:
                    # MODIFIED: Check battery/connection using self.ros_client
                    client_available = self.ros_client is not None and self.ros_client.is_ready
                    battery_level = self.ros_client.current_battery if client_available else -1.0 # Get battery if available
                    battery_ok = not settings.ENFORCE_BATTERY_CHECK or (client_available and battery_level >= settings.BATTERY_MIN_LEVEL)

                    if not battery_ok:
                         # Log detailed status
                         logger.warning(f"Robot not ready to start tour (Enforce Battery Check: {settings.ENFORCE_BATTERY_CHECK}, ROS Client Ready: {client_available}, Battery: {battery_level:.1f}%)")
                         await asyncio.sleep(30) # Wait longer if robot isn't ready
                         continue
                    # END MODIFICATION

                    # Fetch pending deliveries
                    db: Session = SessionLocal()
                    try: # Add try/finally for DB session
                        pending_deliveries = crud.get_deliveries_by_status(db, status=models.DeliveryStatus.PENDING)
                    finally:
                        db.close()

                    # Start tour if batch size reached
                    if len(pending_deliveries) >= settings.DELIVERY_BATCH_SIZE:
                        logger.info(f"Batch size ({settings.DELIVERY_BATCH_SIZE}) reached with {len(pending_deliveries)} pending deliveries. Starting new tour.")
                        # Run start_new_tour in the background
                        asyncio.create_task(self.start_new_tour(pending_deliveries))
                    # else: # Optional: Log if not starting
                    #     logger.debug(f"Only {len(pending_deliveries)} pending deliveries. Waiting for batch size ({settings.DELIVERY_BATCH_SIZE}).")

            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)
            await asyncio.sleep(15) # Check interval

    async def start_new_tour(self, deliveries: list[models.Delivery]):
        """Creates and executes a new delivery tour."""
        if self.is_executing_tour:
            logger.warning("Attempted to start a new tour while one is already in progress.")
            return
        if self.abort_flag is None and self.ros_client is not None:
             logger.error("Scheduler started with ROS client but abort_flag is None. Cannot start tour.")
             return # Safety check

        if self.abort_flag:
            self.abort_flag.clear() # Ensure abort flag is clear at the start of a tour

        self.is_executing_tour = True
        logger.info(f"Starting new tour creation with {len(deliveries)} potential deliveries.")

        db: Session = SessionLocal()
        try:
            # Filter for valid destinations
            valid_deliveries = []
            for d in deliveries:
                if d.destination in self.room_coordinates:
                    valid_deliveries.append(d)
                else:
                    logger.error(f"Destination '{d.destination}' for delivery #{d.id} not found in coordinates map. Marking as Failed.")
                    crud.update_delivery_status_in_db(db, delivery_id=d.id, new_status=models.DeliveryStatus.FAILED)

            if not valid_deliveries:
                logger.warning("No valid deliveries found after filtering. Aborting tour creation.")
                self.is_executing_tour = False # Reset state
                return # Exit early

            logger.info(f"Optimizing path for {len(valid_deliveries)} valid deliveries.")
            locations = [d.destination for d in valid_deliveries]
            all_stops = ["Base Station"] + locations

            # Check if Base Station coordinates exist before creating matrix
            if "Base Station" not in self.room_coordinates:
                 logger.error("Cannot calculate TSP: 'Base Station' coordinates missing.")
                 raise ValueError("'Base Station' coordinates missing.")

            # Calculate distance matrix
            try:
                distance_matrix = np.array([
                    [np.linalg.norm(np.array([self.room_coordinates[p1]['x'], self.room_coordinates[p1]['y']]) - np.array([self.room_coordinates[p2]['x'], self.room_coordinates[p2]['y']])) for p2 in all_stops]
                    for p1 in all_stops
                ])
            except KeyError as e:
                 logger.error(f"Cannot calculate TSP: Coordinate key error - {e}. Check room_coordinates.json.")
                 raise ValueError(f"Missing coordinate for TSP calculation: {e}")


            permutation, _ = solve_tsp_dynamic_programming(distance_matrix)
            # Ensure correct mapping back to deliveries list
            self.current_tour = []
            valid_delivery_map = {d.destination: d for d in valid_deliveries} # Map destination name to delivery object
            for i in permutation:
                 stop_name = all_stops[i]
                 if stop_name != "Base Station":
                      # Find the corresponding original delivery object
                      # This assumes destinations in valid_deliveries are unique within a batch
                      delivery_obj = next((d for d in valid_deliveries if d.destination == stop_name), None)
                      if delivery_obj:
                          self.current_tour.append(delivery_obj)
                      else: # Should not happen if logic is correct
                           logger.error(f"Could not map TSP stop '{stop_name}' back to a valid delivery object.")


            route_str = ' -> '.join([d.destination for d in self.current_tour])
            logger.info(f"Optimized route: Base Station -> {route_str} -> Base Station (implicitly)")

            # Mark deliveries as Scheduled
            for delivery in self.current_tour:
                crud.update_delivery_status_in_db(db, delivery_id=delivery.id, new_status=models.DeliveryStatus.SCHEDULED)

            # Start executing the first goal
            self.current_tour_index = 0
            await self.execute_next_goal_in_tour()

        except Exception as e:
            logger.error(f"Failed during tour creation or initial execution: {e}", exc_info=True)
            # Attempt to reset deliveries that might have been marked Scheduled
            try:
                 ids_to_reset = [d.id for d in self.current_tour if d.status == models.DeliveryStatus.SCHEDULED]
                 if ids_to_reset:
                      crud.reset_deliveries_status(db, delivery_ids=ids_to_reset)
                      logger.info(f"Reset status for deliveries due to tour creation failure: {ids_to_reset}")
            except Exception as reset_e:
                 logger.error(f"Failed to reset delivery statuses after tour creation error: {reset_e}")
            await self.finish_tour() # Ensure state reset and return to base attempt
        finally:
            db.close()

    async def execute_next_goal_in_tour(self):
        """Executes the next step in the current tour, using self.ros_client."""
        # Check for abort signal FIRST
        if self.abort_flag and self.abort_flag.is_set():
            logger.warning("Abort detected before executing next goal. Halting tour.")
            # Do not proceed, finish_tour will be called by the abort function
            return

        if self.current_tour_index >= len(self.current_tour):
            logger.info("Tour completed. Finishing up.")
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
        # MODIFIED: Use self.ros_client and check its existence
        if self.ros_client:
            try:
                logger.info(f"Sending goal for delivery #{delivery.id} to {delivery.destination} ({coords})")
                goal_id = await self.ros_client.send_goal_action(coords)
                # Wait for result, potentially long timeout needed depending on distance
                result = await self.ros_client.wait_for_goal_result(goal_id, timeout=settings.NAVIGATION_TIMEOUT_SECONDS) # Add timeout config
            except ConnectionError as e:
                logger.error(f"Cannot execute goal for delivery #{delivery.id} due to connection error: {e}")
                result = {"success": False, "error": f"Connection Error: {e}"}
            except Exception as e:
                logger.error(f"Error during goal execution (send/wait) for delivery #{delivery.id}: {e}", exc_info=True)
                result = {"success": False, "error": f"Execution Error: {e}"}
        else:
             logger.error(f"Cannot execute goal for delivery #{delivery.id}: ROS client is not available.")
             result = {"success": False, "error": "ROS Client Unavailable"}
        # END MODIFICATION

        # Check abort signal AGAIN after potentially long wait_for_goal_result
        if self.abort_flag and self.abort_flag.is_set():
            logger.warning("Abort detected after goal result/error. Halting tour processing.")
            # Do not proceed to next steps, finish_tour will be called by abort function
            return

        # Process result
        if result and result.get('success'):
            logger.info(f"✅ SUCCESS: Navigation goal for delivery #{delivery.id} (Item: '{delivery.item}') to '{delivery.destination}' reported success.")
            await self.handle_successful_arrival(delivery)
        else:
            reason = result.get("error", "Navigation Failed or Timed Out") if result else "Unknown ROS Client Error"
            logger.error(f"❌ FAILURE: Navigation goal for delivery #{delivery.id} (Item: '{delivery.item}') to '{delivery.destination}' failed. Reason: {reason}")
            await self.handle_failed_arrival(delivery, reason=reason)

    async def handle_successful_arrival(self, delivery: models.Delivery):
        """Handles logic after successful arrival, including pickup wait."""
        # Check abort flag before proceeding
        if self.abort_flag and self.abort_flag.is_set():
             logger.warning(f"Abort detected upon arrival at {delivery.destination}. Skipping pickup wait.")
             return # Don't wait for pickup if aborted

        logger.info(f"Arrived at {delivery.destination} for delivery #{delivery.id}. Awaiting pickup confirmation ({settings.PICKUP_TIMEOUT_SECONDS}s).") # Add config
        db: Session = SessionLocal()
        try:
            crud.update_delivery_status_in_db(db, delivery_id=delivery.id, new_status=models.DeliveryStatus.AWAITING_PICKUP)
        finally:
            db.close()

        pickup_event = asyncio.Event()
        pickup_confirmation_events[delivery.id] = pickup_event

        try:
            # Wait for confirmation or timeout
            await asyncio.wait_for(pickup_event.wait(), timeout=settings.PICKUP_TIMEOUT_SECONDS) # Use config

            # Check abort flag AGAIN after waiting
            if self.abort_flag and self.abort_flag.is_set():
                 logger.warning(f"Abort detected after pickup confirmation for delivery {delivery.id}. Not marking as Delivered.")
                 # Note: Status remains AWAITING_PICKUP. Abort logic will reset it.
                 return

            logger.info(f"Pickup confirmed for delivery #{delivery.id}.")
            db_session = SessionLocal()
            try:
                crud.update_delivery_status_in_db(db_session, delivery_id=delivery.id, new_status=models.DeliveryStatus.DELIVERED)
            finally:
                db_session.close()

            # Successfully delivered, move to next
            self.current_tour_index += 1
            await self.execute_next_goal_in_tour()

        except asyncio.TimeoutError:
            # Check abort flag AGAIN after timeout
            if self.abort_flag and self.abort_flag.is_set():
                 logger.warning(f"Abort detected after pickup timeout for delivery {delivery.id}.")
                 return

            logger.warning(f"Pickup confirmation timed out for delivery #{delivery.id}. Marking as Failed.")
            # Pickup failed, treat as failed arrival for this step
            await self.handle_failed_arrival(delivery, reason="Pickup Timeout")

        finally:
            # Clean up event regardless of outcome
            pickup_confirmation_events.pop(delivery.id, None)


    async def handle_failed_arrival(self, delivery: models.Delivery, reason="Unknown"):
        """Handles failed navigation or pickup timeout."""
        # Check abort flag - if aborted, the main abort logic handles DB updates
        if self.abort_flag and self.abort_flag.is_set():
             logger.info(f"Abort detected during failed arrival handling for delivery #{delivery.id}. Abort logic will reset status.")
             return # Don't update DB here if aborting

        logger.error(f"Handling failed step for delivery #{delivery.id} to {delivery.destination}. Reason: {reason}. Marking as FAILED.")
        db: Session = SessionLocal()
        try:
            crud.update_delivery_status_in_db(db, delivery_id=delivery.id, new_status=models.DeliveryStatus.FAILED)
        finally:
            db.close()

        # Move to the next destination in the tour
        self.current_tour_index += 1
        logger.info(f"Moving to next step in tour after failure of delivery #{delivery.id}.")
        await self.execute_next_goal_in_tour()

    async def finish_tour(self):
        """Resets scheduler state and attempts to return robot to base."""
        # This function might be called after success, failure, or during abort cleanup.
        logger.info("Finishing current tour execution cycle.")
        is_aborting = self.abort_flag and self.abort_flag.is_set()

        # Reset internal state only if not currently aborting (abort handles its own state reset)
        # However, we DO want to send the robot home in both cases if possible.
        if not is_aborting:
             self.is_executing_tour = False
             self.current_tour = []
             self.current_tour_index = -1
             logger.info("Scheduler state reset (idle).")


        logger.info("Attempting to command robot return to Base Station.")
        # MODIFIED: Use self.ros_client
        if self.ros_client:
            try:
                goal_id = await self.ros_client.return_to_base()
                if goal_id:
                    logger.info(f"Return to base goal ({goal_id}) sent. Waiting for completion...")
                    # Give ample time for return journey
                    await self.ros_client.wait_for_goal_result(goal_id, timeout=settings.RETURN_TO_BASE_TIMEOUT_SECONDS) # Add config
                    logger.info(f"Return to base goal ({goal_id}) likely completed.")
                else:
                    logger.warning("Could not initiate return to base (return_to_base returned None). Base coords ok?")
            except ConnectionError as e:
                logger.error(f"Could not command return to base due to connection error: {e}")
            except Exception as e:
                logger.error(f"Error during return to base process: {e}", exc_info=True)
        else:
             logger.warning("Cannot return robot to base: ROS client is not available.")
        # END MODIFICATION

        if is_aborting:
             logger.info("Finished return-to-base attempt during abort sequence.")
        else:
             logger.info("Finished tour cleanup and return-to-base attempt.")


    async def abort_tour_and_return_to_base(self):
        """
        Aborts any active tour, resets relevant delivery statuses,
        and commands the robot home.
        """
        logger.warning("!!! ABORTING CURRENT TOUR - Emergency Return to Base Command Received !!!")

        if self.abort_flag:
            if self.abort_flag.is_set():
                 logger.warning("Abort already in progress.")
                 return # Avoid redundant aborts
            self.abort_flag.set() # Signal other tasks like execute_next_goal to stop
            logger.info("Abort flag set.")
        else:
             logger.error("Cannot abort: Abort flag was not initialized (likely no ROS client).")
             # Still attempt DB reset and finish_tour without cancellation
             pass

        # MODIFIED: Use self.ros_client to cancel goals
        if self.ros_client:
            try:
                logger.info("Attempting to cancel active ROS goals...")
                await self.ros_client.cancel_all_goals()
                logger.info("Cancel command sent to ROS goals.")
            except ConnectionError as e:
                logger.error(f"Could not send cancel command while aborting (ConnectionError): {e}")
            except Exception as e:
                logger.error(f"Error sending cancel command while aborting: {e}", exc_info=True)
        else:
             logger.warning("Cannot cancel ROS goals: ROS client is not available.")
        # END MODIFICATION

        # Reset status of deliveries currently part of the tour/system active states
        logger.info("Resetting status of active deliveries in database...")
        db: Session = SessionLocal()
        try:
            # Query deliveries that are SCHEDULED, IN_PROGRESS, or AWAITING_PICKUP
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

        # Clear any pending pickup confirmation events immediately
        for event in pickup_confirmation_events.values():
             event.set() # Wake up any waiting tasks so they see the abort flag
        pickup_confirmation_events.clear()
        logger.info("Cleared pending pickup confirmation events.")


        # Reset internal scheduler state AFTER resetting DB and canceling goals
        self.is_executing_tour = False
        self.current_tour = []
        self.current_tour_index = -1
        logger.info("Internal scheduler state reset for abort.")

        # Finally, call finish_tour to handle the return to base command
        # finish_tour now checks self.ros_client itself
        await self.finish_tour()
        logger.warning("!!! Abort Tour and Return to Base sequence complete. !!!")


    # MODIFIED: start method signature
    def start(self, room_coords: dict, ros_client_instance: Optional[ROSClient]):
        """Starts the scheduler, storing the ROS client instance."""
        if self._is_running:
             logger.warning("Scheduler start called, but it's already running.")
             return

        logger.info("Starting scheduler...")
        self.room_coordinates = room_coords
        self.ros_client = ros_client_instance # Store the passed instance
        self._is_running = True

        # Initialize abort flag only if we have a client
        if self.ros_client:
            self.abort_flag = asyncio.Event()
            logger.info("Abort flag initialized.")
        else:
             self.abort_flag = None
             logger.warning("Scheduler started without a ROS client instance. Abort functionality may be unavailable.")

        self._task = asyncio.create_task(self._run_scheduler_loop())
    # END MODIFICATION

    def stop(self):
        """Stops the scheduler background task."""
        if not self._is_running:
             logger.info("Scheduler stop called, but it wasn't running.")
             return

        logger.info("Stopping scheduler...")
        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Scheduler task cancellation requested.")
        # Reset state variables on stop as well
        self.is_executing_tour = False
        self.current_tour = []
        self.current_tour_index = -1
        self.ros_client = None # Clear client reference
        self.abort_flag = None

# Create the single instance of the Scheduler
scheduler = Scheduler()