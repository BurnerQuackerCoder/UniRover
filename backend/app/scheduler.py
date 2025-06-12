import asyncio
import logging
import numpy as np
from python_tsp.exact import solve_tsp_dynamic_programming
from sqlalchemy.orm import Session
from .ros_client import connection_established_event
from . import crud, models
from .core.config import settings
from .database import SessionLocal
from .ros import ros_client

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
        # --- FIX: Initialize the abort_flag as None here ---
        self.abort_flag: asyncio.Event | None = None

    async def _run_scheduler_loop(self):
        """
        The main loop for the scheduler background task. It now waits for the ROS
        connection to be ready before starting its main scheduling logic.
        """
        # This line will pause the scheduler indefinitely until the ROSClient
        # successfully connects and signals the event.
        logger.info("Scheduler is waiting for ROS connection to be established...")
        await connection_established_event.wait()
        logger.info("ROS connection established. Scheduler is now active and will check for deliveries.")
        
        while self._is_running:
            try:
                if not self.is_executing_tour:
                    if settings.ENFORCE_BATTERY_CHECK and (not ros_client.connection or ros_client.current_battery < settings.BATTERY_MIN_LEVEL):
                        await asyncio.sleep(30)
                        continue

                    db: Session = SessionLocal()
                    pending_deliveries = crud.get_deliveries_by_status(db, status=models.DeliveryStatus.PENDING)
                    db.close()

                    if len(pending_deliveries) >= settings.DELIVERY_BATCH_SIZE:
                        asyncio.create_task(self.start_new_tour(pending_deliveries))
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)
            await asyncio.sleep(15)

    async def start_new_tour(self, deliveries: list[models.Delivery]):
        if self.is_executing_tour: return
        if not self.abort_flag: return # Safety check

        self.abort_flag.clear()
        self.is_executing_tour = True
        
        db: Session = SessionLocal()
        try:
            valid_deliveries = [d for d in deliveries if d.destination in self.room_coordinates]
            # ... (rest of the method is the same)
            locations = [d.destination for d in valid_deliveries]
            all_stops = ["Base Station"] + locations
            distance_matrix = np.array([[np.linalg.norm(np.array([self.room_coordinates[p1]['x'], self.room_coordinates[p1]['y']]) - np.array([self.room_coordinates[p2]['x'], self.room_coordinates[p2]['y']])) for p2 in all_stops] for p1 in all_stops])
            permutation, _ = solve_tsp_dynamic_programming(distance_matrix)
            self.current_tour = [valid_deliveries[all_stops.index(all_stops[i]) - 1] for i in permutation if all_stops[i] != "Base Station"]
            
            for delivery in self.current_tour:
                crud.update_delivery_status_in_db(db, delivery_id=delivery.id, new_status=models.DeliveryStatus.SCHEDULED)

            self.current_tour_index = 0
            await self.execute_next_goal_in_tour()
        except Exception as e:
            logger.error(f"Failed to create tour: {e}", exc_info=True)
            await self.finish_tour()
        finally:
            db.close()

    async def execute_next_goal_in_tour(self):
        """Executes the next step in the current tour, with improved logging."""
        if self.abort_flag.is_set():
            logger.warning("Abort detected. Halting tour.")
            return

        if self.current_tour_index >= len(self.current_tour):
            await self.finish_tour()
            return

        delivery = self.current_tour[self.current_tour_index]
        coords = self.room_coordinates.get(delivery.destination)

        if not coords:
            await self.handle_failed_arrival(delivery, reason="Invalid Destination")
            return

        db: Session = SessionLocal()
        crud.update_delivery_status_in_db(db, delivery_id=delivery.id, new_status=models.DeliveryStatus.IN_PROGRESS)
        db.close()
        
        try:
            goal_id = await ros_client.send_goal_action(coords)
            result = await ros_client.wait_for_goal_result(goal_id)
        except ConnectionError as e:
            logger.error(f"Cannot execute goal due to connection error: {e}")
            result = {"success": False}
        
        if self.abort_flag.is_set():
            logger.warning("Abort detected after goal result. Halting tour.")
            return

        # --- THIS IS THE NEW LOGGING SECTION ---
        if result and result.get('success'):
            logger.info(f"✅ Goal for delivery #{delivery.id} to '{delivery.destination}' reached successfully.")
            await self.handle_successful_arrival(delivery)
        else:
            logger.error(f"❌ Goal for delivery #{delivery.id} to '{delivery.destination}' failed.")
            await self.handle_failed_arrival(delivery, reason="Navigation Failed or Timed Out")

    async def handle_successful_arrival(self, delivery: models.Delivery):
        db: Session = SessionLocal()
        crud.update_delivery_status_in_db(db, delivery_id=delivery.id, new_status=models.DeliveryStatus.AWAITING_PICKUP)
        db.close()
        pickup_event = asyncio.Event()
        pickup_confirmation_events[delivery.id] = pickup_event
        try:
            await asyncio.wait_for(pickup_event.wait(), timeout=60.0)
            if not self.abort_flag or self.abort_flag.is_set(): return
            db_session = SessionLocal()
            crud.update_delivery_status_in_db(db_session, delivery_id=delivery.id, new_status=models.DeliveryStatus.DELIVERED)
            db_session.close()
        except asyncio.TimeoutError:
            if not self.abort_flag or self.abort_flag.is_set(): return
            await self.handle_failed_arrival(delivery, reason="Missed Pickup")
        finally:
            pickup_confirmation_events.pop(delivery.id, None)
            self.current_tour_index += 1
            await self.execute_next_goal_in_tour()

    async def handle_failed_arrival(self, delivery: models.Delivery, reason="Unknown"):
        if not self.abort_flag or self.abort_flag.is_set(): return
        db: Session = SessionLocal()
        crud.update_delivery_status_in_db(db, delivery_id=delivery.id, new_status=models.DeliveryStatus.FAILED)
        db.close()
        self.current_tour_index += 1
        await self.execute_next_goal_in_tour()

    async def finish_tour(self):
        """
        Resets scheduler state and ensures robot has returned to base before
        allowing new tours to be scheduled.
        """
        logger.info("Finishing tour and returning to base.")
        self.is_executing_tour = False
        self.current_tour = []
        self.current_tour_index = -1
        
        try:
            # Send the robot home and get the goal_id
            goal_id = await ros_client.return_to_base()
            if goal_id:
                # IMPORTANT: Wait for the robot to confirm it has reached the base
                logger.info(f"Waiting for robot to arrive at base (goal: {goal_id})...")
                await ros_client.wait_for_goal_result(goal_id)
                logger.info("Robot has arrived at base station. Scheduler is now idle.")
        except ConnectionError as e:
            logger.error(f"Could not command return to base: {e}")

    async def abort_tour_and_return_to_base(self):
        """
        Aborts any active tour by querying the database for active deliveries,
        resetting their status, and commanding the robot to return home.
        """
        logger.warning("ABORTING CURRENT TOUR! Received emergency return to base command.")
        if self.abort_flag:
            self.abort_flag.set()

        # Cancel any movement command the robot is currently executing.
        try:
            await ros_client.cancel_all_goals()
        except ConnectionError as e:
            logger.error(f"Could not send cancel command while aborting: {e}")

        # --- This is the new, robust logic ---
        db: Session = SessionLocal()
        try:
            # Query the database for ANY delivery that is currently part of a tour.
            deliveries_to_reset = db.query(models.Delivery).filter(
                models.Delivery.status.in_([
                    models.DeliveryStatus.SCHEDULED,
                    models.DeliveryStatus.IN_PROGRESS,
                    models.DeliveryStatus.AWAITING_PICKUP
                ])
            ).all()

            delivery_ids_to_reset = [d.id for d in deliveries_to_reset]
            
            if delivery_ids_to_reset:
                logger.info(f"Found active deliveries to reset: {delivery_ids_to_reset}")
                # Use the existing CRUD function to reset them all to Pending.
                crud.reset_deliveries_status(db, delivery_ids=delivery_ids_to_reset)
            else:
                logger.info("No active deliveries found in the database to reset.")
        finally:
            db.close()

        # Call finish_tour to reset the scheduler's internal state and send the robot home.
        await self.finish_tour()

    def start(self, room_coords: dict):
        logger.info("Starting scheduler...")
        self.room_coordinates = room_coords
        self._is_running = True
        # --- FIX: Create the Event object here, inside the running async context ---
        self.abort_flag = asyncio.Event()
        self._task = asyncio.create_task(self._run_scheduler_loop())

    def stop(self):
        self._is_running = False
        if self._task:
            self._task.cancel()

scheduler = Scheduler()