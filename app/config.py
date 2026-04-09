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

    # MongoDB — supporta Atlas URI e MONGO_URL locale
    MONGODB_ATLAS_URI: Optional[str] = None
    MONGO_URL: Optional[str] = None
    DB_NAME: str = "Gestionale"
    AZIENDA_ID: str = "b0295759-35ce-4b34-a6b4-f01b883234ad"

    # Auth
    AUTH_DISABLED: bool = False
    SECRET_KEY: str = "change-me-in-production-64-chars-secret-key"
    ADMIN_USERNAME: str = "ceraldi"
    ADMIN_PASSWORD: Optional[str] = None
    ADMIN_EMAIL: Optional[str] = None

    # Reparto PIN tracciabilità
    PIN_PASTICCERIA: Optional[str] = None
    PIN_ROSTICCERIA: Optional[str] = None
    PIN_EXTRA: Optional[str] = None

    UPLOAD_FOLDER: Path = Path("uploads")

    # PEC Aruba — fatture SDI
    PEC_IMAP_HOST: str = "imaps.pec.aruba.it"
    PEC_IMAP_PORT: int = 993
    PEC_SMTP_HOST: str = "smtps.pec.aruba.it"
    PEC_SMTP_PORT: int = 465
    PEC_USER: str = "fatturazioneceraldi@pec.it"
    PEC_HOST: Optional[str] = None
    PEC_PASSWORD: Optional[str] = None

    # Gmail
    GMAIL_USER: str = "ceraldigroupsrl@gmail.com"
    GMAIL_APP_PASSWORD: Optional[str] = None
    GMAIL_PASSWORD: Optional[str] = None
    GMAIL_IMAP_HOST: str = "imap.gmail.com"
    GMAIL_SMTP_HOST: str = "smtp.gmail.com"
    GMAIL_SMTP_PORT: int = 587

    # AI
    ANTHROPIC_API_KEY: Optional[str] = None

    # Scheduler
    SCHEDULER_ENABLED: bool = True

    @property
    def mongo_uri(self) -> str:
        """Ritorna URI MongoDB: Atlas se configurato, altrimenti MONGO_URL o localhost."""
        if self.MONGODB_ATLAS_URI:
            return self.MONGODB_ATLAS_URI
        if self.MONGO_URL:
            return self.MONGO_URL
        return "mongodb://localhost:27017"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
