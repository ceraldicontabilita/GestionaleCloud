"""
server.py — Bootstrap FastAPI HACCP Ceraldi.
Solo configurazione DB, registrazione router e middleware.
"""

from fastapi import FastAPI, APIRouter, Depends
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
from app.lotti.deploy_info import get_deploy_info
import asyncio
import os
import logging
import starlette.formparsers as _fp

# Il caricamento del .env e' di GestionaleCloud (app/config.py): qui nessun
# load_dotenv. Le variabili di Lotti sono prefissate LOTTI_ (vedi db.py).
from app.lotti.db import database as db, close_database, DB_NAME, STORAGE

app = FastAPI(title="HACCP Ceraldi API", version="2.0")
_startup_background_tasks: set[asyncio.Task] = set()

_fp.MultiPartParser.max_file_size = 1024 * 1024 * 100
_fp.MultiPartParser.max_files = 50_000

api_router = APIRouter(prefix="/api")

from app.lotti.auth import router as r_auth, auth_dependency
from app.lotti.routers.digest import router as r_digest

# ── HACCP core ──────────────────────────────────────────────────────────────
from app.lotti.routers.disinfestazione import router as r_disinfestazione
from app.lotti.routers.sanificazione import router as r_sanificazione
from app.lotti.routers.temperature_negative import router as r_temp_neg
from app.lotti.routers.temperature_positive import router as r_temp_pos
from app.lotti.routers.controllo_olio import router as r_controllo_olio
from app.lotti.routers.temperature_cottura import router as r_temperature_cottura
from app.lotti.routers.ricezione_merce import router as r_ricezione_merce
from app.lotti.routers.reclami_fornitori import router as r_reclami_fornitori
from app.lotti.routers.task_dipendenti import router as r_task_dipendenti
from app.lotti.routers.diagnostic import router as r_diagnostic
from app.lotti.routers.aggiornamento_ricette import router as r_aggiornamento_ricette
from app.lotti.routers.prodotti_master import router as r_prodotti_master
from app.lotti.routers.shelf_life import router as r_shelf_life
from app.lotti.routers.haccp_periodi_speciali import router as r_haccp_periodi
from app.lotti.routers.anomalie import router as r_anomalie
from app.lotti.routers.manuale_haccp import router as r_manuale
from app.lotti.routers.haccp_auto import router as r_haccp_auto
from app.lotti.routers.report_haccp import router as r_report_haccp
from app.lotti.routers.haccp_manuale_auto import router as r_haccp_manuale_auto
from app.lotti.routers.chiusure import router as r_chiusure

# ── Produzione e lotti ──────────────────────────────────────────────────────
from app.lotti.routers.ricette import router as r_ricette
from app.lotti.routers.lotti import router as r_lotti
from app.lotti.routers.lotti_fornitori import router as r_lotti_fornitori
from app.lotti.routers.lotti_produzione import router as r_lotti_produzione
from app.lotti.routers.produzioni import router as r_produzioni
from app.lotti.routers.stampa import router as r_stampa
from app.lotti.routers.farciture import router as r_farciture

# ── Food cost e ingredienti ─────────────────────────────────────────────────
from app.lotti.routers.food_cost import router as r_food_cost
from app.lotti.routers.ingredienti import router as r_ingredienti
from app.lotti.routers.materie_prime import router as r_materie_prime
from app.lotti.routers.normalizzazione import router as r_normalizzazione
from app.lotti.routers.etichette import router as r_etichette
from app.lotti.routers.schede_tecniche import router as r_schede_tecniche

# ── Fornitori e fatture ─────────────────────────────────────────────────────
from app.lotti.routers.fornitori import router as r_fornitori
from app.lotti.routers.fornitori_anagrafica import router as r_fornitori_anagrafica
from app.lotti.routers.fornitori_dedup import router as r_fornitori_dedup
from app.lotti.routers.fornitori_schede import router as r_fornitori_schede
from app.lotti.routers.fornitori_qualifica import router as r_fornitori_qualifica
from app.lotti.routers.fatture import router as r_fatture
from app.lotti.routers.sconti_merce import router as r_sconti

# ── Prodotti e vendita ──────────────────────────────────────────────────────
from app.lotti.routers.prodotti_vendita import router as r_prodotti_vendita
from app.lotti.routers.acquaviva import router as r_acquaviva
from app.lotti.routers.colazione import router as r_colazione
from app.lotti.routers.fornitori_rivendita import router as r_fornitori_rivendita
from app.lotti.routers.vendita_banco import router as r_vendita_banco
from app.lotti.routers.listino import router as r_listino
from app.lotti.azienda import router as r_azienda

# ── Magazzino e ordini ──────────────────────────────────────────────────────
from app.lotti.routers.magazzino_bar import router as r_magazzino_bar
from app.lotti.routers.magazzino_unificato import router as r_magazzino_unificato
from app.lotti.routers.ordini_fornitori import router as r_ordini_fornitori
from app.lotti.routers.email_ordini import router as r_email_ordini

# ── Cataloghi esterni (scraping) ────────────────────────────────────────────
from app.lotti.routers.saima import router as r_saima
from app.lotti.routers.saima_ricettari import router as r_saima_ricettari
from app.lotti.routers.mepa import router as r_mepa
from app.lotti.routers.cataloghi_arricchimento import router as r_cataloghi_arricchimento

# ── Sistema e infrastruttura ────────────────────────────────────────────────
from app.lotti.routers.costi_giornalieri import router as r_costi_giornalieri
from app.lotti.routers.corrispettivi import router as r_corrispettivi
from app.lotti.routers.attrezzature import router as r_attrezzature
from app.lotti.routers.pipeline import router as r_pipeline
from app.lotti.routers.scheduler import router as r_scheduler
from app.lotti.routers.stampanti import router as r_stampanti
from app.lotti.routers.controllo_dati import router as r_controllo_dati
from app.lotti.routers.backup import router as r_backup
from app.lotti.routers.supervisor_operativo import router as r_supervisor
from app.lotti.routers.tablet_operatori import router as r_tablet_operatori
from app.lotti.routers.log_attivita import router as r_log_attivita
from app.lotti.routers.utils import router as r_utils
from app.lotti.routers.ordini_app import router as r_ordini_app
from app.lotti.routers.gelati import router as r_gelati
from app.lotti.routers.catalogo_forno import router as r_catalogo_forno
from app.lotti.routers.cataloghi_prezzi import router as r_cataloghi_prezzi
from app.lotti.routers.fonti_catalogo import router as r_fonti_catalogo
from app.lotti.routers.collaudi import router as r_collaudi
from app.lotti.routers.gestionale_fatture import router as r_gestionale_fatture
from app.lotti.routers.dashboard_economica import router as r_dashboard_economica
from app.lotti.routers.produzione_consigliata import router as r_produzione_consigliata
from app.lotti.routers.ricerca_globale import router as r_ricerca_globale

for r in [
    r_disinfestazione, r_sanificazione, r_temp_neg, r_temp_pos, r_controllo_olio,
    r_temperature_cottura, r_ricezione_merce, r_aggiornamento_ricette,
    r_prodotti_master, r_ordini_app, r_shelf_life, r_haccp_periodi,
    r_anomalie, r_reclami_fornitori, r_task_dipendenti, r_diagnostic, r_manuale,
    r_haccp_auto, r_report_haccp, r_haccp_manuale_auto, r_chiusure,
    r_ricette, r_lotti, r_lotti_fornitori, r_lotti_produzione, r_produzioni,
    r_stampa, r_farciture, r_food_cost, r_ingredienti, r_materie_prime,
    r_normalizzazione, r_etichette, r_schede_tecniche, r_fornitori, r_fornitori_anagrafica,
    r_fornitori_dedup, r_fornitori_schede, r_fornitori_qualifica, r_fatture,
    r_sconti, r_prodotti_vendita, r_acquaviva, r_colazione, r_vendita_banco, r_listino, r_azienda, r_magazzino_bar, r_magazzino_unificato,
    r_gestionale_fatture,
    r_ordini_fornitori, r_email_ordini, r_saima, r_saima_ricettari,
    r_mepa, r_cataloghi_arricchimento, r_costi_giornalieri, r_corrispettivi, r_attrezzature, r_pipeline, r_scheduler,
    r_controllo_dati, r_backup, r_supervisor, r_tablet_operatori, r_log_attivita, r_utils, r_stampanti,
    r_gelati, r_auth, r_digest, r_catalogo_forno, r_cataloghi_prezzi, r_fornitori_rivendita, r_fonti_catalogo, r_collaudi,
    r_dashboard_economica, r_produzione_consigliata, r_ricerca_globale,
]:
    api_router.include_router(r)

app.include_router(api_router, dependencies=[Depends(auth_dependency)])

# Origini SEMPRE ammesse (unione con l'env CORS_ORIGINS): il dominio ufficiale
# ceraldiapp.it è nel codice perché l'env sul servizio Render potrebbe non
# sincronizzarsi dal blueprint — senza, il sito si apre ma le API sono mute.
_CORS_BASE = {
    "https://www.ceraldiapp.it",
    "https://ceraldiapp.it",
    "https://lotti-frontend.onrender.com",
    "http://localhost:3000",
}
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=sorted(_CORS_BASE | {
        o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()
    }),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    # Non dichiarare il servizio sano se l'archivio persistente non risponde:
    # evita deploy apparentemente verdi con pagine vuote.
    collezioni = await db.list_collection_names()
    return {
        "status": "ok",
        "db": DB_NAME,
        "storage": STORAGE,
        "collections": len(collezioni),
        "api_version": app.version,
        **get_deploy_info(),
    }


def _ing(nome, qta, unita="g", allergeni=None):
    return {"nome": nome, "quantita": qta, "unita": unita, "allergeni": allergeni or [], "fonte": "fattura_xml_o_magazzino"}


def _panino(nome, ingredienti, foto, note):
    allergeni = sorted({a for i in ingredienti for a in i.get("allergeni", [])})
    return {
        "nome": nome,
        "reparto": "rosticceria",
        "categoria": "panini",
        "tipo_produzione": "produzione_giornaliera",
        "porzioni": 1,
        "ingredienti": [i["nome"] for i in ingredienti],
        "ingredienti_dettaglio": ingredienti,
        "componenti": [{"tipo": "materia_prima", "nome": i["nome"], "quantita": i["quantita"], "unita_misura": i["unita"], "fonte": i["fonte"]} for i in ingredienti],
        "allergeni": allergeni,
        "allergeni_auto": allergeni,
        "foto_url": foto,
        "note": note,
        "approvata": True,
        "stagionale": False,
        "updated_at": datetime.now(timezone.utc),
    }


async def seed_panini_rosticceria():
    panini = [
        _panino("Panino Caprese", [_ing("Panuozzo", 1, "pz", ["glutine"]), _ing("Fiordilatte", 80, "g", ["latte"]), _ing("Pomodoro", 70), _ing("Insalata", 20), _ing("Olio extravergine di oliva", 5), _ing("Basilico", 1), _ing("Sale", 1)], "/images/ricette/panino-caprese.jpg", "Panuozzo caprese con fiordilatte, pomodoro e insalata."),
        _panino("Panino Prosciutto Crudo e Fiordilatte", [_ing("Panuozzo", 1, "pz", ["glutine"]), _ing("Prosciutto crudo", 70), _ing("Fiordilatte", 80, "g", ["latte"]), _ing("Insalata", 20), _ing("Olio extravergine di oliva", 5)], "/images/ricette/panino-crudo-fiordilatte.jpg", "Panuozzo con prosciutto crudo, fiordilatte e insalata."),
        _panino("Panino Prosciutto Cotto e Fiordilatte", [_ing("Panuozzo", 1, "pz", ["glutine"]), _ing("Prosciutto cotto", 70), _ing("Fiordilatte", 80, "g", ["latte"]), _ing("Insalata", 20), _ing("Olio extravergine di oliva", 5)], "/images/ricette/panino-cotto-fiordilatte.jpg", "Panuozzo con prosciutto cotto, fiordilatte e insalata."),
    ]
    for p in panini:
        p["id"] = "seed-" + p["nome"].lower().replace(" ", "-")
        p["created_at"] = datetime.now(timezone.utc)
        await db.ricette.update_one({"nome": p["nome"]}, {"$set": p}, upsert=True)


@app.on_event("startup")
async def startup_event():
    logging.info(f"[STARTUP] DB: {DB_NAME} ({STORAGE})")
    from app.lotti.eventi import registra_handlers
    registra_handlers()
    from app.lotti.routers.scheduler import setup_scheduler
    setup_scheduler()
    from app.lotti.routers.tablet_operatori import seed_operatori
    await seed_operatori()
    from app.lotti.routers.magazzino_bar import seed_magazzino_bar
    await seed_magazzino_bar()
    await seed_panini_rosticceria()
    try:
        from app.lotti.routers.ricette import seed_ricette_solo_nome
        await seed_ricette_solo_nome()
    except Exception as e:
        logging.warning(f"[STARTUP] seed ricette solo-nome: {e}")

    try:
        from app.lotti.routers.catalogo_forno import inizializza_cataloghi_precaricati
        risultati = await inizializza_cataloghi_precaricati()
        logging.info(f"[STARTUP] cataloghi fornitori: {risultati}")
    except Exception as e:
        # Il catalogo web continua a funzionare anche se un file precaricato e'
        # temporaneamente assente: non deve mai impedire l'avvio HACCP.
        logging.warning(f"[STARTUP] cataloghi fornitori: {e}")

    try:
        from app.lotti.routers.acquaviva import inizializza_mapping_vandemoortele_2026
        mapping = await inizializza_mapping_vandemoortele_2026()
        logging.info(f"[STARTUP] mapping Acquaviva/Vandemoortele: {mapping}")
    except Exception as e:
        logging.warning(f"[STARTUP] mapping Acquaviva/Vandemoortele: {e}")

    # Il document store Supabase carica ogni collezione al primo accesso. Se la
    # Home le richiede tutte insieme dopo un riavvio Render, le RPC si contendono
    # la connessione e l'operatore resta in attesa. Le precarichiamo una alla
    # volta, prima che il servizio venga dichiarato pronto. Le foto binarie sono
    # escluse: vengono lette solo quando richieste e non servono per le griglie.
    try:
        nomi_collezioni = await db.list_collection_names()
        priorita = ["dizionario_ingredienti", "dizionario_prodotti"]
        da_precaricare = priorita + sorted(
            nome for nome in nomi_collezioni
            if nome not in set(priorita) | {"foto_files"}
        )
        documenti_pronti = 0
        for nome in da_precaricare:
            documenti_pronti += await db[nome].count_documents({})
        logging.info(
            "[STARTUP] archivio pronto: %s collezioni, %s documenti",
            len(da_precaricare),
            documenti_pronti,
        )
    except Exception as e:
        # Un problema di pre-caricamento non deve impedire l'accesso ai moduli
        # HACCP: gli endpoint ritenteranno il caricamento in modo pigro.
        logging.warning(f"[STARTUP] pre-caricamento cataloghi: {e}")

    try:
        from app.lotti.routers.indici import crea_indici
        from app.lotti.db import database
        await crea_indici(database)
    except Exception as e:
        logging.warning(f"[STARTUP] Errore creazione indici: {e}")

    # Completa in background le schede prodotto usando esclusivamente le pagine
    # ufficiali dei fornitori. Il worker e' idempotente: ad ogni deploy riprende
    # soltanto i documenti che non hanno ancora la versione corrente.
    try:
        from app.lotti.routers.cataloghi_arricchimento import FONTI, _arricchisci_catalogo
        for fonte in FONTI:
            task = asyncio.create_task(
                _arricchisci_catalogo(fonte),
                name=f"arricchimento-catalogo-{fonte}",
            )
            _startup_background_tasks.add(task)
            task.add_done_callback(_startup_background_tasks.discard)
        logging.info("[STARTUP] arricchimento cataloghi avviato: %s", ", ".join(FONTI))
    except Exception as e:
        # Il catalogo resta subito consultabile anche se il worker non parte;
        # l'amministratore puo' rilanciarlo dall'endpoint dedicato.
        logging.warning(f"[STARTUP] avvio arricchimento cataloghi: {e}")


@app.on_event("shutdown")
async def shutdown_db_client():
    await close_database()
