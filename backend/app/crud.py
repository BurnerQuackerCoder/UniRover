from sqlalchemy.orm import Session
from . import models, schemas
from .auth import get_password_hash

def get_user_by_email(db: Session, email: str):
    """Fetches a user from the database by their email address."""
    return db.query(models.User).filter(models.User.email == email).first()

def create_user(db: Session, user: schemas.UserCreate):
    """Creates a new user in the database."""
    hashed_password = get_password_hash(user.password)
    db_user = models.User(
        email=user.email,
        hashed_password=hashed_password,
        role=user.role
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_deliveries_by_user(db: Session, user_id: int, skip: int = 0, limit: int = 100):
    """Fetches all deliveries for a specific user."""
    return db.query(models.Delivery).filter(models.Delivery.owner_id == user_id).offset(skip).limit(limit).all()

def get_all_deliveries(db: Session, skip: int = 0, limit: int = 100):
    """Fetches all deliveries in the database (for admins)."""
    return db.query(models.Delivery).offset(skip).limit(limit).all()

def create_user_delivery(db: Session, delivery: schemas.DeliveryCreate, user_id: int):
    """Creates a new delivery for a specific user."""
    db_delivery = models.Delivery(**delivery.model_dump(), owner_id=user_id)
    db.add(db_delivery)
    db.commit()
    db.refresh(db_delivery)
    return db_delivery

def update_delivery_status(db: Session, delivery_id: int, status: schemas.DeliveryUpdate):
    """Updates the status of a specific delivery."""
    db_delivery = db.query(models.Delivery).filter(models.Delivery.id == delivery_id).first()
    if db_delivery:
        db_delivery.status = status.status
        db.commit()
        db.refresh(db_delivery)
    return db_delivery

def get_deliveries_by_status(db: Session, status: models.DeliveryStatus):
    """Fetches all deliveries with a specific status."""
    return db.query(models.Delivery).filter(models.Delivery.status == status).all()

def update_delivery_status_in_db(db: Session, delivery_id: int, new_status: models.DeliveryStatus):
    """Updates the status of a specific delivery in the database."""
    db_delivery = db.query(models.Delivery).filter(models.Delivery.id == delivery_id).first()
    if db_delivery:
        db_delivery.status = new_status
        db.commit()
        db.refresh(db_delivery)
    return db_delivery

def reset_deliveries_status(db: Session, delivery_ids: list[int]):
    """Resets the status of a list of deliveries back to Pending."""
    if not delivery_ids:
        return 0
        
    updated_count = db.query(models.Delivery).\
        filter(models.Delivery.id.in_(delivery_ids)).\
        update({"status": models.DeliveryStatus.PENDING}, synchronize_session=False)
    
    db.commit()
    return updated_count