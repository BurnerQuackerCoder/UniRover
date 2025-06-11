import enum
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum as SQLAlchemyEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class UserRole(str, enum.Enum):
    """Enumeration for user roles."""
    USER = "user"
    ADMIN = "admin"

class DeliveryStatus(str, enum.Enum):
    """Enumeration for delivery statuses."""
    PENDING = "Pending"
    SCHEDULED = "Scheduled"
    IN_PROGRESS = "In Progress"
    AWAITING_PICKUP = "Awaiting Pickup"
    DELIVERED = "Delivered"
    FAILED = "Failed"

class User(Base):
    """SQLAlchemy model for the 'users' table."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(SQLAlchemyEnum(UserRole), default=UserRole.USER, nullable=False)

    deliveries = relationship("Delivery", back_populates="owner")

class Delivery(Base):
    """SQLAlchemy model for the 'deliveries' table."""
    __tablename__ = "deliveries"

    id = Column(Integer, primary_key=True, index=True)
    item = Column(String, index=True, nullable=False)
    destination = Column(String, index=True, nullable=False)
    notes = Column(String, nullable=True)
    status = Column(SQLAlchemyEnum(DeliveryStatus), default=DeliveryStatus.PENDING, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    owner = relationship("User", back_populates="deliveries")