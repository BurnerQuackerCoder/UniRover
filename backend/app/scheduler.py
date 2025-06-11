import asyncio
import logging
import numpy as np
from python_tsp.exact import solve_tsp_dynamic_programming
from sqlalchemy.orm import Session

from . import crud, models
from .core.config import settings
from .database import SessionLocal
#from .ros_client import ros_client # Real_mode
from .ros import ros_client # SIM_mode

# This dictionary will hold asyncio.Event objects for each delivery awaiting pickup.
# The API endpoint will use this to signal that a pickup has been confirmed.
pickup_confirmation_events = {}

logger = logging.getLogger(__name__)

class Scheduler:
    def __init__(self):
        self._task = None
        self._is_running = False
        self.is_executing_tour = False
        self.current_tour = []
        self.current_tour_index = -1
        # Load coordinates on initialization - this should be done in main.py lifespan now
        self.room_coordinates = {} 

    async def _run_scheduler_loop(self):
        """The main loop for the scheduler background task."""
        while self._is_running:
            try:
                # Only try to start a new tour if one isn't already running
                if not self.is_executing_tour:
                    logger.info("Scheduler checking for pending deliveries...")
                    
                    # 1. Check robot state (battery and connection)
                    if not ros_client._connection or ros_client.current_battery < settings.BATTERY_MIN_LEVEL:
                        logger.warning(f"Robot not ready (Connected: {ros_client._connection is not None}, Battery: {ros_client.current_battery}%)")
                        await asyncio.sleep(30)
                        continue

                    # 2. Fetch pending deliveries from DB
                    db: Session = SessionLocal()
                    pending_deliveries = crud.get_deliveries_by_status(db, status=models.DeliveryStatus.PENDING)
                    db.close()

                    # 3. Decide if a batch should be created
                    if len(pending_deliveries) >= settings.DELIVERY_BATCH_SIZE:
                        logger.info(f"Batch size reached ({len(pending_deliveries)} pending). Starting new tour.")
                        # This starts the tour but does not block the loop.
                        # The tour execution is self-managed from here.
                        asyncio.create_task(self.start_new_tour(pending_deliveries))

            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")

            await asyncio.sleep(15) # Check for new tours every 15 seconds

    async def start_new_tour(self, deliveries: list[models.Delivery]):
        """Creates and executes a new delivery tour, filtering for valid destinations."""
        if self.is_executing_tour:
            logger.warning("Attempted to start a new tour while one is already running.")
            return

        self.is_executing_tour = True
        logger.info(f"Received {len(deliveries)} deliveries to consider for new tour.")

        db: Session = SessionLocal()
        
        # --- Filter for valid deliveries ---
        valid_deliveries = []
        for d in deliveries:
            if d.destination in self.room_coordinates:
                valid_deliveries.append(d)
            else:
                logger.error(f"Destination '{d.destination}' for delivery {d.id} not found in coordinates map. Marking as Failed.")
                # Mark the invalid delivery as Failed so it's not picked up again
                crud.update_delivery_status_in_db(db, delivery_id=d.id, new_status=models.DeliveryStatus.FAILED)
        
        # If no valid deliveries are left after filtering, abort the tour creation
        if not valid_deliveries:
            logger.warning("No valid deliveries to create a tour. Aborting.")
            self.is_executing_tour = False
            db.close()
            return
            
        logger.info(f"Optimizing path for {len(valid_deliveries)} valid deliveries.")

        # --- TSP Path Optimization ---
        locations = [d.destination for d in valid_deliveries]
        all_stops = ["Base Station"] + locations
        
        distance_matrix = np.array([
            [np.linalg.norm(np.array([self.room_coordinates[p1]['x'], self.room_coordinates[p1]['y']]) - np.array([self.room_coordinates[p2]['x'], self.room_coordinates[p2]['y']])) for p2 in all_stops]
            for p1 in all_stops
        ])
        
        try:
            permutation, _ = solve_tsp_dynamic_programming(distance_matrix)
            optimized_deliveries = [valid_deliveries[all_stops.index(all_stops[i]) - 1] for i in permutation if all_stops[i] != "Base Station"]
            self.current_tour = optimized_deliveries
            logger.info(f"Optimal tour: {' -> '.join([d.destination for d in self.current_tour])}")

            for delivery in self.current_tour:
                crud.update_delivery_status_in_db(db, delivery_id=delivery.id, new_status=models.DeliveryStatus.SCHEDULED)

            self.current_tour_index = 0
            await self.execute_next_goal_in_tour()
        except Exception as e:
            logger.error(f"Failed to create tour: {e}")
            self.finish_tour() # Reset state on failure
        finally:
            db.close()

    async def execute_next_goal_in_tour(self):
        """Executes the next step in the current tour."""
        if self.current_tour_index >= len(self.current_tour):
            logger.info("All deliveries in tour completed.")
            await self.finish_tour()
            return

        delivery = self.current_tour[self.current_tour_index]
        destination_name = delivery.destination
        coords = self.room_coordinates.get(destination_name)

        if not coords:
            logger.error(f"Coordinates for '{destination_name}' not found. Skipping.")
            await self.handle_failed_arrival(delivery, reason="Invalid Destination")
            return

        # Update status and send goal
        db: Session = SessionLocal()
        crud.update_delivery_status_in_db(db, delivery_id=delivery.id, new_status=models.DeliveryStatus.IN_PROGRESS)
        db.close()
        
        await ros_client.send_goal(coords)
        result = await ros_client.wait_for_goal_result() # Wait for feedback from ros_client

        if result and result['success']:
            await self.handle_successful_arrival(delivery)
        else:
            await self.handle_failed_arrival(delivery, reason="Navigation Failed")
            
    async def handle_successful_arrival(self, delivery: models.Delivery):
        """Handles the logic after the robot successfully arrives at a destination."""
        logger.info(f"Arrived at {delivery.destination}. Awaiting pickup confirmation for 60s.")
        db: Session = SessionLocal()
        crud.update_delivery_status_in_db(db, delivery_id=delivery.id, new_status=models.DeliveryStatus.AWAITING_PICKUP)
        db.close()

        # Create an event that the API endpoint can trigger
        pickup_event = asyncio.Event()
        pickup_confirmation_events[delivery.id] = pickup_event

        try:
            await asyncio.wait_for(pickup_event.wait(), timeout=60.0)
            logger.info(f"Pickup confirmed for delivery {delivery.id}.")
            db: Session = SessionLocal()
            crud.update_delivery_status_in_db(db, delivery_id=delivery.id, new_status=models.DeliveryStatus.DELIVERED)
            db.close()
        except asyncio.TimeoutError:
            logger.warning(f"Pickup confirmation timed out for delivery {delivery.id}.")
            await self.handle_failed_arrival(delivery, reason="Missed Pickup")
        finally:
            del pickup_confirmation_events[delivery.id] # Clean up event
            self.current_tour_index += 1
            await self.execute_next_goal_in_tour() # Move to next goal

    async def handle_failed_arrival(self, delivery: models.Delivery, reason="Unknown"):
        """Handles a failed navigation attempt."""
        logger.error(f"Failed to reach {delivery.destination}. Reason: {reason}")
        db: Session = SessionLocal()
        crud.update_delivery_status_in_db(db, delivery_id=delivery.id, new_status=models.DeliveryStatus.FAILED)
        db.close()
        # Move to the next goal in the tour without stopping the whole tour
        self.current_tour_index += 1
        await self.execute_next_goal_in_tour()

    async def finish_tour(self):
        """Resets the scheduler state after a tour is finished or aborted."""
        logger.info("Finishing tour and returning to base.")
        await ros_client.return_to_base()
        self.is_executing_tour = False
        self.current_tour = []
        self.current_tour_index = -1

    def start(self, room_coords: dict):
        """Starts the scheduler as a background task."""
        logger.info("Starting scheduler...")
        self.room_coordinates = room_coords
        self._is_running = True
        self._task = asyncio.create_task(self._run_scheduler_loop())

    def stop(self):
        """Stops the scheduler background task."""
        logger.info("Stopping scheduler...")
        self._is_running = False
        if self._task:
            self._task.cancel()

    async def abort_tour_and_return_to_base(self):
        """Aborts the current tour and sends the robot home."""
        if not self.is_executing_tour:
            logger.info("Received return to base command, but no tour is active.")
            await ros_client.return_to_base() # Still send home if idle
            return

        logger.warning("ABORTING CURRENT TOUR!")
        
        # 1. Immediately stop the robot's current movement
        await ros_client.cancel_all_goals()
        
        # 2. Reset the status of all deliveries in the aborted tour to 'Pending'
        db: Session = SessionLocal()
        try:
            # Create a list of IDs for the deliveries that were part of the tour
            delivery_ids_to_reset = [d.id for d in self.current_tour]
            
            # Update their status in the database so they can be rescheduled later
            if delivery_ids_to_reset:
                crud.reset_deliveries_status(db, delivery_ids=delivery_ids_to_reset)
                logger.info(f"Reset status for deliveries: {delivery_ids_to_reset}")
        finally:
            db.close()

        # 3. Call finish_tour to reset scheduler state and send the robot to base
        await self.finish_tour()

# A single instance of the Scheduler
scheduler = Scheduler()