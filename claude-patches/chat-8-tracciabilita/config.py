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
    DB_NAME: str = "Gestionale"
    AZIENDA_ID: str = "b0295759-35ce-4b34-a6b4-f01b883234ad"

    AUTH_DISABLED: bool = True
    SECRET_KEY: Optional[str] = "dev-secret-key"

    UPLOAD_FOLDER: Path = Path("uploads")

    # PEC Aruba — fatture SDI
    PEC_IMAP_HOST: str = "imaps.pec.aruba.it"
    PEC_IMAP_PORT: int = 993
    PEC_SMTP_HOST: str = "smtps.pec.aruba.it"
    PEC_SMTP_PORT: int = 465
    PEC_USER: str = "fatturazioneceraldi@pec.it"
    PEC_PASSWORD: Optional[str] = None  # Da variabile ambiente Emergent

    # Gmail
    GMAIL_USER: str = "ceraldigroupsrl@gmail.com"
    GMAIL_PASSWORD: Optional[str] = None
    GMAIL_IMAP_HOST: str = "imap.gmail.com"
    GMAIL_SMTP_HOST: str = "smtp.gmail.com"
    GMAIL_SMTP_PORT: int = 587

    # Scheduler
    SCHEDULER_ENABLED: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
