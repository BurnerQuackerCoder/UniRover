from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from .core.config import settings

# The engine is the entry point to the database.
# The 'connect_args' is needed only for SQLite to allow multi-threaded access.
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

# Each instance of SessionLocal will be a database session.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for our SQLAlchemy models to inherit from.
Base = declarative_base()

# Dependency for getting a DB session in API routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()