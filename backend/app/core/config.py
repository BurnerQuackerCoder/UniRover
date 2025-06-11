from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    """
    # Database URL. Default is a local SQLite file.
    DATABASE_URL: str = "sqlite:///./delivery.db"
    
    # JWT Settings
    SECRET_KEY: str = "e8a3b5a7a8d9a4b1e6f5c8a3b5d9e8f6c7a8b9d0c1e2f3a4b5c6d7e8f9a0b1c2" # A secure default key
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Pydantic settings configuration
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8')

    # ROS Integration Settings
    ROSBRIDGE_URL: str = "ws://192.168.0.151:9090" # IMPORTANT: Change this IP
    ROS_BATTERY_TOPIC: str = "/battery"
    BATTERY_MIN_LEVEL: float = 20.0 # Minimum battery percentage to start a tour
    DELIVERY_BATCH_SIZE: int = 3 # Number of pending deliveries to trigger a tour
    ENFORCE_BATTERY_CHECK: bool = False # << Set to False to disable battery check

    # Development Settings
    SIMULATION_MODE: bool = False # Set to False when you want to use the real robot


# Create a single instance of the settings to be used throughout the application
settings = Settings()