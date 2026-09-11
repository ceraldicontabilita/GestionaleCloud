"""
Application configuration using Pydantic Settings.
FIX: path .env corretto
"""
from pydantic import PrivateAttr
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
    # Supabase e' il registro operativo strutturato. Google Drive conserva gli
    # originali documentali. ``sheets`` resta disponibile soltanto come
    # compatibilita' transitoria di rollback/test durante il cutover.
    DATA_BACKEND: str = "supabase"
    SHEETS_REGISTRY_NAME: str = "GestionaleCloud"
    # Credenziali server-to-server del runtime Supabase. La publishable key non
    # concede da sola accesso ai dati; ogni RPC richiede anche il secret
    # applicativo separato conservato esclusivamente nel secret store Render.
    SUPABASE_URL: Optional[str] = None
    SUPABASE_PUBLISHABLE_KEY: Optional[str] = None
    SUPABASE_RUNTIME_SECRET: Optional[str] = None

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = False

    # Nome logico del registro documentale esposto tramite l'interfaccia database.
    DB_NAME: str = "Gestionale"
    # Le riparazioni dati e migrazioni all'avvio restano disabilitate per default.
    RUN_STARTUP_DATA_REPAIRS: bool = False
    RUN_STARTUP_INDEX_MIGRATIONS: bool = False
    RUN_STARTUP_SEED_DATA: bool = False
    # Perimetro fiscale esplicito. Ogni nuovo record del sottosistema fiscale
    # porta questa chiave e ogni query la filtra: non si deduce mai l'azienda
    # dal nome di un file o di una cartella Drive.
    FISCAL_COMPANY_ID: str = "04523831214"
    ADER_MICRO_RESIDUAL_THRESHOLD_CENTS: int = 500
    # I processi periodici devono poter essere esclusi nelle istanze locali o
    # dedicate al solo frontend. In produzione restano attivi per default.
    ENABLE_SCHEDULER: bool = True
    SCHEDULER_LEASE_SECONDS: int = 21600

    # Security
    SECRET_KEY: Optional[str] = None
    ALGORITHM: str = "HS256"
    # REGOLA UTENTE (10-07-2026): dati sensibili → la sessione scade dopo
    # 1 ORA DI INATTIVITÀ. Il token dura 60 minuti ma viene rinnovato in
    # automatico a ogni richiesta (sessione scorrevole, vedi
    # AuthenticationMiddleware): finché lavori non scade mai; se lasci
    # l'app ferma un'ora, al collegamento successivo richiede il PIN.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    # Canale macchina-a-macchina limitato ai due endpoint Render documentali.
    # Non sostituisce il JWT utente e non deve essere riusato da altri servizi.
    RENDER_INGEST_SHARED_SECRET: Optional[str] = None

    # CORS
    # Origin consentiti in produzione: impostare col dominio reale del
    # gestionale, es. CORS_ALLOWED_ORIGINS="https://gestionale.esempio.it"
    # (più domini separati da virgola). Se valorizzato, chiude l'accesso a
    # ogni altro sito; se vuoto e le credenziali sono abilitate, resta
    # consentito soltanto il traffico same-origin (vedi get_cors_origins).
    CORS_ALLOWED_ORIGINS: str = ""
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
    # Alias effettivi presenti nell'ambiente operativo Ceraldi. Restano
    # separati per non obbligare a rinominare o duplicare segreti su Render.
    GMAIL_ACCOUNT_AMMINISTRATIVO: Optional[str] = None
    GMAIL_APP_PASSWORD_AMMINISTRATIVO: Optional[str] = None
    EMAIL_USER: Optional[str] = None
    EMAIL_PASSWORD: Optional[str] = None
    EMAIL_APP_PASSWORD: Optional[str] = None
    EMAIL_ADDRESS: Optional[str] = None
    IMAP_HOST: str = "imap.gmail.com"
    IMAP_SERVER: Optional[str] = None
    IMAP_USER: Optional[str] = None
    IMAP_PASSWORD: Optional[str] = None
    IMAP_PORT: int = 993

    # OpenAI
    OPENAI_API_KEY: Optional[str] = None

    # Google APIs
    GEMINI_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None

    # Google OAuth
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "/api/auth/google/callback"

    # Google Drive — ingest fatture XML
    GOOGLE_DRIVE_FATTURE_FOLDER_ID: Optional[str] = None
    GOOGLE_DRIVE_SA_FILE: Optional[str] = None
    GOOGLE_DRIVE_SA_JSON: Optional[str] = None
    GOOGLE_DRIVE_CEDOLINI_FOLDER_ID: Optional[str] = None
    GOOGLE_DRIVE_CORRISPETTIVI_FOLDER_ID: Optional[str] = None
    GOOGLE_DRIVE_QUIETANZE_FOLDER_ID: Optional[str] = None
    GOOGLE_DRIVE_ESTRATTI_FOLDER_ID: Optional[str] = None
    GOOGLE_DRIVE_ESTRATTI_FOLDER_IDS: Optional[str] = None
    GOOGLE_DRIVE_BONIFICI_FOLDER_ID: Optional[str] = None
    # Compatibilita' transitoria del vecchio ledger Sheets. Non usare queste
    # variabili per nuovi flussi applicativi.
    GOOGLE_SHEETS_LEDGER_ID: Optional[str] = None
    GOOGLE_SHEETS_LEDGER_FOLDER_ID: Optional[str] = None
    GOOGLE_DRIVE_DICHIARAZIONI_IVA_FOLDER_ID: Optional[str] = None
    GOOGLE_DRIVE_CARTELLE_ESATTORIALI_FOLDER_ID: Optional[str] = None
    GOOGLE_DRIVE_AVVISI_BONARI_FOLDER_ID: Optional[str] = None

    DRIVE_PRESENZE_FOLDER_ID: Optional[str] = None
    DRIVE_F24_FOLDER_ID: Optional[str] = None
    DRIVE_CARTE_FOLDER_ID: Optional[str] = None
    DRIVE_PAYPAL_FOLDER_ID: Optional[str] = None
    DRIVE_NOLEGGIO_FOLDER_ID: Optional[str] = None
    DRIVE_VERBALI_FOLDER_ID: Optional[str] = None
    DRIVE_FOLDER_REGISTRY_JSON: Optional[str] = None
    DRIVE_FISCAL_ROOT_FOLDER_ID: str = "1f48bounfoOyHL_kqpHAp2GAnFfEpHvVa"
    DRIVE_DOCUMENT_INDEX_ROOT_FOLDER_ID: str = "1tmVu6fl7qhJbLcGCHT3wEQzrvFAElc9h"
    GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON: Optional[str] = None

    GOOGLE_SERVICE_ACCOUNT_JSON_CEDOLINI: Optional[str] = None
    GOOGLE_SERVICE_ACCOUNT_JSON_CORRISPETTIVI: Optional[str] = None
    GOOGLE_SERVICE_ACCOUNT_JSON_FATTURE: Optional[str] = None
    GOOGLE_SERVICE_ACCOUNT_JSON_QUIETANZE: Optional[str] = None
    GOOGLE_SERVICE_ACCOUNT_JSON_ESTRATTI_CONTO: Optional[str] = None
    GOOGLE_SERVICE_ACCOUNT_JSON_BONIFICI: Optional[str] = None

    ENABLE_DRIVE_FATTURE_SYNC: bool = True
    DRIVE_FATTURE_BATCH_SIZE: int = 1
    ENABLE_DRIVE_CEDOLINI_SYNC: bool = True
    ENABLE_DRIVE_CORRISPETTIVI_SYNC: bool = True
    ENABLE_DRIVE_QUIETANZE_SYNC: bool = True
    ENABLE_DRIVE_ESTRATTI_CONTO_SYNC: bool = True
    DRIVE_ESTRATTI_BATCH_SIZE: int = 1
    DRIVE_ESTRATTI_ANNO_MINIMO: int = 2026
    ENABLE_DRIVE_BONIFICI_SYNC: bool = False
    ENABLE_DRIVE_DICHIARAZIONI_IVA_SYNC: bool = False
    ENABLE_DRIVE_CARTELLE_ESATTORIALI_SYNC: bool = True
    ENABLE_DRIVE_AVVISI_BONARI_SYNC: bool = True
    ENABLE_DRIVE_VERBALI_SYNC: bool = True
    ENABLE_EMAIL_F24_SYNC: bool = True
    ENABLE_EMAIL_VERBALI_SYNC: bool = True
    VERBALI_EMAIL_SCAN_HOUR: int = 6

    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None

    # PayPal Reporting API
    PAYPAL_CLIENT_ID: str = ""
    PAYPAL_CLIENT_SECRET: str = ""

    # SumUp
    SUMUP_API_KEY: str = ""
    SUMUP_MERCHANT_CODE: str = ""
    SUMUP_API_BASE: str = "https://api.sumup.com"

    # OpenAPI.it
    OPENAPI_IT_KEY: Optional[str] = None
    OPENAPI_IT_ENV: str = "production"
    OPENAPI_IMPRESE_TOKEN: Optional[str] = None

    # Feature Flags
    ENABLE_SMTP_EMAIL: bool = False
    ENABLE_GMAIL_IMAP: bool = True
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

    _auth_secret_source: str = PrivateAttr(default="unset")

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
        return (init_settings, env_settings, dotenv_settings, file_secret_settings)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.SECRET_KEY:
            self._auth_secret_source = "configured"
        else:
            import secrets
            self.SECRET_KEY = secrets.token_urlsafe(64)
            self._auth_secret_source = "ephemeral"

    @property
    def auth_secret_source(self) -> str:
        return self._auth_secret_source

    def set_runtime_auth_secret(self, value: str, *, source: str) -> None:
        if not value or len(value) < 32:
            raise ValueError("SECRET_KEY deve contenere almeno 32 caratteri")
        self.SECRET_KEY = value
        self._auth_secret_source = source

    def get_cors_origins(self) -> list[str]:
        """Origin CORS consentiti, chiusi per default con cookie attivi."""
        import logging
        esplicite = (
            getattr(self, "CORS_ALLOWED_ORIGINS", "")
            or self.CORS_ORIGINS
            or self.ALLOWED_ORIGINS
            or ""
        ).strip()

        if esplicite and esplicite != "*":
            lista = [o.strip() for o in esplicite.split(",") if o.strip() and o.strip() != "*"]
            if lista:
                return lista

        if self.FRONTEND_URL:
            return [self.FRONTEND_URL]

        if self.ALLOW_CREDENTIALS:
            logging.getLogger(__name__).warning(
                "CORS cross-site disabilitato: ALLOW_CREDENTIALS=True senza "
                "origin esplicito."
            )
        return [] if self.ALLOW_CREDENTIALS else ["*"]

    def get_allowed_extensions(self) -> set[str]:
        return set(ext.strip() for ext in self.ALLOWED_EXTENSIONS.split(","))

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    def validate_required_secrets(self) -> dict[str, bool]:
        """Riepiloga disponibilita' dei segreti per il backend selezionato."""
        backend = self.DATA_BACKEND.strip().lower()
        if backend == "supabase":
            database_ready = all(
                str(value or "").strip()
                for value in (
                    self.SUPABASE_URL,
                    self.SUPABASE_PUBLISHABLE_KEY,
                    self.SUPABASE_RUNTIME_SECRET,
                )
            )
        elif backend == "sheets":
            database_ready = bool(
                self.GOOGLE_SHEETS_LEDGER_ID or self.GOOGLE_SHEETS_LEDGER_FOLDER_ID
            )
        else:
            database_ready = False
        return {
            'database': database_ready,
            'auth': bool(self.SECRET_KEY),
            'google_oauth': bool(self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_SECRET),
            'openai': bool(self.OPENAI_API_KEY),
            'telegram': bool(self.TELEGRAM_BOT_TOKEN),
        }

    def validate_startup(self) -> None:
        """Valida la configurazione critica senza fallback silenziosi.

        In produzione Supabase e' il backend operativo previsto. Sheets resta
        accettato solo quando selezionato esplicitamente come percorso di
        rollback/test e richiede il proprio ledger configurato.
        """
        import logging
        import os
        logger = logging.getLogger(__name__)

        fail_fast = self.is_production and os.getenv("FAIL_FAST_SECRETS", "").lower() in ("true", "1", "yes")
        errors: list[str] = []

        if self.auth_secret_source == "ephemeral":
            msg = (
                "SECRET_KEY effimera: configurare SECRET_KEY nel secret store "
                "prima dell'avvio."
            )
            if fail_fast:
                errors.append(msg)
            else:
                logger.warning(f"⚠️ {msg}")

        backend = self.DATA_BACKEND.strip().lower()
        if backend not in ("sheets", "supabase"):
            errors.append(
                "DATA_BACKEND non supportato: usare 'supabase' in produzione "
                "oppure 'sheets' solo per rollback/test esplicito."
            )

        if backend == "sheets":
            if not (self.GOOGLE_SHEETS_LEDGER_ID or self.GOOGLE_SHEETS_LEDGER_FOLDER_ID):
                msg = (
                    "DATA_BACKEND=sheets richiede GOOGLE_SHEETS_LEDGER_ID oppure "
                    "GOOGLE_SHEETS_LEDGER_FOLDER_ID; non esiste fallback di persistenza."
                )
                if fail_fast:
                    errors.append(msg)
                else:
                    logger.error(msg)
            if self.is_production:
                logger.warning(
                    "DATA_BACKEND=sheets attivo in produzione: modalita' di "
                    "rollback transitoria, non backend operativo raccomandato."
                )

        if backend == "supabase" and not all(
            str(value or "").strip()
            for value in (
                self.SUPABASE_URL,
                self.SUPABASE_PUBLISHABLE_KEY,
                self.SUPABASE_RUNTIME_SECRET,
            )
        ):
            msg = (
                "DATA_BACKEND=supabase richiede SUPABASE_URL, "
                "SUPABASE_PUBLISHABLE_KEY e SUPABASE_RUNTIME_SECRET; "
                "non esiste fallback di persistenza."
            )
            if fail_fast:
                errors.append(msg)
            else:
                logger.error(msg)

        if backend == "sheets" and not (self.SHEETS_REGISTRY_NAME or "").strip():
            msg = "SHEETS_REGISTRY_NAME non configurato per il runtime Sheets."
            errors.append(msg) if fail_fast else logger.error(f"❌ ERROR: {msg}")

        cors_raw = (self.CORS_ALLOWED_ORIGINS or "").strip()
        if self.is_production and self.ALLOW_CREDENTIALS and "*" in {
            value.strip() for value in cors_raw.split(",") if value.strip()
        }:
            msg = (
                "CORS wildcard non consentito con ALLOW_CREDENTIALS=true: "
                "usa origini esplicite oppure il fallback same-origin."
            )
            if fail_fast:
                errors.append(msg)
            else:
                logger.error(f"❌ ERROR: {msg}")

        if errors:
            raise RuntimeError(
                "Fail-fast produzione: configurazione mancante. "
                + " | ".join(errors)
            )


settings = Settings()
FEATURES = settings.validate_required_secrets()


def get_settings() -> Settings:
    return settings
