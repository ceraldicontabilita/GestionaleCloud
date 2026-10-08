"""Modulo Lotti (HACCP tracciabilità, ricette, food cost, ordini fornitori).

Backend portato pari pari dal repository ``ceraldicontabilita/Lotti``
(``backend/``) dentro GestionaleCloud come pacchetto ``app.lotti``: stessa
logica, stessi router, stesse rotte. Viene montato come sotto-applicazione
FastAPI a ``/lotti`` (le rotte diventano ``/lotti/api/...``); vedi
``app/lotti/embed.py`` per i punti di aggancio (app, avvio/arresto, frontend).

Variabili d'ambiente proprie (non collidono con quelle di GestionaleCloud):
``LOTTI_SUPABASE_URL``, ``LOTTI_SUPABASE_ANON_KEY``, ``LOTTI_DB_SECRET``,
``LOTTI_DB_NAME`` (default ``Gestionale``), ``LOTTI_AUTH_SECRET``.
"""
