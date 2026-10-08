"""Archivio condiviso dai router Lotti.

In produzione usa il document store nello schema Lotti del progetto Supabase
GestionaleCloud. Le variabili restano prefissate ``LOTTI_`` per distinguere
le credenziali delle RPC dai client delle altre aree:

  LOTTI_SUPABASE_URL        URL del progetto Supabase GestionaleCloud
  LOTTI_SUPABASE_ANON_KEY   chiave anon del progetto
  LOTTI_DB_SECRET           segreto applicativo richiesto dalle RPC ``lotti_*``
  LOTTI_DB_NAME             nome logico del database (default ``Gestionale``)

Una configurazione Supabase mancante blocca l'avvio: nessun fallback silenzioso e
nessuna perdita al riavvio. Nessuna connessione Motor/pymongo verso un server
reale viene aperta.

Il caricamento delle variabili d'ambiente (.env) e' responsabilita' della
configurazione di GestionaleCloud (``app/config.py``).
"""

import logging
import os

logger = logging.getLogger("uvicorn.error")

DB_NAME = os.environ.get("LOTTI_DB_NAME", "Gestionale")
if os.environ.get("LOTTI_SUPABASE_URL"):
    from app.lotti.supabase_document_store import build_supabase_database

    database = build_supabase_database()
    STORAGE = "supabase"
else:
    raise RuntimeError(
        "Configurazione Supabase Lotti assente: impostare LOTTI_SUPABASE_URL, "
        "LOTTI_SUPABASE_ANON_KEY e LOTTI_DB_SECRET. Il fallback non persistente "
        "non e' consentito nel runtime."
    )


async def close_database():
    if hasattr(database, "close"):
        result = database.close()
        if hasattr(result, "__await__"):
            await result
