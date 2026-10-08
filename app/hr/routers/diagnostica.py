"""
Diagnostica / Autotest dell'app
================================
Controlli DAL VIVO sul sistema reale (DB, collezioni, variabili d'ambiente, motori
dei flussi). A differenza di un file di test separato, questi controlli non
"invecchiano": esercitano le capacità correnti dell'app, quindi se domani qualcosa
si rompe diventano rossi. Pensato per la pagina "Diagnostica" (solo admin).

Ogni check ritorna: {area, nome, stato: "ok"|"warn"|"err", dettaglio}.
"""
import os
import asyncio
import shutil
import logging
from typing import Dict, Any, List
from fastapi import APIRouter

from app.hr.database import Database

logger = logging.getLogger(__name__)
router = APIRouter()

# Collezioni principali che devono essere sempre leggibili
COLLEZIONI = [
    ("dipendenti", "Anagrafica dipendenti"),
    ("cedolini", "Cedolini / buste paga"),
    ("paghe_mensili", "Paghe mensili (busta+bonifico)"),
    ("pagamenti_esiti", "Bonifici reali (banca)"),
    ("presenze_cloud", "Presenze"),
    ("turni_cloud", "Tipi turno"),
    ("assegnazioni_turni_cloud", "Assegnazioni turni"),
    ("turni_config", "Configurazione turni"),
    ("documenti_cloud", "Documenti dipendenti"),
    ("ferie_cloud", "Ferie & permessi"),
    ("richieste", "Richieste"),
    ("notifiche", "Notifiche"),
    ("alerts", "Avvisi & scadenze"),
]

# Variabili d'ambiente: (nome, obbligatoria?, a cosa serve)
# Dentro GestionaleCloud i nomi sono prefissati HR_ (vedi config.py/database.py).
ENV_VARS = [
    ("HR_SUPABASE_DB_URL|APPDIPENDENTI_DB_URL|SUPABASE_DB_URL", True, "Connessione Supabase/Postgres"),
    ("HR_JWT_SECRET|JWT_SECRET", True, "Firma token login"),
    ("PIN_HASH_ADMIN", True, "PIN amministratore centrale GestionaleCloud"),
    ("ANTHROPIC_API_KEY", False, "Estrazione AI documenti (opzionale)"),
]


@router.get("")
async def diagnostica() -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []

    def add(area, nome, stato, dettaglio=""):
        checks.append({"area": area, "nome": nome, "stato": stato, "dettaglio": dettaglio})

    # ---- DATABASE ----
    db = None
    try:
        db = Database.get_db()
        await asyncio.wait_for(db.ping(), timeout=10)
        add("Database", "Connessione Supabase/Postgres", "ok", "Connesso")
    except Exception as e:
        add("Database", "Connessione Supabase/Postgres", "err", str(e)[:200])

    # ---- COLLEZIONI LEGGIBILI ----
    if db is not None:
        for coll, label in COLLEZIONI:
            try:
                n = await db[coll].count_documents({})
                add("Collezioni", label, "ok", f"{n} record")
            except Exception as e:
                add("Collezioni", label, "err", str(e)[:160])

    # ---- VARIABILI D'AMBIENTE ----
    for nome, obbligatoria, scopo in ENV_VARS:
        presente = any(os.getenv(n) for n in nome.split("|"))
        if presente:
            add("Configurazione", nome, "ok", f"impostata · {scopo}")
        else:
            add("Configurazione", nome, "err" if obbligatoria else "info",
                f"{'MANCANTE (obbligatoria)' if obbligatoria else 'Opzionale, non configurata'} · {scopo}")

    # Le stesse alternative dei servizi effettivi; assenza totale = funzione
    # opzionale non attivata, configurazione parziale = intervento necessario.
    imap = [bool(os.getenv(a) or os.getenv(b)) for a, b in (
        ("IMAP_HOST", "IMAP_SERVER"), ("IMAP_USER", "IMAP_EMAIL"), ("IMAP_PASSWORD", "IMAP_PASS"))]
    add("Configurazione", "Import diretto dalla posta HR", "ok" if all(imap) else "warn" if any(imap) else "info",
        "Configurazione presente; connessione non provata" if all(imap) else
        "Configurazione incompleta: host, utente e password necessari" if any(imap) else
        "Non configurato; il caricamento dei file dalla pagina resta disponibile")
    conversione = bool(os.getenv("CONVERTAPI_TOKEN") or shutil.which("soffice") or shutil.which("libreoffice"))
    add("Configurazione", "Conversione DOCX in PDF", "ok" if conversione else "info",
        "Convertitore disponibile; conversione non eseguita" if conversione else
        "Non disponibile: configurare ConvertAPI oppure LibreOffice per convertire i contratti")
    firma = [bool(os.getenv(k)) for k in ("OPENAPI_CLIENT_ID", "OPENAPI_CLIENT_SECRET")]
    add("Configurazione", "Firma digitale OpenAPI", "ok" if all(firma) else "warn" if any(firma) else "info",
        "Credenziali configurate; firma non eseguita" if all(firma) else
        "Configurazione incompleta: servono entrambi i parametri OpenAPI" if any(firma) else
        "Servizio opzionale non attivato")

    # ---- FLUSSI / MOTORI ----
    # 1) Turni → Presenze
    try:
        from app.hr.routers import dipendenti_cloud
        getattr(dipendenti_cloud, "consolida_presenze_da_turni")
        add("Flussi", "Motore Turni→Presenze", "info", "Funzione presente; consolidamento non eseguito dalla diagnostica")
    except Exception as e:
        add("Flussi", "Motore Turni→Presenze", "err", str(e)[:160])

    # 2) Gmail → Documenti dipendente
    try:
        from app.hr.routers import dipendenti_cloud
        getattr(dipendenti_cloud, "_archivia_documento_cloud")
        getattr(dipendenti_cloud, "_indici_dipendenti")
        add("Flussi", "Posta HR→Documenti", "info",
            "Funzione presente; accesso alla casella e import non eseguiti dalla diagnostica")
    except Exception as e:
        add("Flussi", "Gmail→Documenti", "err", str(e)[:160])

    # 3) Associazione cedolino ↔ bonifico
    try:
        from app.hr.routers import dipendenti_cloud
        getattr(dipendenti_cloud, "associazioni_bonifici")
        add("Flussi", "Associazione cedolino↔bonifico", "info", "Funzione presente; nessuna associazione eseguita")
    except Exception as e:
        add("Flussi", "Associazione cedolino↔bonifico", "err", str(e)[:160])

    # ---- DATI UTILI ----
    if db is not None:
        try:
            from app.hr.services.stato_rapporto import e_in_forza
            attivi = 0
            async for dip in db.dipendenti.find({}, {"stato": 1, "attivo": 1, "in_carico": 1, "merged_into": 1}):
                attivi += int(e_in_forza(dip))
            add("Dati", "Dipendenti attivi", "ok" if attivi > 0 else "warn", f"{attivi} attivi")
        except Exception as e:
            add("Dati", "Dipendenti attivi", "err", str(e)[:120])
        try:
            buste_attesa = await db.paghe_mensili.count_documents(
                {"stato_pagamento": {"$in": ["in_attesa_pagamento", "parziale"]}})
            add("Dati", "Buste in attesa di pagamento", "ok", f"{buste_attesa}")
        except Exception as e:
            add("Dati", "Buste in attesa di pagamento", "err", str(e)[:120])

    riepilogo = {
        "ok": sum(1 for c in checks if c["stato"] == "ok"),
        "warn": sum(1 for c in checks if c["stato"] == "warn"),
        "err": sum(1 for c in checks if c["stato"] == "err"),
        "info": sum(1 for c in checks if c["stato"] == "info"),
        "totale": len(checks),
    }
    return {"riepilogo": riepilogo, "checks": checks}
