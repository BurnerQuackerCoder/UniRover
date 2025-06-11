import json
import asyncio
from contextlib import asynccontextmanager
#from .ros_client import ros_client # Real_mode
from .ros import ros_client # Simulation_mode
from .scheduler import scheduler
from fastapi import FastAPI, HTTPException, status, APIRouter, Depends
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from .database import engine, Base
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from .scheduler import scheduler, pickup_confirmation_events

from . import crud, schemas, models, auth, dependencies
from .database import engine, Base, get_db

# This command creates all the database tables defined in models.py
# In a production environment with migrations, you would use Alembic instead.
Base.metadata.create_all(bind=engine)

# --- Gloabl variable for coordinates ---
# This will be loaded on startup
room_coordinates = {}

# --- Lifespan Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup Logic ---
    print("Server starting up...")
    # Load room coordinates from JSON file
    global room_coordinates
    with open("/home/po/Desktop/Jay_MT/Code/UniRover/backend/app/room_coordinates.json", "r") as f:
        room_coordinates = json.load(f)
    print(f"Loaded {len(room_coordinates)} room coordinates.")
    
    # Connect to ROS and start the scheduler
    await ros_client.connect() # Use create_task to run connection in background
    scheduler.start(room_coords=room_coordinates) # Start the scheduler and pass coordinates
    
    yield # The application runs here

    # --- Shutdown Logic ---
    print("Server shutting down...")
    scheduler.stop()
    await ros_client.disconnect()



app = FastAPI(
    title="Indoor Delivery System API",
    description="API for managing indoor deliveries with ROSbot integration.",
    version="2.0.0",
    lifespan=lifespan
)

# CORS Middleware Configuration
origins = [
    "http://localhost:5173", # The address of your React frontend
    "http://localhost:3000", # A common alternative for React
    "http://127.0.0.1:5173"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods (GET, POST, etc.)
    allow_headers=["*"], # Allows all headers
)

# --- Global Error Handling ---
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.detail},
    )

# --- Routers ---
auth_router = APIRouter(prefix="/auth", tags=["Authentication"])
users_router = APIRouter(prefix="/users", tags=["Users"])
deliveries_router = APIRouter(tags=["Deliveries"])

@auth_router.post("/signup", response_model=schemas.UserInDB, status_code=status.HTTP_201_CREATED)
def signup(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """Sign up a new user."""
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user(db=db, user=user)

@auth_router.post("/login", response_model=schemas.Token)
def login(db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    """Log in a user to get an access token."""
    user = crud.get_user_by_email(db, email=form_data.username)
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = auth.create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@users_router.get("/me", response_model=schemas.UserInDB)
def read_users_me(current_user: models.User = Depends(dependencies.get_current_user)):
    """Get the details of the currently authenticated user."""
    return current_user

# --- ADD THE NEW DELIVERY ENDPOINTS ---

@deliveries_router.post("/deliveries", response_model=schemas.DeliveryInDB, status_code=status.HTTP_201_CREATED)
def create_delivery(
    delivery: schemas.DeliveryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(dependencies.get_current_user)
):
    """Create a new delivery request (for authenticated users)."""
    return crud.create_user_delivery(db=db, delivery=delivery, user_id=current_user.id)

@deliveries_router.get("/deliveries", response_model=list[schemas.DeliveryInDB])
def read_user_deliveries(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(dependencies.get_current_user)
):
    """Retrieve all delivery requests for the current user."""
    return crud.get_deliveries_by_user(db=db, user_id=current_user.id)

@deliveries_router.get("/admin/deliveries", response_model=list[schemas.DeliveryWithOwner])
def read_all_deliveries(
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(dependencies.get_current_admin_user)
):
    """Retrieve all delivery requests (admin only)."""
    return crud.get_all_deliveries(db=db)

@deliveries_router.put("/admin/deliveries/{delivery_id}", response_model=schemas.DeliveryWithOwner)
def update_delivery(
    delivery_id: int,
    status: schemas.DeliveryUpdate,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(dependencies.get_current_admin_user)
):
    """Update a delivery's status (admin only)."""
    updated_delivery = crud.update_delivery_status(db, delivery_id=delivery_id, status=status)
    if not updated_delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    return updated_delivery

@deliveries_router.post("/deliveries/{delivery_id}/confirm_pickup", status_code=status.HTTP_200_OK)
def confirm_pickup(
    delivery_id: int,
    current_user: models.User = Depends(dependencies.get_current_user)
):
    """Endpoint for a user to confirm they have picked up a delivery."""
    if delivery_id in pickup_confirmation_events:
        pickup_confirmation_events[delivery_id].set()
        return {"message": "Pickup confirmed successfully."}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Delivery is not currently awaiting pickup or does not exist."
        )
    
@deliveries_router.post("/admin/robot/return_to_base", status_code=status.HTTP_200_OK)
async def command_return_to_base(
    admin_user: models.User = Depends(dependencies.get_current_admin_user)
):
    """
    Emergency command to abort the current delivery tour and send the robot
    to its base station. Resets any in-progress deliveries to Pending.
    """
    # We use asyncio.create_task to run this in the background and immediately
    # return a response to the admin, as the full process might take a moment.
    asyncio.create_task(scheduler.abort_tour_and_return_to_base())
    
    return {"message": "Command received: aborting tour and returning to base."}

# Include routers in the main app
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(deliveries_router)


@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    # Log the exception here for debugging
    # For example: logging.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"message": "An unexpected error occurred on the server."},
    )

# Add this temporary endpoint for testing
@app.get("/test/send_action_goal", include_in_schema=False)
async def test_send_action_goal():
    from .ros import ros_client
    if not ros_client._connection:
        raise HTTPException(status_code=503, detail="Not connected to ROS.")

    test_coords = {"x": 1.0, "y": -1.0, "w": 1.0}
    try:
        goal_id = await ros_client.send_goal_action(test_coords)
        return {"status": "success", "detail": f"Sent action goal {goal_id} to robot."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send goal: {e}")

# --- API Endpoints ---
@app.get("/", tags=["Root"])
def read_root():
    """A welcome message to verify the API is running."""
    return {"message": "Welcome to the Indoor Delivery System API"}

# Authentication and delivery endpoints will be added in the next steps.