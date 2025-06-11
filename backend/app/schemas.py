from pydantic import BaseModel, EmailStr, ConfigDict
from datetime import datetime
from typing import Optional
from .models import UserRole, DeliveryStatus

# Pydantic's orm_mode is now from_attributes in V2
# We use a config class for reusability.
class OrmConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)

# --- Token Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# --- User Schemas ---
class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str
    role: UserRole = UserRole.USER

class UserInDB(UserBase, OrmConfig):
    id: int
    role: UserRole

# --- Delivery Schemas ---
class DeliveryBase(BaseModel):
    item: str
    destination: str
    notes: Optional[str] = None

class DeliveryCreate(DeliveryBase):
    pass

class DeliveryUpdate(BaseModel):
    status: DeliveryStatus

class DeliveryInDB(DeliveryBase, OrmConfig):
    id: int
    status: DeliveryStatus
    created_at: datetime
    owner_id: int


# --- Schemas for returning data with relationships ---

class UserInDBWithDeliveries(UserInDB):
    deliveries: list[DeliveryInDB] = []

class DeliveryWithOwner(DeliveryInDB):
    owner: UserInDB