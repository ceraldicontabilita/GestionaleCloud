"""Archivio condiviso dai router Lotti.

In produzione usa il document store Supabase dedicato a Lotti (progetto
DIVERSO da quello di GestionaleCloud, per questo le variabili sono prefissate
``LOTTI_``):

  LOTTI_SUPABASE_URL        URL del progetto Supabase di Lotti
  LOTTI_SUPABASE_ANON_KEY   chiave anon del progetto
  LOTTI_DB_SECRET           segreto applicativo richiesto dalle RPC ``lotti_*``
  LOTTI_DB_NAME             nome logico del database (default ``Gestionale``)

Senza ``LOTTI_SUPABASE_URL`` l'archivio e' un Mongo finto in memoria
(``mongomock-motor``): utile per test e collaudi locali, ma i dati NON
sopravvivono al riavvio del processo. Nessuna connessione Motor/pymongo verso
un server reale viene mai aperta.

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
    _client = None
    STORAGE = "supabase"
else:
    from mongomock_motor import AsyncMongoMockClient

    _client = AsyncMongoMockClient()
    database = _client[DB_NAME]
    STORAGE = "memoria"
    logger.warning(
        "Lotti: archivio in memoria, dati non persistenti (impostare "
        "LOTTI_SUPABASE_URL, LOTTI_SUPABASE_ANON_KEY e LOTTI_DB_SECRET per "
        "la persistenza su Supabase)"
    )


async def close_database():
    # Prima il client in memoria: su un database mongomock ``hasattr(db, "close")``
    # e' sempre vero (restituirebbe una collezione chiamata "close").
    if _client is not None:
        _client.close()
        return
    if hasattr(database, "close"):
        result = database.close()
        if hasattr(result, "__await__"):
            await result
