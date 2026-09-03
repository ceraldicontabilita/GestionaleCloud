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
# Dentro GestionaleCloud i nomi sono prefissati HR_ (vedi config.py/database.py):
# il controllo accetta sia il nome prefissato sia quello originale (fallback).
ENV_VARS = [
    ("HR_SUPABASE_DB_URL|APPDIPENDENTI_DB_URL|SUPABASE_DB_URL|HR_MONGO_URL|MONGO_URL", True, "Connessione database"),
    ("HR_JWT_SECRET|JWT_SECRET", True, "Firma token login"),
    ("HR_PIN_CODE|PIN_CODE", True, "PIN amministratore"),
    ("HR_DB_NAME|DB_NAME", False, "Nome database (solo Mongo)"),
    ("IMAP_HOST", False, "Import documenti da Gmail"),
    ("IMAP_USER", False, "Import documenti da Gmail"),
    ("IMAP_PASSWORD", False, "Import documenti da Gmail (App Password)"),
    ("CONVERTAPI_TOKEN", False, "Conversione docx→PDF (firma)"),
    ("OPENAPI_CLIENT_ID", False, "Firma digitale OpenAPI"),
    ("OPENAPI_CLIENT_SECRET", False, "Firma digitale OpenAPI"),
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
        await db.command("ping")
        add("Database", "Connessione MongoDB", "ok", "Connesso")
    except Exception as e:
        add("Database", "Connessione MongoDB", "err", str(e)[:200])

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
            add("Configurazione", nome, "err" if obbligatoria else "warn",
                f"{'MANCANTE (obbligatoria)' if obbligatoria else 'non impostata'} · {scopo}")

    # ---- FLUSSI / MOTORI ----
    # 1) Turni → Presenze
    try:
        from app.hr.routers.dipendenti_cloud import consolida_presenze_da_turni  # noqa: F401
        add("Flussi", "Motore Turni→Presenze", "ok", "Consolidamento disponibile")
    except Exception as e:
        add("Flussi", "Motore Turni→Presenze", "err", str(e)[:160])

    # 2) Gmail → Documenti dipendente
    try:
        from app.hr.routers.dipendenti_cloud import _archivia_documento_cloud, _indici_dipendenti  # noqa: F401
        imap_ok = all(os.getenv(v) for v in ("IMAP_HOST", "IMAP_USER", "IMAP_PASSWORD"))
        if imap_ok:
            add("Flussi", "Gmail→Documenti", "ok", "Motore pronto e casella collegata")
        else:
            add("Flussi", "Gmail→Documenti", "warn", "Motore pronto, ma manca la casella (IMAP_* su Render)")
    except Exception as e:
        add("Flussi", "Gmail→Documenti", "err", str(e)[:160])

    # 3) Associazione cedolino ↔ bonifico
    try:
        from app.hr.routers.dipendenti_cloud import associazioni_bonifici  # noqa: F401
        add("Flussi", "Associazione cedolino↔bonifico", "ok", "Vista disponibile")
    except Exception as e:
        add("Flussi", "Associazione cedolino↔bonifico", "err", str(e)[:160])

    # ---- DATI UTILI ----
    if db is not None:
        try:
            attivi = await db.dipendenti.count_documents(
                {"$and": [{"merged_into": {"$exists": False}},
                          {"stato": {"$nin": ["cessato", "disattivo", "inattivo"]}}]})
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
        "totale": len(checks),
    }
    return {"riepilogo": riepilogo, "checks": checks}
