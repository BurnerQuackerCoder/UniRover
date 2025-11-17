# import logging
# from datetime import datetime, timedelta, timezone
# from typing import Optional
# from jose import jwt
# from passlib.context import CryptContext

# from .core.config import settings

# logger = logging.getLogger(__name__)

# # Setup password hashing context
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# def verify_password(plain_password: str, hashed_password: str) -> bool:
#     """Verifies a plain password against a hashed password."""
#     return pwd_context.verify(plain_password, hashed_password)

# def get_password_hash(password: str) -> str:
#     """Hashes a plain password, truncating if necessary for bcrypt compatibility."""
#     password_bytes = password.encode('utf-8')
#     if len(password_bytes) > 72:
#         # --- ADD THIS LINE ---
#         logger.warning(f"Password length ({len(password_bytes)} bytes) > 72. Truncating.")
#         password_bytes = password_bytes[:72]
#     # Log the length being hashed AFTER potential truncation
#     logger.debug(f"Hashing password with length: {len(password_bytes)} bytes.") # Add this debug log
#     return pwd_context.hash(password_bytes)

# def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
#     """Creates a JWT access token."""
#     to_encode = data.copy()
#     if expires_delta:
#         expire = datetime.now(timezone.utc) + expires_delta
#     else:
#         expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
#     to_encode.update({"exp": expire})
#     encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
#     return encoded_jwt

#------------------------ Without Hash ------------------
'''from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt
# from passlib.context import CryptContext # Comment out

from .core.config import settings
import logging # Added for logging
logger = logging.getLogger(__name__) # Added for logging

# Setup password hashing context
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto") # Comment out

def verify_password(plain_password: str, stored_password: str) -> bool:
    """Verifies a plain password against the stored plain password (INSECURE)."""
    logger.warning("Using INSECURE plain text password verification!") # Add warning
    return plain_password == stored_password # Simple comparison

def get_password_hash(password: str) -> str:
    """Returns the plain password (INSECURE). Hashing is skipped."""
    logger.warning("Skipping password hashing! Storing plain text (INSECURE).") # Add warning
    # Optional: Still apply truncation for consistency if needed elsewhere, though less critical now.
    # password_bytes = password.encode('utf-8')
    # if len(password_bytes) > 72:
    #    logger.warning(f"Password length ({len(password_bytes)} bytes) > 72. Truncating anyway.")
    #    password_bytes = password_bytes[:72]
    # return password_bytes.decode('utf-8', errors='ignore') # Return potentially truncated string
    return password # Just return the plain password

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Creates a JWT access token."""
    # This function remains the same
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt'''

    #------------------------ End Without Hash ------------------

from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt
from passlib.context import CryptContext
import logging # Import logging

from .core.config import settings

logger = logging.getLogger(__name__) # Get logger

# Setup password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hashes a plain password, truncating if necessary for bcrypt compatibility."""
    # Bcrypt has a 72-byte limit. Encode to bytes, truncate, then pass to hash.
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        logger.warning(f"Password length ({len(password_bytes)} bytes) > 72. Truncating.")
        password_bytes = password_bytes[:72]
    return pwd_context.hash(password_bytes) # Hash the (potentially truncated) bytes

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Creates a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt