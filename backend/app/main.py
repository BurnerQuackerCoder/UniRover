import json
import asyncio
import websockets
import logging
import os # Added for path handling
from contextlib import asynccontextmanager

# --- ROS 2 Imports ---
import rclpy
from .ros_client import initialize_ros_client, ros_client as rclpy_ros_client, connection_established_event
# --- End ROS 2 Imports ---

from .scheduler import scheduler
from fastapi import FastAPI, HTTPException, status, APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from .database import engine, Base, get_db
from .core.config import settings
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from fastapi import WebSocket, WebSocketDisconnect

from .scheduler import pickup_confirmation_events # Keep this
from . import crud, schemas, models, auth, dependencies # Keep these

# --- Basic Logging Setup ---
# Configure logging level and format
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# Get logger instance for this module
logger = logging.getLogger(__name__)
# --- End Logging Setup ---


# Create database tables (consider Alembic for production migrations)
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables checked/created.")
except Exception as e:
    logger.error(f"Failed to create database tables: {e}", exc_info=True)
    # Depending on policy, you might exit here if the DB is critical
    # raise RuntimeError(f"Database initialization failed: {e}")

# Global variable for coordinates
room_coordinates = {}

# --- Updated Lifespan Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the application lifecycle: initializes and shuts down ROS 2,
    starts the ROSClient node spinning, and starts the scheduler.
    Raises RuntimeError if critical components fail to initialize.
    """
    global room_coordinates # Ensure we're modifying the global variable
    ros_initialized = False
    ros_node_started = False

    print("--- UniRover Server Starting Up ---")
    logger.info("Server starting up...")

    # Determine the correct path for room_coordinates.json based on expected CWD
    # Assuming uvicorn is run from the 'backend' directory
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # Should point to 'backend'
    coord_path = os.path.join(base_dir, "app", "room_coordinates.json")
    logger.info(f"Attempting to load room coordinates from: {coord_path}")

    # Load room coordinates FIRST - Essential for scheduler
    try:
        with open(coord_path, "r") as f:
            room_coordinates = json.load(f)
        logger.info(f"Successfully loaded {len(room_coordinates)} room coordinates.")
        if not room_coordinates:
             logger.warning("Room coordinates file loaded, but it's empty.")
        if "Base Station" not in room_coordinates:
            logger.warning("'Base Station' coordinates missing. Return to base might fail.")

    except FileNotFoundError:
        logger.critical(f"CRITICAL: Room coordinates file not found at {coord_path}. Cannot start scheduler effectively.")
        # Raise an exception to prevent startup without coordinates
        raise RuntimeError(f"Room coordinates file not found: {coord_path}")
    except json.JSONDecodeError as e:
        logger.critical(f"CRITICAL: Error decoding JSON from room coordinates file: {e}")
        raise RuntimeError(f"Invalid JSON in room coordinates file: {e}")
    except Exception as e:
        logger.critical(f"CRITICAL: Unexpected error loading room coordinates: {e}", exc_info=True)
        raise RuntimeError(f"Failed to load room coordinates: {e}")

    # --- ROS 2 Initialization ---
    if not settings.SIMULATION_MODE: # Only initialize rclpy if not in simulation mode
        try:
            logger.info("Initializing rclpy...")
            rclpy.init()
            ros_initialized = True
            logger.info("rclpy initialized successfully.")

            # Initialize our ROSClient node instance AFTER rclpy.init()
            logger.info("Initializing ROSClient node...")
            ros_node = initialize_ros_client() # This function now returns the client
            if ros_node:
                 # Start the ROS 2 node spinning in a background thread
                 ros_node.start_spinning()
                 ros_node_started = True
                 logger.info("ROSClient spinning initiated.")
            else:
                 # If initialize_ros_client somehow returns None
                 logger.critical("Failed to create ROSClient node instance.")
                 raise RuntimeError("Failed to create ROSClient node instance.")

        except Exception as e:
            logger.critical(f"CRITICAL: Error during ROS 2 setup: {e}", exc_info=True)
            # If ROS communication is essential, prevent the server from starting
            if ros_initialized and rclpy.ok(): # Attempt cleanup if init succeeded but node failed
                rclpy.shutdown()
            raise RuntimeError(f"Failed to initialize ROS 2 components: {e}")
    else:
         logger.warning("SIMULATION_MODE is True. Skipping rclpy initialization and ROSClient spinning.")
         # In simulation mode, signal readiness immediately for the scheduler
         connection_established_event.set()


    # Start the scheduler background task (pass coordinates)
    # It will internally wait for the connection_established_event from ros_client
    # or proceed immediately if in simulation mode.
    try:
        logger.info("Starting scheduler...")
        scheduler.start(room_coords=room_coordinates)
        logger.info("Scheduler started.")
    except Exception as e:
        logger.critical(f"CRITICAL: Failed to start the scheduler: {e}", exc_info=True)
        # Cleanup ROS if it started
        if ros_node_started and rclpy_ros_client:
            rclpy_ros_client.destroy_node()
        if ros_initialized and rclpy.ok():
            rclpy.shutdown()
        raise RuntimeError(f"Failed to start the scheduler: {e}")

    logger.info("--- Application startup complete. Server is live. ---")

    yield # The application runs here

    # --- Shutdown Logic ---
    print("--- UniRover Server Shutting Down ---")
    logger.info("Server shutting down...")

    # Stop scheduler first to prevent new ROS actions
    scheduler.stop()
    logger.info("Scheduler stopped.")

    # Shutdown rclpy gracefully
    if ros_initialized and rclpy.ok():
        logger.info("Shutting down rclpy...")
        if ros_node_started and rclpy_ros_client: # Check if instance exists
             logger.info("Destroying ROSClient node...")
             rclpy_ros_client.destroy_node()
        rclpy.shutdown()
        logger.info("rclpy shut down.")
    elif settings.SIMULATION_MODE:
         logger.info("SIMULATION_MODE was active. No rclpy shutdown needed.")

    logger.info("--- UniRover Server Shutdown Complete ---")
# --- End Lifespan Manager ---


# --- FastAPI App Initialization ---
app = FastAPI(
    title="UniRover Indoor Delivery API",
    description="API for managing indoor deliveries with ROS 2 Nav2 integration.",
    version="2.1.0", # Incremented version
    lifespan=lifespan # Use the updated lifespan manager
)

# CORS Middleware Configuration (remains the same)
origins = [
    "http://localhost:5173", # Standard Vite port
    "http://localhost:3000", # Common alternative
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://192.168.0.100:5173"
    # Add other origins if needed (e.g., deployed frontend URL)
]

app.add_middleware(
    CORSMiddleware,
    #allow_origins=origins,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Global Exception Handlers ---
# Keep the specific HTTPException handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Log the HTTP exception details
    logger.warning(f"HTTPException: Status={exc.status_code}, Detail='{exc.detail}' for URL: {request.url}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.detail},
        headers=getattr(exc, "headers", None) # Include headers like WWW-Authenticate if present
    )

# Keep the generic Exception handler for unhandled errors
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    # Log the full traceback for unexpected errors
    logger.error(f"Unhandled exception for URL {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"message": "An internal server error occurred."},
    )
# --- End Exception Handlers ---


# --- Routers (remain the same) ---
auth_router = APIRouter(prefix="/auth", tags=["Authentication"])
users_router = APIRouter(prefix="/users", tags=["Users"])
deliveries_router = APIRouter(tags=["Deliveries"]) # No prefix needed if endpoints start with /deliveries etc.

# --- Authentication Endpoints (remain the same) ---
@auth_router.post("/signup", response_model=schemas.UserInDB, status_code=status.HTTP_201_CREATED)
def signup(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """Registers a new user."""
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        logger.warning(f"Signup attempt failed: Email '{user.email}' already registered.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    logger.info(f"Creating new user: {user.email}")
    return crud.create_user(db=db, user=user)

@auth_router.post("/login", response_model=schemas.Token)
def login(db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticates a user and returns an access token."""
    logger.info(f"Login attempt for user: {form_data.username}")
    user = crud.get_user_by_email(db, email=form_data.username)
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        logger.warning(f"Login failed for user: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = auth.create_access_token(data={"sub": user.email})
    logger.info(f"Login successful for user: {form_data.username}")
    return {"access_token": access_token, "token_type": "bearer"}
# --- End Authentication Endpoints ---

# --- User Endpoints (remain the same) ---
@users_router.get("/me", response_model=schemas.UserInDB)
def read_users_me(current_user: models.User = Depends(dependencies.get_current_user)):
    """Retrieves the details of the currently authenticated user."""
    logger.info(f"Fetching details for user: {current_user.email}")
    return current_user
# --- End User Endpoints ---


# --- Delivery Endpoints (remain the same, but logging added) ---
@deliveries_router.post("/deliveries", response_model=schemas.DeliveryInDB, status_code=status.HTTP_201_CREATED)
def create_delivery(
    delivery: schemas.DeliveryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(dependencies.get_current_user)
):
    """Creates a new delivery request for the authenticated user."""
    logger.info(f"User '{current_user.email}' creating delivery: Item='{delivery.item}', Dest='{delivery.destination}'")
    # Basic validation: Check if destination exists in coordinates (optional but good)
    if delivery.destination not in room_coordinates:
         logger.warning(f"Delivery creation failed: Destination '{delivery.destination}' not found in coordinates.")
         # You could raise an HTTPException here, or let the scheduler handle it later
         # raise HTTPException(status_code=400, detail=f"Invalid destination: '{delivery.destination}' not recognized.")
         pass # Let scheduler mark as failed for now
    return crud.create_user_delivery(db=db, delivery=delivery, user_id=current_user.id)

@deliveries_router.get("/deliveries", response_model=list[schemas.DeliveryInDB])
def read_user_deliveries(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(dependencies.get_current_user)
):
    """Retrieves all delivery requests for the currently authenticated user."""
    logger.info(f"Fetching deliveries for user: {current_user.email}")
    return crud.get_deliveries_by_user(db=db, user_id=current_user.id)

@deliveries_router.get("/admin/deliveries", response_model=list[schemas.DeliveryWithOwner])
def read_all_deliveries(
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(dependencies.get_current_admin_user)
):
    """Retrieves all delivery requests in the system (Admin Only)."""
    logger.info(f"Admin '{admin_user.email}' fetching all deliveries.")
    return crud.get_all_deliveries(db=db)

@deliveries_router.put("/admin/deliveries/{delivery_id}", response_model=schemas.DeliveryWithOwner)
def update_delivery(
    delivery_id: int,
    status_update: schemas.DeliveryUpdate, # Renamed variable for clarity
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(dependencies.get_current_admin_user)
):
    """Updates the status of a specific delivery (Admin Only)."""
    logger.info(f"Admin '{admin_user.email}' updating delivery {delivery_id} status to '{status_update.status}'")
    updated_delivery = crud.update_delivery_status(db, delivery_id=delivery_id, status=status_update)
    if not updated_delivery:
        logger.error(f"Admin update failed: Delivery {delivery_id} not found.")
        raise HTTPException(status_code=404, detail="Delivery not found")
    return updated_delivery

@deliveries_router.post("/deliveries/{delivery_id}/confirm_pickup", status_code=status.HTTP_200_OK)
def confirm_pickup(
    delivery_id: int,
    current_user: models.User = Depends(dependencies.get_current_user) # Ensures user is logged in
    # Consider adding DB check: is this delivery owned by current_user or is it AWAITING_PICKUP?
):
    """Confirms that the user has picked up the delivery item."""
    logger.info(f"User '{current_user.email}' attempting to confirm pickup for delivery {delivery_id}")
    if delivery_id in pickup_confirmation_events:
        pickup_confirmation_events[delivery_id].set()
        logger.info(f"Pickup confirmed event set for delivery {delivery_id}")
        return {"message": "Pickup confirmed successfully."}
    else:
        # Check DB status to give better feedback
        db: Session = Depends(get_db)() # Get a DB session here if needed
        delivery = db.query(models.Delivery).filter(models.Delivery.id == delivery_id).first()
        db.close()
        if delivery and delivery.status != models.DeliveryStatus.AWAITING_PICKUP:
             logger.warning(f"Confirm pickup failed: Delivery {delivery_id} status is '{delivery.status}', not 'Awaiting Pickup'.")
             raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, # Conflict status
                detail=f"Delivery is not currently awaiting pickup (status: {delivery.status})."
             )
        else: # Delivery not found or event missing for some reason
             logger.error(f"Confirm pickup failed: Delivery {delivery_id} not found or not awaiting pickup event.")
             raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Delivery not found or not currently awaiting pickup."
             )

@deliveries_router.post("/admin/robot/return_to_base", status_code=status.HTTP_202_ACCEPTED) # Use 202 Accepted
async def command_return_to_base(
    admin_user: models.User = Depends(dependencies.get_current_admin_user)
):
    """
    (Admin Only) Asynchronously commands the robot to abort the current tour
    (if any), reset active deliveries, and return to the base station.
    """
    logger.warning(f"Admin '{admin_user.email}' initiated EMERGENCY RETURN TO BASE.")
    # Run in background and return immediately
    asyncio.create_task(scheduler.abort_tour_and_return_to_base())
    return {"message": "Command received: Aborting tour and returning to base initiated."}
# --- End Delivery Endpoints ---


# Include routers in the main app
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(deliveries_router)


# --- WebSocket Proxy Endpoint (remains the same, but added logging) ---
@app.websocket("/ws/ros")
async def websocket_proxy(frontend_ws: WebSocket):
    """
    Proxies WebSocket messages between the frontend (using roslibjs) and
    the rosbridge_server (ROS 2).
    """
    await frontend_ws.accept()
    client_host = frontend_ws.client.host if frontend_ws.client else "unknown"
    logger.info(f"Frontend WebSocket connection accepted from {client_host}.")

    rosbridge_url = settings.ROSBRIDGE_URL
    ros_ws: websockets.WebSocketClientProtocol | None = None # Initialize as None

    try:
        logger.info(f"Attempting WebSocket connection to rosbridge at {rosbridge_url}...")
        # Add a timeout to the connection attempt
        ros_ws = await asyncio.wait_for(websockets.connect(rosbridge_url), timeout=10.0)
        logger.info("WebSocket proxy successfully connected to rosbridge.")

        # Task to forward messages from frontend -> ROS
        async def forward_to_ros():
            try:
                while True:
                    message = await frontend_ws.receive_text()
                    # logger.debug(f"WS PROXY: FE -> ROS: {message[:100]}...") # Log snippet
                    if ros_ws and ros_ws.open:
                        await ros_ws.send(message)
                    else:
                        logger.warning("WS PROXY: Cannot forward to ROS, connection is closed.")
                        break # Exit if ROS connection is closed
            except WebSocketDisconnect:
                logger.info("WS PROXY: Frontend disconnected while forwarding to ROS.")
            except Exception as e_inner:
                 logger.error(f"WS PROXY: Error forwarding FE -> ROS: {e_inner}", exc_info=True)


        # Task to forward messages from ROS -> frontend
        async def forward_to_frontend():
             try:
                 # Use 'async for' for cleaner handling of messages and connection close
                 async for message in ros_ws:
                      # logger.debug(f"WS PROXY: ROS -> FE: {str(message)[:100]}...") # Log snippet
                      if frontend_ws.client_state == WebSocketState.CONNECTED:
                           await frontend_ws.send_text(message)
                      else:
                           logger.warning("WS PROXY: Cannot forward to Frontend, connection is closed.")
                           break # Exit if frontend connection is closed
             except websockets.exceptions.ConnectionClosedOK:
                  logger.info("WS PROXY: Rosbridge connection closed normally.")
             except websockets.exceptions.ConnectionClosedError as e_close:
                  logger.warning(f"WS PROXY: Rosbridge connection closed with error: {e_close}")
             except Exception as e_inner:
                  logger.error(f"WS PROXY: Error forwarding ROS -> FE: {e_inner}", exc_info=True)


        # Run both forwarding tasks concurrently
        # gather will stop when the first task finishes (e.g., due to disconnect)
        await asyncio.gather(forward_to_ros(), forward_to_frontend())

    except asyncio.TimeoutError:
         logger.error(f"WebSocket proxy failed: Timeout connecting to rosbridge at {rosbridge_url}.")
         await frontend_ws.close(code=1008, reason="Could not connect to ROS backend") # 1008 = Policy Violation
    except websockets.exceptions.InvalidURI:
         logger.error(f"WebSocket proxy failed: Invalid ROSBRIDGE_URL: {rosbridge_url}")
         await frontend_ws.close(code=1011, reason="Server configuration error") # 1011 = Internal Error
    except websockets.exceptions.WebSocketException as e_ws: # Catch specific websocket errors
         logger.error(f"WebSocket proxy error connecting to rosbridge: {e_ws}")
         await frontend_ws.close(code=1011, reason=f"ROS connection error: {e_ws}")
    except WebSocketDisconnect:
        logger.info("Frontend WebSocket disconnected before rosbridge connection could complete or during operation.")
    except Exception as e:
        # Catch-all for other unexpected errors during setup or run
        logger.error(f"Unexpected error in WebSocket proxy: {e}", exc_info=True)
        # Attempt to close the frontend connection gracefully if possible
        if frontend_ws.client_state == WebSocketState.CONNECTED:
             await frontend_ws.close(code=1011, reason="Internal server error")
    finally:
        # Ensure cleanup happens
        logger.info("WebSocket proxy closing connections.")
        if ros_ws and ros_ws.open:
            await ros_ws.close()
        # FastAPI handles closing the frontend_ws when the handler exits
        logger.info(f"Frontend WebSocket connection from {client_host} closed.")
# --- End WebSocket Proxy ---


# --- Root Endpoint (remains the same) ---
@app.get("/", tags=["Root"], summary="API Root/Health Check")
def read_root():
    """Provides a simple welcome message to verify the API is running."""
    return {"message": "Welcome to the UniRover Indoor Delivery API"}
# --- End Root Endpoint ---

# --- (Optional) Test Endpoint Cleanup ---
# Comment out or remove the old test endpoint if no longer needed
'''
@app.get("/test/send_action_goal", include_in_schema=False)
async def test_send_action_goal():
    # Ensure rclpy_ros_client is initialized and ready
    if not rclpy_ros_client or not rclpy_ros_client.is_ready:
        raise HTTPException(status_code=503, detail="ROS 2 node is not ready.")

    test_coords = {"x": 1.0, "y": -1.0, "theta": 0.0} # Added theta
    try:
        goal_id = await rclpy_ros_client.send_goal_action(test_coords)
        return {"status": "success", "detail": f"Sent NavigateToPose goal {goal_id}."}
    except ConnectionError as e:
         raise HTTPException(status_code=503, detail=f"Failed to send goal: {e}")
    except Exception as e:
        logger.error(f"Error in test endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error sending goal: {e}")
'''
# --- End Optional Test Endpoint ---

# --- WebSocket State Import (needed for robust proxy handling) ---
from starlette.websockets import WebSocketState
# --- End Import ---