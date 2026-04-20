"""
Application configuration using Pydantic Settings.
FIX: path .env corretto
"""
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource
from typing import Optional, Type, Tuple
from pathlib import Path
import os


class Settings(BaseSettings):
    """Application settings with environment variable validation."""

    # Application
    APP_NAME: str = "Azienda in Cloud ERP"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = False

    # MongoDB Atlas
    MONGODB_ATLAS_URI: Optional[str] = None
    MONGO_URL: Optional[str] = None
    DB_NAME: str = "azienda_erp_db"
    MONGODB_MAX_POOL_SIZE: int = 50
    MONGODB_MIN_POOL_SIZE: int = 10
    MONGODB_TIMEOUT_MS: int = 5000

    # Security
    SECRET_KEY: Optional[str] = None
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # CORS
    CORS_ORIGINS: str = "*"
    ALLOWED_ORIGINS: str = "*"
    ALLOW_CREDENTIALS: bool = True
    ALLOWED_METHODS: str = "*"
    ALLOWED_HEADERS: str = "*"

    # File Upload
    MAX_UPLOAD_SIZE_MB: int = 50
    UPLOAD_FOLDER: Path = Path("uploads")
    ALLOWED_EXTENSIONS: str = ".xml,.xlsx,.xls,.pdf,.csv"

    # Email SMTP
    SMTP_ENABLED: bool = False
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = 587
    SMTP_USER: Optional[str] = None
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None
    FROM_EMAIL: Optional[str] = None

    # Gmail IMAP
    GMAIL_IMAP_ENABLED: bool = False
    GMAIL_EMAIL: Optional[str] = None
    GMAIL_APP_PASSWORD: Optional[str] = None
    EMAIL_USER: Optional[str] = None
    EMAIL_PASSWORD: Optional[str] = None
    EMAIL_APP_PASSWORD: Optional[str] = None
    EMAIL_ADDRESS: Optional[str] = None
    IMAP_HOST: str = "imap.gmail.com"
    IMAP_SERVER: Optional[str] = None
    IMAP_USER: Optional[str] = None
    IMAP_PASSWORD: Optional[str] = None
    IMAP_PORT: int = 993

    # Aruba PEC - Fatturazione Elettronica
    ARUBA_PEC_HOST: str = "imaps.pec.aruba.it"
    ARUBA_PEC_PORT: int = 993
    ARUBA_PEC_USER: Optional[str] = None
    ARUBA_PEC_PASSWORD: Optional[str] = None
    
    # OpenAI
    OPENAI_API_KEY: Optional[str] = None
    
    # Google APIs
    GEMINI_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    
    # Google OAuth
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "/api/auth/google/callback"
    
    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    
    # PayPal Reporting API
    PAYPAL_CLIENT_ID: str = ""
    PAYPAL_CLIENT_SECRET: str = ""
    
    # InvoiceTronic
    INVOICETRONIC_API_KEY: Optional[str] = None
    INVOICETRONIC_SANDBOX: bool = True
    INVOICETRONIC_CODICE_DESTINATARIO: str = "7hd37x0"
    
    # OpenAPI.it
    OPENAPI_IT_KEY: Optional[str] = None
    OPENAPI_IT_ENV: str = "production"
    OPENAPI_IMPRESE_TOKEN: Optional[str] = None
    
    # Feature Flags
    ENABLE_SMTP_EMAIL: bool = False
    ENABLE_GMAIL_IMAP: bool = False
    ENABLE_DOCUMENT_AI: bool = False
    ENABLE_ASYNC_IMPORTS: bool = True
    ENABLE_CACHING: bool = True
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    LOG_FILE: Optional[Path] = None
    
    # Performance
    REQUEST_TIMEOUT_SECONDS: int = 300
    CACHE_TTL_SECONDS: int = 3600
    MAX_CONCURRENT_IMPORTS: int = 5
    
    # Business Logic
    DEFAULT_USER_ID: str = "admin"
    DEFAULT_USER_EMAIL: str = "admin@ceraldi.it"
    IVA_ALIQUOTE: list[float] = [4.0, 5.0, 10.0, 22.0]
    
    # Frontend
    FRONTEND_URL: Optional[str] = None
    
    # Paths
    STATIC_FILES_DIR: Path = Path("static")
    TEMPLATES_DIR: Path = Path("templates")
    FONTS_DIR: Path = Path("fonts")
    
    model_config = SettingsConfigDict(
        env_file="/app/backend/.env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        # Priorità: valori espliciti > .env file > variabili OS (pod Kubernetes)
        # Garantisce che MONGO_URL e DB_NAME nel .env non vengano
        # sovrascritti dalle variabili iniettate dalla piattaforma Emergent.
        return (init_settings, dotenv_settings, env_settings, file_secret_settings)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.MONGODB_ATLAS_URI and self.MONGO_URL:
            self.MONGODB_ATLAS_URI = self.MONGO_URL
        
        # Generate SECRET_KEY if missing (with critical warning)
        if not self.SECRET_KEY:
            import secrets
            import logging
            self.SECRET_KEY = secrets.token_urlsafe(64)
            logging.getLogger(__name__).critical(
                "⚠️ CRITICAL: SECRET_KEY non configurata! Generata chiave temporanea. "
                "Impostare SECRET_KEY nell'ambiente per la produzione. "
                "I token JWT generati NON saranno validi dopo il riavvio."
            )
    
    def get_cors_origins(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        origins = self.CORS_ORIGINS or self.ALLOWED_ORIGINS or "*"
        if origins == "*":
            # CORS con credentials non permette wildcard
            if self.ALLOW_CREDENTIALS and self.FRONTEND_URL:
                import logging
                logging.getLogger(__name__).warning(
                    "CORS: allow_credentials=True con origins=* non è valido. "
                    f"Uso FRONTEND_URL: {self.FRONTEND_URL}"
                )
                return [self.FRONTEND_URL]
            return ["*"]
        return [origin.strip() for origin in origins.split(",") if origin.strip()]
    
    def get_allowed_extensions(self) -> set[str]:
        """Parse allowed file extensions."""
        return set(ext.strip() for ext in self.ALLOWED_EXTENSIONS.split(","))
    
    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"
    
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"
    
    def validate_required_secrets(self) -> dict[str, bool]:
        """Validate required and optional secrets."""
        return {
            'database': bool(self.MONGODB_ATLAS_URI or self.MONGO_URL),
            'auth': bool(self.SECRET_KEY),
            'google_oauth': bool(self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_SECRET),
            'openai': bool(self.OPENAI_API_KEY),
            'telegram': bool(self.TELEGRAM_BOT_TOKEN),
        }
    
    def validate_startup(self) -> None:
        """Validate critical configuration at startup."""
        import logging
        logger = logging.getLogger(__name__)
        
        # Check SECRET_KEY was explicitly configured (not auto-generated)
        # This can't be done perfectly, but we can at least warn if it looks auto-generated
        if not os.getenv("SECRET_KEY"):
            logger.error(
                "❌ ERROR: SECRET_KEY non configurata nell'ambiente! "
                "L'applicazione sta usando una chiave temporanea. "
                "Configurare SECRET_KEY nel file .env per la produzione."
            )
        
        # Check database configuration
        if not self.MONGODB_ATLAS_URI:
            logger.error(
                "❌ ERROR: MONGODB_ATLAS_URI non configurata! "
                "Il database non funzionerà correttamente."
            )


settings = Settings()
FEATURES = settings.validate_required_secrets()

def get_settings() -> Settings:
    return settings
