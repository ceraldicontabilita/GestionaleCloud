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
    # Archivio operativo: ``sheets`` usa Google Sheets/Drive come sorgente
    # primaria mantenendo una API asincrona compatibile con il codice attuale.
    # MongoDB resta solo compatibilita' transitoria del runtime; il default
    # di produzione e' il registro Drive/Sheets.
    DATA_BACKEND: str = "sheets"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = False

    # MongoDB Atlas
    MONGODB_ATLAS_URI: Optional[str] = None
    MONGO_URL: Optional[str] = None
    # Default allineato al DB reale (INDEX.md) e ai fallback interni
    # (auth_secret): evita la divergenza 'azienda_erp_db' vs 'Gestionale'.
    # In produzione è comunque impostato via env.
    DB_NAME: str = "Gestionale"
    MONGODB_MAX_POOL_SIZE: int = 50
    # Dieci connessioni minime per ogni replica/worker esauriscono presto i
    # limiti Atlas. Il pool cresce su domanda e rilascia le socket inattive.
    MONGODB_MIN_POOL_SIZE: int = 0
    MONGODB_TIMEOUT_MS: int = 5000
    MONGODB_CONNECT_TIMEOUT_MS: int = 5000
    MONGODB_SOCKET_TIMEOUT_MS: int = 20000
    MONGODB_WAIT_QUEUE_TIMEOUT_MS: int = 5000
    MONGODB_MAX_IDLE_TIME_MS: int = 120000
    # Le riparazioni dati sono migrazioni operative, non attivita' di bootstrap.
    # Un riavvio dell'app non deve modificare registrazioni contabili.
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
    GOOGLE_DRIVE_FATTURE_FOLDER_ID: Optional[str] = None  # cartella Drive da cui leggere gli XML
    GOOGLE_DRIVE_SA_FILE: Optional[str] = None            # path al JSON del service account
    GOOGLE_DRIVE_SA_JSON: Optional[str] = None            # oppure il JSON inline (alternativa al file)
    # Altre cartelle Drive (specifica utente 10-07-2026): gli ID vanno nelle
    # variabili d'ambiente su Render, MAI nel codice.
    GOOGLE_DRIVE_CEDOLINI_FOLDER_ID: Optional[str] = None      # cedolini paga (PDF)
    GOOGLE_DRIVE_CORRISPETTIVI_FOLDER_ID: Optional[str] = None # corrispettivi RT
    GOOGLE_DRIVE_QUIETANZE_FOLDER_ID: Optional[str] = None     # quietanze F24
    GOOGLE_DRIVE_ESTRATTI_FOLDER_ID: Optional[str] = None      # estratti conto
    GOOGLE_DRIVE_ESTRATTI_FOLDER_IDS: Optional[str] = None     # piu radici, separate da virgola
    GOOGLE_DRIVE_BONIFICI_FOLDER_ID: Optional[str] = None      # bonifici effettuati: fornitori, stipendi e altri pagamenti
    # Registro dati portabile: un Google Spreadsheet con un foglio per ogni
    # entita canonica. ID diretto oppure cartella in cui crearlo/ritrovarlo.
    GOOGLE_SHEETS_LEDGER_ID: Optional[str] = None
    GOOGLE_SHEETS_LEDGER_FOLDER_ID: Optional[str] = None
    # Nuovi canali documentali (scelta utente 12-07-2026): cartelle Drive
    # dedicate. Gli ID vanno su Render; ogni cartella condivisa con la
    # client_email del service account che la legge.
    GOOGLE_DRIVE_DICHIARAZIONI_IVA_FOLDER_ID: Optional[str] = None   # dichiarazioni IVA (PDF)
    GOOGLE_DRIVE_CARTELLE_ESATTORIALI_FOLDER_ID: Optional[str] = None # cartelle esattoriali (PDF)
    GOOGLE_DRIVE_AVVISI_BONARI_FOLDER_ID: Optional[str] = None       # avvisi bonari (PDF)

    # Canali documentali ancora privi di un nome GOOGLE_DRIVE_* dedicato.
    # Le aree principali sopra hanno invece una sola variabile canonica:
    # non reintrodurre alias Render che puntano allo stesso folder ID.
    DRIVE_PRESENZE_FOLDER_ID: Optional[str] = None
    DRIVE_F24_FOLDER_ID: Optional[str] = None
    DRIVE_CARTE_FOLDER_ID: Optional[str] = None
    DRIVE_PAYPAL_FOLDER_ID: Optional[str] = None
    DRIVE_NOLEGGIO_FOLDER_ID: Optional[str] = None
    DRIVE_VERBALI_FOLDER_ID: Optional[str] = None
    DRIVE_FOLDER_REGISTRY_JSON: Optional[str] = None
    # Radice fiscale canonica indicata dall'amministratore. L'ID identifica
    # soltanto la cartella contenitore: le sottocartelle operative vengono
    # scoperte e verificate via Drive API, mai create per supposizione.
    DRIVE_FISCAL_ROOT_FOLDER_ID: str = "1f48bounfoOyHL_kqpHAp2GAnFfEpHvVa"
    # Archivio documentale esterno: il gestionale legge esclusivamente
    # l'indice Excel e lascia i file originali su Google Drive.
    DRIVE_DOCUMENT_INDEX_ROOT_FOLDER_ID: str = "1tmVu6fl7qhJbLcGCHT3wEQzrvFAElc9h"
    GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON: Optional[str] = None

    # Service account DEDICATI per cartella (scelta utente: un account per
    # canale). Se valorizzato, il canale usa il suo; altrimenti ricade su
    # GOOGLE_DRIVE_SA_JSON/SA_FILE condiviso. Ogni cartella Drive deve essere
    # condivisa con la client_email del service account che la legge.
    GOOGLE_SERVICE_ACCOUNT_JSON_CEDOLINI: Optional[str] = None
    GOOGLE_SERVICE_ACCOUNT_JSON_CORRISPETTIVI: Optional[str] = None
    GOOGLE_SERVICE_ACCOUNT_JSON_FATTURE: Optional[str] = None
    GOOGLE_SERVICE_ACCOUNT_JSON_QUIETANZE: Optional[str] = None
    GOOGLE_SERVICE_ACCOUNT_JSON_ESTRATTI_CONTO: Optional[str] = None
    GOOGLE_SERVICE_ACCOUNT_JSON_BONIFICI: Optional[str] = None

    # Interruttori canali Drive (accesi/spenti — regola utente): letti
    # dall'ambiente, default = stato attuale dei canali.
    ENABLE_DRIVE_FATTURE_SYNC: bool = True
    ENABLE_DRIVE_CEDOLINI_SYNC: bool = True
    ENABLE_DRIVE_CORRISPETTIVI_SYNC: bool = True
    # Quietanze: ACCESO su scelta esplicita dell'utente (10/07/2026)
    ENABLE_DRIVE_QUIETANZE_SYNC: bool = True
    ENABLE_DRIVE_ESTRATTI_CONTO_SYNC: bool = True
    # Anno minimo dei documenti da importare dall'area Estratti conto
    # (scelta utente 07/08/2026: "solo 2026, il resto fermo"). L'inbox unico
    # contiene un arretrato dal 2023: i documenti piu' vecchi restano dove
    # sono, non vengono ne' importati ne' spostati. Metterlo a 0 li sblocca.
    DRIVE_ESTRATTI_ANNO_MINIMO: int = 2026
    ENABLE_DRIVE_BONIFICI_SYNC: bool = False
    # Canali fiscali Drive: avvisi bonari e cartelle esattoriali sono abilitati,
    # ma restano fail-closed finche' la discovery non trova una sola cartella
    # con il nome atteso sotto la radice fiscale configurata.
    ENABLE_DRIVE_DICHIARAZIONI_IVA_SYNC: bool = False
    ENABLE_DRIVE_CARTELLE_ESATTORIALI_SYNC: bool = True
    ENABLE_DRIVE_AVVISI_BONARI_SYNC: bool = True
    ENABLE_DRIVE_VERBALI_SYNC: bool = True
    # Canali EMAIL F24 e Verbali: ACCESI su scelta esplicita dell'utente
    # (13/07/2026). Interruttore dedicato per poterli spegnere senza toccare
    # le credenziali IMAP. NB: il parser F24 email non è ancora validato su
    # F24 reali — controllare i primi risultati prima di fidarsi.
    ENABLE_EMAIL_F24_SYNC: bool = True
    ENABLE_EMAIL_VERBALI_SYNC: bool = True
    # Ora locale Europe/Rome del controllo giornaliero verbali.
    VERBALI_EMAIL_SCAN_HOUR: int = 6
    
    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    
    # PayPal Reporting API
    PAYPAL_CLIENT_ID: str = ""
    PAYPAL_CLIENT_SECRET: str = ""

    # SumUp — secondo gestore POS accanto a Nexi.
    # Chiave statica del nostro stesso conto commerciante: niente OAuth.
    SUMUP_API_KEY: str = ""
    SUMUP_MERCHANT_CODE: str = ""
    SUMUP_API_BASE: str = "https://api.sumup.com"
    
    # OpenAPI.it
    OPENAPI_IT_KEY: Optional[str] = None
    OPENAPI_IT_ENV: str = "production"
    OPENAPI_IMPRESE_TOKEN: Optional[str] = None
    
    # Feature Flags
    ENABLE_SMTP_EMAIL: bool = False
    # Interruttore maestro della scansione email (Gmail IMAP). Default acceso
    # (13/07/2026): coerente con i canali email attivi (cedolini/F24/verbali).
    # Metterlo a False ferma TUTTA l'ingestione email dallo scheduler.
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

    # Stato runtime, escluso dalle variabili e dalla serializzazione. La
    # configurazione non deve aprire connessioni o scrivere su MongoDB durante
    # l'import: il segreto condiviso viene inizializzato dal lifecycle async.
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
        # Priorità: valori espliciti > .env file > variabili OS (pod Kubernetes)
        # Garantisce che MONGO_URL e DB_NAME nel .env non vengano
        # sovrascritti da variabili d'ambiente iniettate dalla piattaforma di deploy.
        # Le variabili iniettate da Render/Kubernetes devono prevalere su un
        # file .env dell'immagine potenzialmente obsoleto.
        return (init_settings, env_settings, dotenv_settings, file_secret_settings)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.MONGODB_ATLAS_URI and self.MONGO_URL:
            self.MONGODB_ATLAS_URI = self.MONGO_URL

        if self.SECRET_KEY:
            self._auth_secret_source = "configured"
        else:
            # Mantiene importabili i moduli e isolati i test, senza I/O di
            # rete. In produzione il lifecycle sostituisce questa chiave con
            # quella condivisa di Mongo prima di accettare richieste.
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
        """Origin CORS consentiti.

        Sicurezza (audit 13/07/2026): con autenticazione via cookie
        (`ALLOW_CREDENTIALS=True`) NON è mai lecito rispondere con wildcard
        `*` — il browser rifletterebbe qualunque Origin, permettendo a un
        sito terzo di usare la sessione dell'utente. Quindi:

        - Se sono elencati origin espliciti in `CORS_ALLOWED_ORIGINS`
          (o `CORS_ORIGINS`/`ALLOWED_ORIGINS`/`FRONTEND_URL`), usa quelli.
        - Se non c'è nulla di esplicito e le credenziali sono attive,
          NON aprire a `*`: restituisci lista vuota (nessun sito esterno
          autorizzato) e logga un warning, così l'app resta chiusa finché
          non si imposta il dominio reale.
        - `*` è concesso solo quando le credenziali sono disattivate.

        Dominio da impostare in produzione: variabile d'ambiente
        `CORS_ALLOWED_ORIGINS` (o `FRONTEND_URL`), es.
        `CORS_ALLOWED_ORIGINS="https://gestionale.esempio.it"`.
        Più domini separati da virgola.
        """
        import logging
        esplicite = (
            getattr(self, "CORS_ALLOWED_ORIGINS", "")
            or self.CORS_ORIGINS
            or self.ALLOWED_ORIGINS
            or ""
        )
        esplicite = esplicite.strip()

        if esplicite and esplicite != "*":
            lista = [o.strip() for o in esplicite.split(",") if o.strip() and o.strip() != "*"]
            if lista:
                return lista

        # Nessun origin esplicito valido: fallback su FRONTEND_URL se presente.
        if self.FRONTEND_URL:
            return [self.FRONTEND_URL]

        # Niente di esplicito. Il frontend di produzione e' same-origin:
        # con cookie attivi si chiude ogni accesso cross-site finche' il
        # dominio esterno non viene autorizzato esplicitamente.
        if self.ALLOW_CREDENTIALS:
            logging.getLogger(__name__).warning(
                "CORS cross-site disabilitato: ALLOW_CREDENTIALS=True senza "
                "origin esplicito. Imposta CORS_ALLOWED_ORIGINS soltanto per "
                "i domini esterni autorizzati."
            )
        # Il frontend di produzione e' same-origin. Con cookie abilitati il
        # fallback sicuro e' quindi nessun origin cross-site; le integrazioni
        # esterne devono essere autorizzate esplicitamente.
        return [] if self.ALLOW_CREDENTIALS else ["*"]
    
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
            'database': bool(
                self.GOOGLE_SHEETS_LEDGER_ID or self.GOOGLE_SHEETS_LEDGER_FOLDER_ID
                if self.DATA_BACKEND.strip().lower() == "sheets"
                else (self.MONGODB_ATLAS_URI or self.MONGO_URL)
            ),
            'auth': bool(self.SECRET_KEY),
            'google_oauth': bool(self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_SECRET),
            'openai': bool(self.OPENAI_API_KEY),
            'telegram': bool(self.TELEGRAM_BOT_TOKEN),
        }
    
    def validate_startup(self) -> None:
        """Validate critical configuration at startup.

        In produzione, se FAIL_FAST_SECRETS=true è attivo, l'applicazione
        fallisce l'avvio se mancano SECRET_KEY o la configurazione richiesta
        dal backend selezionato. Non esiste un fallback automatico fra
        Drive/Sheets e MongoDB.
        """
        import logging
        import os
        logger = logging.getLogger(__name__)

        fail_fast = self.is_production and os.getenv("FAIL_FAST_SECRETS", "").lower() in ("true", "1", "yes")
        errors: list[str] = []

        # Una chiave effimera rende i token diversi tra worker e li invalida
        # a ogni deploy. Il lifecycle puo' sostituirla con la chiave Mongo
        # condivisa; in modalita' fail-fast una sorgente effimera e' fatale.
        if self.auth_secret_source == "ephemeral":
            msg = (
                "SECRET_KEY effimera: configurare SECRET_KEY nel secret store "
                "oppure inizializzare la chiave condivisa Mongo prima dell'avvio."
            )
            if fail_fast:
                errors.append(msg)
            else:
                logger.warning(f"⚠️ {msg}")

        backend = self.DATA_BACKEND.strip().lower()
        if backend not in {"mongodb", "sheets"}:
            errors.append("DATA_BACKEND deve essere 'mongodb' oppure 'sheets'.")

        # Check database configuration. Sheets e' il runtime operativo
        # predefinito; MongoDB resta disponibile solo quando viene selezionato
        # esplicitamente come backend di compatibilita'. Non usare credenziali
        # Mongo per mascherare una configurazione Sheets incompleta.
        if backend == "sheets":
            if self.GOOGLE_SHEETS_LEDGER_ID or self.GOOGLE_SHEETS_LEDGER_FOLDER_ID:
                pass
            else:
                msg = (
                    "DATA_BACKEND=sheets richiede GOOGLE_SHEETS_LEDGER_ID oppure "
                    "GOOGLE_SHEETS_LEDGER_FOLDER_ID; MongoDB non e' un fallback."
                )
                if fail_fast:
                    errors.append(msg)
                else:
                    logger.error(msg)
        elif backend == "mongodb" and not (self.MONGODB_ATLAS_URI or self.MONGO_URL):
            msg = (
                "MONGODB_ATLAS_URI non configurata! "
                "Il database non funzionerà correttamente."
            )
            if fail_fast:
                errors.append(msg)
            else:
                logger.error(f"❌ ERROR: {msg}")

        # DB_NAME: in produzione dev'essere valorizzato (default 'Gestionale').
        if self.is_production and not (self.DB_NAME or "").strip():
            msg = "DB_NAME non configurato in produzione."
            errors.append(msg) if fail_fast else logger.error(f"❌ ERROR: {msg}")

        # Senza origin espliciti ``get_cors_origins`` restituisce [] e mantiene
        # il frontend same-origin: e' una configurazione sicura. L'unico caso
        # da rifiutare e' una wildcard esplicita insieme alle credenziali.
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
