"""
Ceraldi ERP - Main Application
==============================
FastAPI + MongoDB Atlas | Refactored Modular Architecture
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Database
from app.middleware.error_handler import add_exception_handlers
from app.utils.logger import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)

_PROJECT_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
_FRONTEND_DIST = os.path.realpath(os.path.join(_PROJECT_ROOT, "frontend", "dist"))
_FRONTEND_PUBLIC = os.path.realpath(os.path.join(_PROJECT_ROOT, "frontend", "public"))
SALARI_SYNC_MARKER = "sync_prima_nota_salari_da_cedolini_2018_20260804_v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup, yield, shutdown."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    try:
        await Database.connect_db()
    except Exception as e:
        logger.error(f"Database connection failed: {e}")

    settings.validate_startup()

    # Bus eventi unico (app/services/event_bus.py): include anche gli handler
    # migrati dal vecchio bus core (app/core/event_bus.py, rimosso).
    try:
        from app.services.event_bus import register_all_handlers

        register_all_handlers()
    except Exception as e:
        logger.warning(f"Event bus non inizializzato: {e}")

    try:
        from app.services.alert_engine import seed_alert_definitions

        db = Database.get_db()
        if db is not None:
            await seed_alert_definitions(db)
    except Exception as e:
        logger.warning(f"Seed alert_definitions non eseguito: {e}")

    if settings.ENVIRONMENT.lower() not in {"test", "testing"}:
        try:
            from app.scheduler import start_scheduler

            start_scheduler()
            logger.info("Scheduler avviato")
        except Exception as e:
            logger.warning(f"Scheduler non avviato: {e}")
    else:
        logger.info("Scheduler disabilitato nell'ambiente di test locale")

    try:
        db = Database.get_db()
        if db is not None:
            from app.routers.prima_nota_module.manutenzione import migrazione_pulisci_bancari_da_cassa

            await migrazione_pulisci_bancari_da_cassa()
    except Exception:
        pass

    # Operazione una tantum autorizzata: elimina i dati operativi antecedenti
    # al 2026 solo in produzione Render, dopo backup separato per collection.
    # Cedolini, prima nota salari e bonifici collegati sono esclusi e verificati.
    if os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID"):
        try:
            from app.routers.prima_nota_module.manutenzione import (
                esegui_pulizia_pregressi_una_tantum,
                neutralizza_versamenti_cassa_generati_da_ec,
                ripristina_provvisori_metodo_errato,
                ripristina_abbinamenti_banca_senza_identita,
            )

            pulizia = await esegui_pulizia_pregressi_una_tantum()
            if not pulizia.get("skipped"):
                logger.info(
                    "Pulizia pre-2026 completata: %s documenti archiviati ed eliminati",
                    pulizia.get("totale_eliminati", 0),
                )

            versamenti = await neutralizza_versamenti_cassa_generati_da_ec()
            if not versamenti.get("skipped"):
                logger.info(
                    "Versamenti creati dal solo estratto conto neutralizzati: cassa=%s banca=%s",
                    versamenti.get("cassa_neutralizzati", 0),
                    versamenti.get("banca_neutralizzati", 0),
                )

            # Ripara una sola volta le registrazioni automatiche sul lato
            # errato. Pagamenti manuali e riconciliati non vengono toccati.
            # Nuova regola 03/08/2026: anche una riga sul lato "banca"
            # torna provvisoria se fu creata automaticamente dal solo metodo
            # fornitore e non porta l'ID di un movimento reale. Soft-delete
            # reversibile: nessuna registrazione manuale/riconciliata toccata.
            repair_marker = "repair_bank_without_statement_20260803_v2"
            repair_run = await db["migration_runs"].find_one({"id": repair_marker})
            if not repair_run or repair_run.get("status") != "completed":
                riparazione = await ripristina_provvisori_metodo_errato(
                    dry_run=False, anno=2026,
                    banca_non_riconciliate=True, _admin={}
                )
                await db["migration_runs"].update_one(
                    {"id": repair_marker},
                    {"$set": {
                        "id": repair_marker,
                        "status": "completed",
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                        "result": riparazione,
                    }},
                    upsert=True,
                )
                if riparazione.get("corretti"):
                    logger.info(
                        "Fatture automatiche con metodo errato ripristinate: %s",
                        riparazione["corretti"],
                    )

            strict_marker = "revalidate_invoice_bank_identity_20260803_v2"
            strict_run = await db["migration_runs"].find_one({"id": strict_marker})
            if not strict_run or strict_run.get("status") != "completed":
                strict_result = await ripristina_abbinamenti_banca_senza_identita(
                    anno=2026, dry_run=False
                )
                await db["migration_runs"].update_one(
                    {"id": strict_marker},
                    {"$set": {"id": strict_marker, "status": "completed",
                              "finished_at": datetime.now(timezone.utc).isoformat(),
                              "result": strict_result}},
                    upsert=True,
                )
                logger.info(
                    "Auto-match banca rivalidati: validi=%s provvisori=%s",
                    strict_result.get("validi", 0),
                    strict_result.get("ripristinati_provvisori", 0),
                )

            # Correzione puntuale autorizzata 04/08/2026: l'addebito nomina
            # TIMAS, ma una precedente logica basata sul solo importo aveva
            # chiuso anche Carta & Party fattura 56. TIMAS resta associata;
            # viene riaperta esclusivamente la fattura estranea e l'estratto
            # conto originale non viene modificato/eliminato.
            carta_marker = "fix_carta_party_timas_collision_20260804_v1"
            carta_run = await db["migration_runs"].find_one({"id": carta_marker})
            if not carta_run or carta_run.get("status") != "completed":
                from app.routers.prima_nota_module.manutenzione import (
                    AnnullaAssociazioneFatturaBancaRequest,
                    annulla_associazione_fattura_banca,
                )
                try:
                    carta_result = await annulla_associazione_fattura_banca(
                        AnnullaAssociazioneFatturaBancaRequest(
                            partita_iva="05851861210",
                            numero_fattura="56",
                            importo_atteso=153.72,
                            motivo=(
                                "Correzione falsa associazione: il movimento bancario "
                                "indica TIMAS ASCENSORI e non Carta & Party"
                            ),
                        ),
                        {"username": "startup-migration"},
                    )
                    carta_status = "completed"
                except Exception as exc:
                    # Se la fattura e' gia' stata corretta o non e' presente,
                    # non si altera alcun dato e il tentativo resta tracciato.
                    # Lo stato resta failed affinche' un errore temporaneo di
                    # database venga ritentato automaticamente al prossimo avvio.
                    carta_result = {"skipped": True, "reason": str(exc)}
                    carta_status = "failed"
                await db["migration_runs"].update_one(
                    {"id": carta_marker},
                    {"$set": {"id": carta_marker, "status": carta_status,
                              "finished_at": datetime.now(timezone.utc).isoformat(),
                              "result": carta_result}},
                    upsert=True,
                )

            # La stessa correzione operativa conferma che Carta & Party ha
            # metodo predefinito misto. L'anagrafica resta riutilizzabile per
            # le fatture future, mentre la fattura riaperta rimane provvisoria
            # fino a una prova reale di pagamento.
            carta_method_marker = "set_carta_party_payment_method_misto_20260804_v1"
            carta_method_run = await db["migration_runs"].find_one(
                {"id": carta_method_marker}
            )
            if not carta_method_run or carta_method_run.get("status") != "completed":
                carta_method_status = "failed"
                try:
                    supplier_filter = {"$or": [
                        {"partita_iva": "05851861210"},
                        {"piva": "05851861210"},
                        {"vat_number": "05851861210"},
                    ]}
                    carta_supplier = await db["fornitori"].find_one(supplier_filter)
                    if not carta_supplier:
                        raise RuntimeError("Fornitore Carta & Party non trovato")
                    old_method = carta_supplier.get("metodo_pagamento") or ""
                    method_now = datetime.now(timezone.utc).isoformat()
                    update_method = {"$set": {
                        "metodo_pagamento": "misto",
                        "metodo_pagamento_dal": carta_supplier.get("metodo_pagamento_dal")
                        or method_now[:10],
                        "updated_at": method_now,
                    }}
                    if old_method != "misto":
                        update_method["$push"] = {"storico_metodi_pagamento": {
                            "metodo": "misto",
                            "dal": method_now[:10],
                            "registrato_il": method_now,
                            "fonte": "correzione_amministrativa",
                        }}
                    await db["fornitori"].update_one(supplier_filter, update_method)
                    carta_method_result = {
                        "success": True, "old_method": old_method,
                        "new_method": "misto",
                    }
                    carta_method_status = "completed"
                except Exception as exc:
                    carta_method_result = {"success": False, "reason": str(exc)}
                await db["migration_runs"].update_one(
                    {"id": carta_method_marker},
                    {"$set": {
                        "id": carta_method_marker,
                        "status": carta_method_status,
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                        "result": carta_method_result,
                    }},
                    upsert=True,
                )

            # Le versioni precedenti confondevano "copiata in Prima Nota"
            # con "riconciliata": riapriamo soltanto le righe generiche che
            # non hanno alcun documento collegato. In questo modo una fattura
            # XML importata dopo l'estratto puo' ancora trovare la sua uscita.
            reopen_marker = "reopen_generic_statement_rows_20260803_v1"
            reopen_run = await db["migration_runs"].find_one({"id": reopen_marker})
            if not reopen_run or reopen_run.get("status") != "completed":
                reopened = await db["estratto_conto_movimenti"].update_many(
                    {"tipo_riconciliazione": "auto_generico",
                     "$and": [
                         {"$or": [{"fattura_id": {"$exists": False}}, {"fattura_id": None}]},
                         {"$or": [{"documento_id": {"$exists": False}}, {"documento_id": None}]},
                     ]},
                    {"$set": {"riconciliato": False,
                              "importato_prima_nota": True,
                              "stato_riconciliazione": "da_verificare"},
                     "$unset": {"tipo_riconciliazione": ""}},
                )
                await db["migration_runs"].update_one(
                    {"id": reopen_marker},
                    {"$set": {"id": reopen_marker, "status": "completed",
                              "finished_at": datetime.now(timezone.utc).isoformat(),
                              "modified_count": reopened.modified_count}},
                    upsert=True,
                )
        except Exception as e:
            logger.error("Pulizia pregressi/riparazione metodo non completata: %s", e)

        # Riallineamento una tantum del registro salari al registro canonico
        # dei cedolini. I PDF vengono riletti per distinguere una mensilita'
        # ordinaria da 13a/14a; pagamenti e riconciliazioni esistenti restano
        # nei record originali e non vengono mai eliminati.
        try:
            salari_marker = SALARI_SYNC_MARKER
            salari_run = await db["migration_runs"].find_one({"id": salari_marker})
            if not salari_run or salari_run.get("status") != "completed":
                from app.services.salari_sync import sincronizza_prima_nota_da_cedolini

                salari_result = await sincronizza_prima_nota_da_cedolini(
                    db, anno_minimo=2018
                )
                await db["migration_runs"].update_one(
                    {"id": salari_marker},
                    {"$set": {
                        "id": salari_marker,
                        "status": "completed",
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                        "result": salari_result,
                    }},
                    upsert=True,
                )
                logger.info("Riallineamento cedolini/salari completato: %s", salari_result)
        except Exception as e:
            logger.error("Riallineamento cedolini/salari non completato: %s", e)

    # Backfill: fatture importate da Drive/bulk prima del fix campi — senza
    # `anno`/`data_documento` non comparivano nei filtri per anno.
    try:
        db = Database.get_db()
        if db is not None:
            r = await db["invoices"].update_many(
                {"anno": {"$exists": False},
                 "invoice_date": {"$regex": r"^\d{4}-"}},
                [{"$set": {
                    "anno": {"$toInt": {"$substrCP": ["$invoice_date", 0, 4]}},
                    "data_documento": {"$ifNull": ["$data_documento", "$invoice_date"]},
                    "numero_fattura": {"$ifNull": ["$numero_fattura", "$invoice_number"]},
                    "cedente_denominazione": {"$ifNull": ["$cedente_denominazione", "$supplier_name"]},
                    "cedente_piva": {"$ifNull": ["$cedente_piva", "$supplier_vat"]},
                }}],
            )
            if r.modified_count:
                logger.info(f"Backfill fatture senza anno: {r.modified_count} aggiornate")
    except Exception as e:
        logger.warning(f"Backfill anno fatture non eseguito: {e}")

    # Migrazione: assegni auto-associati con beneficiario sintetico
    # "Pag. fatt. X - Y" invece di un vero nome beneficiario. Li riporta a
    # "da associare" senza perdere il collegamento alla fattura già trovato.
    try:
        db = Database.get_db()
        if db is not None:
            r = await db["assegni"].update_many(
                {"beneficiario": {"$regex": r"^Pag\. fatt\. "}},
                {"$set": {"beneficiario": "", "stato": "vuoto"}},
            )
            if r.modified_count:
                logger.info(f"Corretti {r.modified_count} assegni con beneficiario fittizio")
    except Exception as e:
        logger.warning(f"Pulizia beneficiari fittizi assegni non eseguita: {e}")

    # Migrazione: gli ammortamenti cespiti venivano registrati anche come
    # "uscita" reale in prima_nota_cassa (costo non monetario che abbassava
    # il saldo cassa). Soft-delete dei movimenti generati da quel bug:
    # riconoscibili senza ambiguità dal source dedicato.
    try:
        db = Database.get_db()
        if db is not None:
            r = await db["prima_nota_cassa"].update_many(
                {"source": "ammortamento_cespiti", "status": {"$ne": "deleted"}},
                {"$set": {"status": "deleted",
                          "nota_migrazione": "ammortamento non monetario, rimosso dalla cassa"}},
            )
            if r.modified_count:
                logger.info(f"Neutralizzati {r.modified_count} movimenti cassa da ammortamenti (non monetari)")
    except Exception as e:
        logger.warning(f"Pulizia ammortamenti in cassa non eseguita: {e}")

    logger.info("Application startup complete")
    yield

    logger.info("Shutting down...")
    try:
        from app.services.email_monitor_service import stop_monitor

        stop_monitor()
    except Exception:
        pass
    try:
        from app.scheduler import stop_scheduler

        stop_scheduler()
    except Exception:
        pass
    await Database.close_db()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=settings.ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
    # Sessione scorrevole: il browser deve poter leggere il token rinnovato
    expose_headers=["X-Token-Rinnovato"],
)

try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    # Audit sicurezza 19/07/2026: il Limiter era istanziato ma senza questo
    # middleware default_limits non veniva mai applicato — nessun endpoint
    # (tranne login/PIN, che hanno il loro lockout dedicato) aveva un limite
    # di richieste reale.
    app.add_middleware(SlowAPIMiddleware)
except ImportError:
    pass

from app.middleware.authentication import AuthenticationMiddleware

app.add_middleware(AuthenticationMiddleware)
add_exception_handlers(app)

from app.router_registry import register_all_routers

register_all_routers(app)


def _frontend_index_path() -> str | None:
    for root in (_FRONTEND_DIST, _FRONTEND_PUBLIC):
        index_path = os.path.join(root, "index.html")
        if os.path.isfile(index_path):
            return index_path
    return None


# Bug segnalato dall'utente 17/07/2026 ("non vedo niente di live"): l'index
# veniva servito SENZA Cache-Control, quindi il browser (specie la PWA su
# telefono) applicava la cache euristica e continuava a caricare i chunk JS
# vecchi anche dopo il deploy. no-cache = il browser riconvalida l'index a
# ogni apertura (costa un 304 da pochi byte) e prende subito il bundle nuovo.
_INDEX_HEADERS = {"Cache-Control": "no-cache"}


def _index_response(index_path: str) -> FileResponse:
    return FileResponse(index_path, headers=_INDEX_HEADERS)


def _static_response(file_path: str) -> FileResponse:
    # I file dentro /assets hanno l'hash del contenuto nel nome: se cambiano,
    # cambia l'URL — la cache lunga e "immutable" è sicura e velocizza l'app.
    if f"{os.sep}assets{os.sep}" in file_path:
        return FileResponse(
            file_path, headers={"Cache-Control": "public, max-age=31536000, immutable"}
        )
    # Altri file statici (icone, manifest, service-worker): riconvalida.
    return FileResponse(file_path, headers=_INDEX_HEADERS)


def _safe_frontend_file(root: str, requested_path: str) -> str | None:
    safe_path = os.path.normpath(requested_path).lstrip("/\\")
    if not safe_path:
        return None
    candidate = os.path.realpath(os.path.join(root, safe_path))
    root_prefix = root if root.endswith(os.sep) else root + os.sep
    if os.path.isfile(candidate) and candidate.startswith(root_prefix):
        return candidate
    return None


@app.get("/")
async def root(request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        index_path = _frontend_index_path()
        if index_path:
            return _index_response(index_path)
    return {"app": settings.APP_NAME, "version": settings.APP_VERSION, "status": "online"}


@app.get("/health")
@app.get("/api/health")
async def health_check():
    from datetime import datetime, timezone

    salari_sync = "not_started"
    try:
        if Database.db is not None:
            run = await Database.db["migration_runs"].find_one(
                {"id": SALARI_SYNC_MARKER}, {"_id": 0, "status": 1}
            )
            salari_sync = (run or {}).get("status") or "not_started"
    except Exception:
        salari_sync = "unavailable"

    return {
        "status": "healthy",
        "database": "connected" if Database.db is not None else "disconnected",
        "version": settings.APP_VERSION,
        # Prefisso pubblico e non sensibile: permette di verificare che
        # Render stia realmente servendo il commit atteso.
        "deploy_commit": (os.getenv("RENDER_GIT_COMMIT") or "")[:8] or None,
        "salari_sync": salari_sync,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/ping")
async def ping():
    return {"pong": True}


@app.get("/api/system/lock-status")
async def system_lock_status():
    from app.routers.documenti import get_current_operation, is_email_operation_running

    return {
        "email_locked": is_email_operation_running(),
        "operation": get_current_operation(),
        "can_start_email_operation": not is_email_operation_running(),
    }


docs_path = "./docs"
os.makedirs(docs_path, exist_ok=True)
app.mount("/api/download", StaticFiles(directory=docs_path), name="download")

class _HashedAssets(StaticFiles):
    """Asset con hash nel nome (index-BJ8lb5ff.js): cache lunga sicura."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


if os.path.isdir(_FRONTEND_DIST):
    assets_path = os.path.join(_FRONTEND_DIST, "assets")
    if os.path.isdir(assets_path):
        app.mount("/assets", _HashedAssets(directory=assets_path), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    async def serve_spa_dist(request: Request, full_path: str) -> FileResponse | JSONResponse:
        if full_path.startswith("api/") or full_path == "api":
            return JSONResponse({"detail": "Not found"}, status_code=404)
        static_file = _safe_frontend_file(_FRONTEND_DIST, full_path)
        if static_file:
            return _static_response(static_file)
        return _index_response(os.path.join(_FRONTEND_DIST, "index.html"))

    logger.info("Frontend dist montato")
elif os.path.isdir(_FRONTEND_PUBLIC):

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    async def serve_spa_public(request: Request, full_path: str) -> FileResponse | JSONResponse:
        if full_path.startswith("api/") or full_path == "api":
            return JSONResponse({"detail": "Not found"}, status_code=404)
        static_file = _safe_frontend_file(_FRONTEND_PUBLIC, full_path)
        if static_file:
            return _static_response(static_file)
        return _index_response(os.path.join(_FRONTEND_PUBLIC, "index.html"))

    logger.info("Frontend public montato")

# reload-trigger
