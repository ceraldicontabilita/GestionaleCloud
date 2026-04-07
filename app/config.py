"""Application configuration using Pydantic Settings."""
from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path


class Settings(BaseSettings):
    APP_NAME: str = "Ceraldi ERP v2"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "production"
    DEBUG: bool = False

    HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8001

    MONGODB_ATLAS_URI: Optional[str] = None
    DB_NAME: str = "azienda_erp_db"
    AZIENDA_ID: str = "b0295759-35ce-4b34-a6b4-f01b883234ad"

    AUTH_DISABLED: bool = True
    SECRET_KEY: Optional[str] = "dev-secret-key"

    UPLOAD_FOLDER: Path = Path("uploads")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
