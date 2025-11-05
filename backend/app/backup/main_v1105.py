import json
import asyncio
import websockets
import logging
import os # Added for path handling
from contextlib import asynccontextmanager

# --- ROS 2 Imports ---
import rclpy
# Corrected import from previous step
from .ros_client import ROSClient, connection_established_event
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
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# --- End Logging Setup ---

# Create database tables
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables checked/created.")
except Exception as e:
    logger.error(f"Failed to create database tables: {e}", exc_info=True)
    raise RuntimeError(f"Database initialization failed: {e}")

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
    global room_coordinates
    ros_initialized = False
    ros_node_started = False
    # Use the consistent variable name throughout
    ros_node_instance: Optional[ROSClient] = None

    print("--- UniRover Server Starting Up ---")
    logger.info("Server starting up...")

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    coord_path = os.path.join(base_dir, "app", "room_coordinates.json")
    logger.info(f"Attempting to load room coordinates from: {coord_path}")

    # Load room coordinates
    try:
        with open(coord_path, "r") as f:
            room_coordinates = json.load(f)
        logger.info(f"Successfully loaded {len(room_coordinates)} room coordinates.")
        if not room_coordinates:
             logger.warning("Room coordinates file loaded, but it's empty.")
        if "Base Station" not in room_coordinates:
            logger.warning("'Base Station' coordinates missing. Return to base might fail.")
    except FileNotFoundError:
        logger.critical(f"CRITICAL: Room coordinates file not found at {coord_path}.")
        raise RuntimeError(f"Room coordinates file not found: {coord_path}")
    except json.JSONDecodeError as e:
        logger.critical(f"CRITICAL: Error decoding JSON from room coordinates file: {e}")
        raise RuntimeError(f"Invalid JSON in room coordinates file: {e}")
    except Exception as e:
        logger.critical(f"CRITICAL: Unexpected error loading room coordinates: {e}", exc_info=True)
        raise RuntimeError(f"Failed to load room coordinates: {e}")

    # --- ROS 2 Initialization ---
    if not settings.SIMULATION_MODE:
        try:
            logger.info("Initializing rclpy...")
            rclpy.init()
            ros_initialized = True
            logger.info("rclpy initialized successfully.")

            logger.info("Initializing ROSClient node...")
            ros_node_instance = ROSClient() # Create instance directly

            if ros_node_instance:
                 ros_node_instance.start_spinning()
                 ros_node_started = True
                 logger.info("ROSClient spinning initiated.")
            else:
                 logger.critical("Failed to create ROSClient node instance.")
                 raise RuntimeError("Failed to create ROSClient node instance.")

        except Exception as e:
            logger.critical(f"CRITICAL: Error during ROS 2 setup: {e}", exc_info=True)
            # --- FIX IS HERE: Check ros_node_instance in except block ---
            # Attempt cleanup using the correct variable name
            if ros_node_started and ros_node_instance: # Check if instance exists before destroying
                 ros_node_instance.destroy_node() # Destroy the node if spinning started
            # --- END FIX ---
            if ros_initialized and rclpy.ok(): # Attempt rclpy shutdown if init succeeded
                rclpy.shutdown()
            raise RuntimeError(f"Failed to initialize ROS 2 components: {e}")
    else:
         logger.warning("SIMULATION_MODE is True. Skipping rclpy initialization and ROSClient spinning.")
         connection_established_event.set()

    # Start the scheduler background task
    try:
        logger.info("Starting scheduler...")
        # Pass the instance (or None if in SIM_MODE/error)
        scheduler.start(room_coords=room_coordinates, ros_client_instance=ros_node_instance)
        logger.info("Scheduler started.")
    except Exception as e:
        logger.critical(f"CRITICAL: Failed to start the scheduler: {e}", exc_info=True)
        # Cleanup ROS if it started
        if ros_node_started and ros_node_instance:
            ros_node_instance.destroy_node()
        if ros_initialized and rclpy.ok():
            rclpy.shutdown()
        raise RuntimeError(f"Failed to start the scheduler: {e}")

    logger.info("--- Application startup complete. Server is live. ---")

    yield # The application runs here

    # --- Shutdown Logic ---
    print("--- UniRover Server Shutting Down ---")
    logger.info("Server shutting down...")

    scheduler.stop()
    logger.info("Scheduler stopped.")

    if ros_initialized and rclpy.ok():
        logger.info("Shutting down rclpy...")
        if ros_node_started and ros_node_instance:
             logger.info("Destroying ROSClient node...")
             ros_node_instance.destroy_node()
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
    lifespan=lifespan
)

# CORS Middleware Configuration
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173", # Make sure this is present
    # Add other origins if needed
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, # Use the specific list
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Global Exception Handlers ---
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning(f"HTTPException: Status={exc.status_code}, Detail='{exc.detail}' for URL: {request.url}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.detail},
        headers=getattr(exc, "headers", None)
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception for URL {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"message": "An internal server error occurred."},
    )
# --- End Exception Handlers ---


# --- Routers ---
auth_router = APIRouter(prefix="/auth", tags=["Authentication"])
users_router = APIRouter(prefix="/users", tags=["Users"])
deliveries_router = APIRouter(tags=["Deliveries"])

# --- Authentication Endpoints ---
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
    # Uses the TEMPORARY plain text comparison from auth.py
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

# --- User Endpoints ---
@users_router.get("/me", response_model=schemas.UserInDB)
def read_users_me(current_user: models.User = Depends(dependencies.get_current_user)):
    """Retrieves the details of the currently authenticated user."""
    logger.info(f"Fetching details for user: {current_user.email}")
    return current_user
# --- End User Endpoints ---


# --- Delivery Endpoints ---
@deliveries_router.post("/deliveries", response_model=schemas.DeliveryInDB, status_code=status.HTTP_201_CREATED)
def create_delivery(
    delivery: schemas.DeliveryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(dependencies.get_current_user)
):
    """Creates a new delivery request for the authenticated user."""
    logger.info(f"User '{current_user.email}' creating delivery: Item='{delivery.item}', Dest='{delivery.destination}'")
    if delivery.destination not in room_coordinates:
         logger.warning(f"Delivery creation attempt with invalid destination '{delivery.destination}'. Allowing, scheduler will handle.")
         pass # Let scheduler mark as failed
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
    status_update: schemas.DeliveryUpdate,
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
    current_user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(get_db) # Add DB dependency to check status
):
    """Confirms that the user has picked up the delivery item."""
    logger.info(f"User '{current_user.email}' attempting to confirm pickup for delivery {delivery_id}")
    if delivery_id in pickup_confirmation_events:
        pickup_confirmation_events[delivery_id].set()
        logger.info(f"Pickup confirmed event set for delivery {delivery_id}")
        return {"message": "Pickup confirmed successfully."}
    else:
        delivery = db.query(models.Delivery).filter(models.Delivery.id == delivery_id).first()
        if delivery and delivery.status != models.DeliveryStatus.AWAITING_PICKUP:
             logger.warning(f"Confirm pickup failed: Delivery {delivery_id} status is '{delivery.status}', not 'Awaiting Pickup'.")
             raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Delivery is not currently awaiting pickup (status: {delivery.status})."
             )
        else:
             logger.error(f"Confirm pickup failed: Delivery {delivery_id} not found or not awaiting pickup event.")
             raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Delivery not found or not currently awaiting pickup."
             )

@deliveries_router.post("/admin/robot/return_to_base", status_code=status.HTTP_202_ACCEPTED)
async def command_return_to_base(
    admin_user: models.User = Depends(dependencies.get_current_admin_user)
):
    """
    (Admin Only) Asynchronously commands the robot to abort the current tour
    (if any), reset active deliveries, and return to the base station.
    """
    logger.warning(f"Admin '{admin_user.email}' initiated EMERGENCY RETURN TO BASE.")
    asyncio.create_task(scheduler.abort_tour_and_return_to_base())
    return {"message": "Command received: Aborting tour and returning to base initiated."}
# --- End Delivery Endpoints ---


# Include routers in the main app
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(deliveries_router)


# --- WebSocket Proxy Endpoint ---
# (Added WebSocketState import at the bottom)
'''@app.websocket("/ws/ros")
async def websocket_proxy(frontend_ws: WebSocket):
    """
    Proxies WebSocket messages between the frontend (using roslibjs) and
    the rosbridge_server (ROS 2).
    """
    await frontend_ws.accept()
    client_host = frontend_ws.client.host if frontend_ws.client else "unknown"
    logger.info(f"Frontend WebSocket connection accepted from {client_host}.")

    rosbridge_url = settings.ROSBRIDGE_URL
    ros_ws: websockets.WebSocketClientProtocol | None = None

    try:
        logger.info(f"Attempting WebSocket connection to rosbridge at {rosbridge_url}...")
        ros_ws = await asyncio.wait_for(websockets.connect(rosbridge_url), timeout=10.0)
        logger.info("WebSocket proxy successfully connected to rosbridge.")

        async def forward_to_ros():
            try:
                while True:
                    message = await frontend_ws.receive_text()
                    if ros_ws and not ros_ws.close:
                        await ros_ws.send(message)
                    else:
                        logger.warning("WS PROXY: Cannot forward to ROS, connection is closed.")
                        break
            except WebSocketDisconnect:
                logger.info("WS PROXY: Frontend disconnected while forwarding to ROS.")
            except Exception as e_inner:
                 logger.error(f"WS PROXY: Error forwarding FE -> ROS: {e_inner}", exc_info=True)

        async def forward_to_frontend():
             try:
                 async for message in ros_ws:
                      if frontend_ws.client_state == WebSocketState.CONNECTED:
                           await frontend_ws.send_text(message)
                      else:
                           logger.warning("WS PROXY: Cannot forward to Frontend, connection is closed.")
                           break
             except websockets.exceptions.ConnectionClosedOK:
                  logger.info("WS PROXY: Rosbridge connection closed normally.")
             except websockets.exceptions.ConnectionClosedError as e_close:
                  logger.warning(f"WS PROXY: Rosbridge connection closed with error: {e_close}")
             except Exception as e_inner:
                  logger.error(f"WS PROXY: Error forwarding ROS -> FE: {e_inner}", exc_info=True)

        await asyncio.gather(forward_to_ros(), forward_to_frontend())

    except asyncio.TimeoutError:
         logger.error(f"WebSocket proxy failed: Timeout connecting to rosbridge at {rosbridge_url}.")
         await frontend_ws.close(code=1008, reason="Could not connect to ROS backend")
    except websockets.exceptions.InvalidURI:
         logger.error(f"WebSocket proxy failed: Invalid ROSBRIDGE_URL: {rosbridge_url}")
         await frontend_ws.close(code=1011, reason="Server configuration error")
    except websockets.exceptions.WebSocketException as e_ws:
         logger.error(f"WebSocket proxy error connecting to rosbridge: {e_ws}")
         await frontend_ws.close(code=1011, reason=f"ROS connection error: {e_ws}")
    except WebSocketDisconnect:
        logger.info("Frontend WebSocket disconnected before rosbridge connection could complete or during operation.")
    except Exception as e:
        logger.error(f"Unexpected error in WebSocket proxy: {e}", exc_info=True)
        if frontend_ws.client_state == WebSocketState.CONNECTED:
             await frontend_ws.close(code=1011, reason="Internal server error")
    finally:
        logger.info("WebSocket proxy closing connections.")
        if ros_ws and ros_ws.open:
            await ros_ws.close()
        logger.info(f"Frontend WebSocket connection from {client_host} closed.")'''
# --- End WebSocket Proxy ---

# --- WebSocket Proxy Endpoint (Robust Version) ---
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
    ros_ws: websockets.WebSocketClientProtocol | None = None
    
    # Create two asyncio Events to signal when each task has exited
    fe_to_ros_exited = asyncio.Event()
    ros_to_fe_exited = asyncio.Event()

    try:
        logger.info(f"Attempting WebSocket connection to rosbridge at {rosbridge_url}...")
        ros_ws = await asyncio.wait_for(websockets.connect(rosbridge_url), timeout=10.0)
        logger.info("WebSocket proxy successfully connected to rosbridge.")

        async def forward_to_ros():
            """Task to forward messages from Frontend (browser) to ROS (rosbridge)"""
            # Add a small delay to ensure ros_to_fe task is waiting
            await asyncio.sleep(0.01) 
            try:
                while True:
                    message = await frontend_ws.receive_text()
                    if ros_ws and not ros_ws.closed:
                        await ros_ws.send(message)
                    else:
                        logger.warning("WS PROXY (FE->ROS): Cannot forward, ros_ws connection is closed.")
                        break
            except WebSocketDisconnect:
                logger.info("WS PROXY (FE->ROS): Frontend disconnected.")
            except Exception as e:
                 logger.error(f"WS PROXY (FE->ROS): Error: {e}", exc_info=True)
            finally:
                logger.warning("WS PROXY (FE->ROS): Task is exiting.")
                fe_to_ros_exited.set() # Signal that this task has stopped

        async def forward_to_frontend():
            """Task to forward messages from ROS (rosbridge) to Frontend (browser)"""
            try:
                 async for message in ros_ws:
                      if frontend_ws.client_state == WebSocketState.CONNECTED:
                           await frontend_ws.send_text(message)
                      else:
                           logger.warning("WS PROXY (ROS->FE): Cannot forward, frontend connection is closed.")
                           break
            except websockets.exceptions.ConnectionClosedOK:
                  logger.info("WS PROXY (ROS->FE): Rosbridge connection closed normally.")
            except websockets.exceptions.ConnectionClosedError as e_close:
                  logger.warning(f"WS PROXY (ROS->FE): Rosbridge connection closed with error: {e_close}")
            except Exception as e_inner:
                  logger.error(f"WS PROXY (ROS->FE): Error: {e_inner}", exc_info=True)
            finally:
                logger.warning("WS PROXY (ROS->FE): Task is exiting.")
                ros_to_fe_exited.set() # Signal that this task has stopped

        # Run both tasks
        await asyncio.gather(forward_to_ros(), forward_to_frontend())

    except asyncio.TimeoutError:
         logger.error(f"WebSocket proxy failed: Timeout connecting to rosbridge at {rosbridge_url}.")
         if frontend_ws.client_state == WebSocketState.CONNECTED:
             await frontend_ws.close(code=1008, reason="Could not connect to ROS backend")
    except Exception as e:
        logger.error(f"Unexpected error in WebSocket proxy setup: {e}", exc_info=True)
        if frontend_ws.client_state == WebSocketState.CONNECTED:
             await frontend_ws.close(code=1011, reason="Internal server error")
    finally:
        # This block runs when gather() finishes (i.e., when one of the tasks exits)
        logger.warning("WebSocket proxy gather() has finished. Closing all connections.")
        
        # Ensure both tasks are aware and connections are closed
        if ros_ws and not ros_ws.closed:
            await ros_ws.close()
        if frontend_ws.client_state == WebSocketState.CONNECTED:
            await frontend_ws.close(reason="Proxy shutting down")
            
        logger.info(f"Frontend WebSocket connection from {client_host} fully closed.")
# --- End WebSocket Proxy ---

# --- Root Endpoint ---
@app.get("/", tags=["Root"], summary="API Root/Health Check")
def read_root():
    """Provides a simple welcome message to verify the API is running."""
    return {"message": "Welcome to the UniRover Indoor Delivery API"}
# --- End Root Endpoint ---

# Import necessary for WebSocket Proxy state checking
from starlette.websockets import WebSocketState