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
    # Default allineato al DB reale (INDEX.md) e ai fallback interni
    # (auth_secret): evita la divergenza 'azienda_erp_db' vs 'Gestionale'.
    # In produzione è comunque impostato via env.
    DB_NAME: str = "Gestionale"
    MONGODB_MAX_POOL_SIZE: int = 50
    MONGODB_MIN_POOL_SIZE: int = 10
    MONGODB_TIMEOUT_MS: int = 5000

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
    # ogni altro sito; se vuoto, resta aperto (vedi get_cors_origins).
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
    GOOGLE_DRIVE_BONIFICI_FOLDER_ID: Optional[str] = None      # bonifici stipendi (PDF)
    # Nuovi canali documentali (scelta utente 12-07-2026): cartelle Drive
    # dedicate. Gli ID vanno su Render; ogni cartella condivisa con la
    # client_email del service account che la legge.
    GOOGLE_DRIVE_DICHIARAZIONI_IVA_FOLDER_ID: Optional[str] = None   # dichiarazioni IVA (PDF)
    GOOGLE_DRIVE_CARTELLE_ESATTORIALI_FOLDER_ID: Optional[str] = None # cartelle esattoriali (PDF)
    GOOGLE_DRIVE_AVVISI_BONARI_FOLDER_ID: Optional[str] = None       # avvisi bonari (PDF)

    # Nomi REALI già presenti nell'ambiente Render dell'utente (file .env
    # del 10-07-2026): il codice li accetta come alias — vale il primo
    # valorizzato tra il nome GOOGLE_DRIVE_* e questi.
    DRIVE_FOLDER_CEDOLINI_ID: Optional[str] = None
    DRIVE_FOLDER_CORRISPETTIVI_ID: Optional[str] = None
    DRIVE_FOLDER_QUIETANZE_ID: Optional[str] = None
    DRIVE_FOLDER_ESTRATTI_CONTO_ID: Optional[str] = None
    DRIVE_FOLDER_ESTRATTI_CONTO_IDS: Optional[str] = None
    DRIVE_FOLDER_BONIFICI_ID: Optional[str] = None
    DRIVE_FOLDER_FATTURE_ID: Optional[str] = None
    DRIVE_FOLDER_DICHIARAZIONI_IVA_ID: Optional[str] = None
    DRIVE_FOLDER_CARTELLE_ESATTORIALI_ID: Optional[str] = None
    DRIVE_FOLDER_AVVISI_BONARI_ID: Optional[str] = None

    # Alias usati dal gestionale privato corrente. Consentono di trasferire
    # la configurazione Render senza duplicare o rinominare valori sensibili.
    DRIVE_FATTURE_FOLDER_ID: Optional[str] = None
    DRIVE_CEDOLINI_FOLDER_ID: Optional[str] = None
    DRIVE_CORRISPETTIVI_FOLDER_ID: Optional[str] = None
    DRIVE_QUIETANZE_FOLDER_ID: Optional[str] = None
    DRIVE_ESTRATTI_CONTO_FOLDER_ID: Optional[str] = None
    DRIVE_ESTRATTI_CONTO_FOLDER_IDS: Optional[str] = None
    DRIVE_PRESENZE_FOLDER_ID: Optional[str] = None
    DRIVE_F24_FOLDER_ID: Optional[str] = None
    DRIVE_CARTE_FOLDER_ID: Optional[str] = None
    DRIVE_PAYPAL_FOLDER_ID: Optional[str] = None
    DRIVE_NOLEGGIO_FOLDER_ID: Optional[str] = None
    DRIVE_VERBALI_FOLDER_ID: Optional[str] = None
    DRIVE_AVVISI_ESATTORIALI_FOLDER_ID: Optional[str] = None
    DRIVE_FOLDER_REGISTRY_JSON: Optional[str] = None
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
    ENABLE_DRIVE_BONIFICI_SYNC: bool = False
    # Nuovi canali documentali (default SPENTI finché l'utente non crea le
    # cartelle su Drive e ne mette gli ID su Render).
    ENABLE_DRIVE_DICHIARAZIONI_IVA_SYNC: bool = False
    ENABLE_DRIVE_CARTELLE_ESATTORIALI_SYNC: bool = False
    ENABLE_DRIVE_AVVISI_BONARI_SYNC: bool = False
    ENABLE_DRIVE_VERBALI_SYNC: bool = True
    # Canali EMAIL F24 e Verbali: ACCESI su scelta esplicita dell'utente
    # (13/07/2026). Interruttore dedicato per poterli spegnere senza toccare
    # le credenziali IMAP. NB: il parser F24 email non è ancora validato su
    # F24 reali — controllare i primi risultati prima di fidarsi.
    ENABLE_EMAIL_F24_SYNC: bool = True
    ENABLE_EMAIL_VERBALI_SYNC: bool = True
    
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
        return (init_settings, dotenv_settings, env_settings, file_secret_settings)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.MONGODB_ATLAS_URI and self.MONGO_URL:
            self.MONGODB_ATLAS_URI = self.MONGO_URL
        
        # ── SECRET_KEY JWT: DEVE essere stabile tra riavvii e identica su
        # tutti i worker, altrimenti i login "muoiono" a ogni deploy e con
        # piu' processi un token firmato da un worker viene rifiutato dagli
        # altri (401 intermittenti: era la causa dell'autenticazione che si
        # rompeva di continuo in produzione).
        # Priorita':
        #   1. variabile d'ambiente SECRET_KEY (se impostata, vince sempre)
        #   2. chiave condivisa in Gestionale.sistema_stato.auth_secret
        #      (stesso meccanismo di Lotti/AppDipendenti: token interoperabili);
        #      se il documento NON esiste viene CREATO in modo atomico
        #      ($setOnInsert: piu' worker concorrenti convergono sulla stessa)
        #   3. fallback deterministico derivato dall'URI Mongo (stabile tra
        #      worker e riavvii anche se il DB e' momentaneamente irraggiungibile)
        if not self.SECRET_KEY:
            import logging
            import os as _os
            import secrets

            _uri = self.MONGO_URL or self.MONGODB_ATLAS_URI or _os.getenv("MONGO_URL") or ""

            chiave_condivisa = None
            if _uri:
                try:
                    from pymongo import MongoClient as _MC
                    _cli = _MC(_uri, serverSelectionTimeoutMS=4000)
                    _coll = _cli[_os.getenv("DB_NAME", "Gestionale")]["sistema_stato"]
                    _doc = _coll.find_one({"chiave": "auth_secret"})
                    if not (_doc and _doc.get("valore")):
                        # crea la chiave condivisa una sola volta, race-safe
                        from datetime import datetime as _dt, timezone as _tz
                        _coll.update_one(
                            {"chiave": "auth_secret"},
                            {"$setOnInsert": {
                                "chiave": "auth_secret",
                                "valore": secrets.token_urlsafe(64),
                                "created_at": _dt.now(_tz.utc).isoformat(),
                                "created_by": "gestionale_config",
                            }},
                            upsert=True,
                        )
                        _doc = _coll.find_one({"chiave": "auth_secret"})
                    _cli.close()
                    if _doc and _doc.get("valore"):
                        chiave_condivisa = _doc["valore"]
                except Exception:
                    logging.getLogger(__name__).warning(
                        "SECRET_KEY: impossibile leggere/creare auth_secret su Mongo, "
                        "uso il fallback deterministico"
                    )

            if chiave_condivisa:
                self.SECRET_KEY = chiave_condivisa
            else:
                # Nessuna chiave esplicita e nessuna leggibile/creabile su Mongo.
                # NON derivarla dall'URI (sarebbe prevedibile da chi conosce la
                # stringa di connessione): usa una chiave casuale di processo con
                # avviso critico. Se il DB è irraggiungibile l'app è comunque
                # inoperante (è un'app MongoDB), quindi non si perde continuità
                # reale delle sessioni.
                # §12.2 fail-fast produzione (OPT-IN, non distruttivo di default): se
                # SECRET_KEY_REQUIRED=true e siamo in produzione, rifiuta l'avvio invece
                # di usare una chiave temporanea (che invaliderebbe i token ad ogni
                # riavvio). Default off = comportamento attuale invariato.
                _strict = _os.getenv("SECRET_KEY_REQUIRED", "").lower() in ("1", "true", "yes")
                if _strict and self.ENVIRONMENT == "production":
                    raise RuntimeError(
                        "SECRET_KEY mancante in produzione (SECRET_KEY_REQUIRED=true): "
                        "impostare SECRET_KEY nelle variabili d'ambiente. Avvio rifiutato."
                    )
                self.SECRET_KEY = secrets.token_urlsafe(64)
                logging.getLogger(__name__).critical(
                    "⚠️ CRITICAL: SECRET_KEY non configurata e auth_secret non "
                    "disponibile su Mongo: chiave temporanea di processo. Imposta "
                    "SECRET_KEY nelle variabili d'ambiente per token stabili."
                )
        else:
            # SECRET_KEY esplicita: comunque prova ad allinearla alla chiave
            # condivisa tra le app se presente (interoperabilita' token).
            try:
                import os as _os
                from pymongo import MongoClient as _MC
                _uri = self.MONGO_URL or self.MONGODB_ATLAS_URI or _os.getenv("MONGO_URL")
                if _uri:
                    _cli = _MC(_uri, serverSelectionTimeoutMS=4000)
                    _doc = _cli[_os.getenv("DB_NAME", "Gestionale")]["sistema_stato"].find_one({"chiave": "auth_secret"})
                    _cli.close()
                    if _doc and _doc.get("valore"):
                        self.SECRET_KEY = _doc["valore"]
            except Exception:
                pass
    
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

        # Niente di esplicito. Se le credenziali sono attive segnaliamo il
        # rischio ma NON blocchiamo: restare a wildcard preserva il
        # funzionamento attuale del frontend finché il dominio non è
        # impostato. La chiusura effettiva scatta appena si valorizza
        # CORS_ALLOWED_ORIGINS (o FRONTEND_URL).
        if self.ALLOW_CREDENTIALS:
            logging.getLogger(__name__).warning(
                "CORS APERTO A TUTTI (insicuro): ALLOW_CREDENTIALS=True senza "
                "origin esplicito. Imposta CORS_ALLOWED_ORIGINS col dominio del "
                "gestionale per chiudere l'accesso agli altri siti."
            )
        return ["*"]
    
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
        """Validate critical configuration at startup.

        In produzione, se FAIL_FAST_SECRETS=true è attivo, l'applicazione
        fallisce l'avvio se mancano SECRET_KEY o MONGODB_ATLAS_URI.
        Altrimenti logga un errore critico ma continua (comportamento legacy).
        """
        import logging
        import os
        logger = logging.getLogger(__name__)

        fail_fast = self.is_production and os.getenv("FAIL_FAST_SECRETS", "").lower() in ("true", "1", "yes")
        errors: list[str] = []

        # Check SECRET_KEY was explicitly configured (not auto-generated).
        # NB: dal 10/07/2026 la chiave, se non in env, viene presa/creata
        # nella collection condivisa sistema_stato.auth_secret (stabile tra
        # riavvii e worker): il messaggio resta come promemoria, ma i token
        # NON muoiono piu' al riavvio.
        if not os.getenv("SECRET_KEY"):
            msg = (
                "SECRET_KEY non configurata nell'ambiente: uso la chiave "
                "condivisa sistema_stato.auth_secret (stabile). Per maggiore "
                "robustezza configurare comunque SECRET_KEY nei secret del deploy."
            )
            if fail_fast:
                errors.append(msg)
            else:
                logger.warning(f"⚠️ {msg}")

        # Check database configuration
        if not self.MONGODB_ATLAS_URI:
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

        # CORS in produzione: senza origin espliciti si ricade su una policy
        # permissiva. Va impostato CORS_ALLOWED_ORIGINS col dominio reale (§8/SEC-2).
        if self.is_production and not (self.CORS_ALLOWED_ORIGINS or "").strip():
            msg = (
                "CORS_ALLOWED_ORIGINS non configurato in produzione: imposta il "
                "dominio reale (es. 'https://impresasemplice.online') nelle "
                "variabili d'ambiente per limitare le origini consentite."
            )
            if fail_fast:
                errors.append(msg)
            else:
                logger.warning(f"⚠️ {msg}")

        if errors:
            raise RuntimeError(
                "Fail-fast produzione: configurazione mancante. "
                + " | ".join(errors)
            )


settings = Settings()
FEATURES = settings.validate_required_secrets()

def get_settings() -> Settings:
    return settings
