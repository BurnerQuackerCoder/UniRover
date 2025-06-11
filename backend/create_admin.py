import os
import sys
from sqlalchemy.orm import Session
from getpass import getpass

# Add the 'app' directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app import crud, schemas
from app.database import SessionLocal
from app.models import UserRole

def create_super_user():
    """
    Creates the initial admin user.
    """
    db: Session = SessionLocal()
    print("Creating new admin user...")
    
    while True:
        email = input("Enter admin email: ")
        if crud.get_user_by_email(db, email=email):
            print("Email already registered. Please use a different one.")
        else:
            break
            
    while True:
        password = getpass("Enter admin password: ")
        password_confirm = getpass("Confirm admin password: ")
        if password != password_confirm:
            print("Passwords do not match. Please try again.")
        else:
            break

    user_in = schemas.UserCreate(
        email=email,
        password=password,
        role=UserRole.ADMIN
    )
    
    admin_user = crud.create_user(db, user=user_in)
    print(f"Admin user '{admin_user.email}' created successfully.")
    db.close()

if __name__ == "__main__":
    create_super_user()