"""AppDipendenti — Backend FastAPI."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .database import Database
from .config import CORS_ORIGINS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def avvio(*, avvia_scheduler: bool = True):
    """Startup originale (DB, scheduler scadenze, seed TFR, scheduler paghe, fix avvio).

    Estratto dal lifespan cosi' che l'app ospite (GestionaleCloud, che monta
    questa app a /hr) possa richiamarlo dal proprio lifespan: Starlette NON
    propaga gli eventi lifespan alle sotto-applicazioni montate.
    """
    await Database.connect()
    if avvia_scheduler:
        try:
            from .services.scadenze_scheduler import start_scheduler
            start_scheduler()
        except Exception as e:
            logger.warning(f"Scadenzario non avviato: {e}")
    try:
        from .services.tfr_seed import seed_tfr_periodi
        await seed_tfr_periodi()
    except Exception as e:
        logger.warning(f"Seed TFR non avviato: {e}")
    if avvia_scheduler:
        try:
            from .services.paghe_scheduler import start_scheduler as start_paghe_scheduler
            start_paghe_scheduler()
        except Exception as e:
            logger.warning(f"Sincronizzazione paghe periodica non avviata: {e}")
    try:
        from .services.startup_fixes import applica_fix_avvio
        await applica_fix_avvio()
    except Exception as e:
        logger.warning(f"Fix avvio non eseguiti: {e}")


async def arresto():
    """Shutdown originale (stop scheduler + chiusura DB)."""
    try:
        from .services.scadenze_scheduler import stop_scheduler
        stop_scheduler()
    except Exception:
        pass
    try:
        from .services.paghe_scheduler import stop_scheduler as stop_paghe_scheduler
        stop_paghe_scheduler()
    except Exception:
        pass
    await Database.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await avvio()
    yield
    await arresto()


app = FastAPI(title="AppDipendenti — Ceraldi Group", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def register_routers():
    # Autenticazione strict per l'area gestione (niente bypass).
    from .utils.dependencies import require_admin, require_staff

    # Nessun login amministratore proprio (email/password o PIN): l'admin
    # entra dalla sessione del Gestionale, `pin_login` espone `/session`.
    from .routers import pin_login
    app.include_router(pin_login.router, prefix="/api/auth", tags=["PIN Login"])

    # Dipendenze di sicurezza riusate. STAFF = admin o responsabile_turni; ADMIN = solo admin.
    STAFF = [Depends(require_staff)]
    ADMIN = [Depends(require_admin)]

    from .routers.employees import dipendenti, buste_paga, employee_contracts, giustificativi, shifts, fascicolo_dipendente, accessi
    app.include_router(dipendenti.router, prefix="/api/dipendenti", tags=["Dipendenti"], dependencies=STAFF)
    app.include_router(accessi.router, prefix="/api/accessi", tags=["Accessi"])  # già protetto per-endpoint (admin)
    app.include_router(buste_paga.router, prefix="/api", tags=["Buste Paga"], dependencies=ADMIN)
    # Contratti: solo amministratore (JWT valido + ruolo admin).
    app.include_router(employee_contracts.router, prefix="/api/contracts", tags=["Contratti"],
                       dependencies=ADMIN)
    app.include_router(giustificativi.router, prefix="/api/giustificativi", tags=["Giustificativi"], dependencies=STAFF)
    app.include_router(shifts.router, prefix="/api/shifts", tags=["Turni"], dependencies=STAFF)
    app.include_router(fascicolo_dipendente.router, prefix="/api", tags=["Fascicolo"], dependencies=STAFF)

    from .routers import cedolini, tfr, attendance, richieste, portale_buste, turni, notifiche
    from .routers import dipendenti_cloud
    from .routers import portale_documenti
    from .routers import timbrature
    app.include_router(timbrature.router, prefix="/api/timbrature", tags=["Timbrature"])
    app.include_router(richieste.router, prefix="/api/richieste", tags=["Richieste"])
    app.include_router(portale_buste.router, prefix="/api/portale/buste", tags=["Portale Buste"])
    app.include_router(portale_documenti.router, prefix="/api/portale/documenti", tags=["Portale Documenti"])
    app.include_router(turni.router, prefix="/api/turni", tags=["Turni"])
    app.include_router(notifiche.router, prefix="/api/notifiche", tags=["Notifiche"])
    # App "Dipendenti in Cloud" (8 pagine HR) -> /api/dipendenti-cloud
    # Area gestione: JWT valido + ruolo admin o responsabile_turni (la pagina
    # Turni del responsabile carica dati da questo router).
    app.include_router(dipendenti_cloud.router, prefix="/api", tags=["Dipendenti Cloud"],
                       dependencies=[Depends(require_staff)])
    app.include_router(cedolini.router, prefix="/api/cedolini", tags=["Cedolini"], dependencies=ADMIN)
    app.include_router(tfr.router, prefix="/api/tfr", tags=["TFR"], dependencies=ADMIN)
    app.include_router(attendance.router, prefix="/api/attendance", tags=["Presenze"], dependencies=STAFF)

    # Cedolini e Libro Unico ERP: un solo motore, `app/services/cedolini_motore.py`,
    # chiamato dalla pipeline di ingest documentale. La copia `app/hr/routers/libro_unico_parser.py`, registrata
    # qui fino al 19/09/2026, non e' mai stata usata: scriveva su collection
    # `employees`/`buste_paga`/`presenze_mensili` le cui tabelle
    # (`hr.app_employees`, `hr.app_buste_paga`, `hr.app_presenze_mensili`) non
    # esistono in Supabase, e le sue rotte non avevano chiamanti.
    # Stessa storia per il router F24 (rimosso il 19/09/2026): scriveva sulla
    # collection `f24_pagamenti`, che in produzione NON ESISTE — l'unico
    # archivio F24 vivo e' `f24_unificato` (93 righe), alimentato solo da
    # `services/f24_canonico.salva_f24`. Nessuna rotta aveva chiamanti.
    from .routers import salari_unificati_v2
    app.include_router(salari_unificati_v2.router, prefix="/api/salari-v2", tags=["Salari V2"], dependencies=ADMIN)

    # Contabilità / Gestione Pagamenti (fatture passive, fornitori, documenti fiscali PEC)
    from .routers import contabilita
    app.include_router(contabilita.router, prefix="/api/contabilita", tags=["Contabilità"], dependencies=ADMIN)

    # Diagnostica / autotest dell'app (controlli dal vivo: DB, env, flussi)
    from .routers import diagnostica
    app.include_router(diagnostica.router, prefix="/api/diagnostica", tags=["Diagnostica"], dependencies=ADMIN)

    logger.info("✅ Router AppDipendenti registrati")


register_routers()


from app.services.health_probe import ProbeUnica, risposta_salute  # noqa: E402

# Budget della liveness: Render la chiama con un timeout di pochi secondi.
_HEALTH_TIMEOUT = 2.0
_probe_database = ProbeUnica("database HR")


async def _ping_database() -> None:
    db = Database.db
    if Database.backend == "supabase":
        await db.ping()
    elif Database.backend == "mongo":
        await db.command("ping")
    else:
        raise RuntimeError(f"backend HR non connesso ({Database.backend or 'avvio non completato'})")


def _auth_configurata() -> dict:
    """Quali segreti ci sono (sì/no), mai il valore."""
    from app.services import admin_pin
    from .config import _env

    return {
        # Senza, i token HR sono firmati con un segreto effimero di processo:
        # ogni riavvio butta fuori tutto il portale.
        "jwt_secret": bool(_env("HR_JWT_SECRET", "JWT_SECRET")),
        # PIN amministratore unico del gruppo (letto dal login ERP).
        "pin_admin": admin_pin.configured(),
    }


@app.get("/api/health")
async def health(strict: bool = False):
    """Salute del portale HR: commit pubblicato, database, segreti di accesso.

    Risponde entro ``_HEALTH_TIMEOUT`` secondi anche con il database appeso
    (``degraded``, HTTP 200); ``?strict=true`` rende 503 un guasto certo.
    """
    if Database.backend in ("supabase", "mongo"):
        esito_db = await _probe_database.esito(_ping_database, timeout=_HEALTH_TIMEOUT)
    elif Database.backend == "non_configurato":
        esito_db = None  # nessuna DSN: lo dice risposta_salute
    else:
        esito_db = ("failed", "connessione non ancora aperta (avvio in corso)")
    return risposta_salute(
        "hr",
        componenti={"database": esito_db},
        auth=_auth_configurata(),
        strict=strict,
        extra={"app": "AppDipendenti", "version": "1.0.0", "database_backend": Database.backend or None},
    )


# Serve frontend React in produzione.
# Dentro GestionaleCloud la build Vite (base '/hr/') vive in <repo>/frontend_hr/dist
# (compilata su Render, non committata): questo file sta in app/hr/,
# quindi parents[2] e' la radice del repository.
STATIC_DIR = str(Path(__file__).resolve().parents[2] / "frontend_hr" / "dist")
_frontend_montato = False


def serve_frontend_da(build_dir) -> bool:
    """Registra /assets + catch-all SPA per la build in `build_dir`.

    Va chiamata DOPO register_routers(): il catch-all finisce in coda alla
    tabella delle rotte e /api/... resta prioritario. Per un percorso che
    corrisponde a un file reale della build (favicon, manifest...) serve quel
    file; per tutto il resto (deep link tipo /dipendenti/turni, /portale)
    serve index.html. Idempotente; False se la cartella non esiste.
    """
    global _frontend_montato
    if _frontend_montato:
        return True
    build_dir = Path(build_dir)
    if not build_dir.is_dir() or not (build_dir / "index.html").is_file():
        return False
    assets_dir = build_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        # Le API inesistenti devono dare 404, non l'index.html dell'app.
        if full_path == "api" or full_path.startswith("api/"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Endpoint non trovato")
        if full_path:
            candidato = (build_dir / full_path).resolve()
            try:
                candidato.relative_to(build_dir.resolve())
                if candidato.is_file():
                    return FileResponse(str(candidato))
            except ValueError:
                pass
        # index.html mai in cache: il browser deve sempre scaricare la versione
        # nuova dopo ogni deploy (i bundle in /assets hanno l'hash nel nome,
        # quindi cambiano da soli). Senza questo header Chrome riusava una copia
        # vecchia e le voci nuove del menu "sparivano".
        return FileResponse(str(build_dir / "index.html"),
                            headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

    _frontend_montato = True
    logger.info("Frontend AppDipendenti servito da %s", build_dir)
    return True


serve_frontend_da(STATIC_DIR)
