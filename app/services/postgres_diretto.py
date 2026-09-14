"""Connessione Postgres diretta (asyncpg) del gestionale.

Usata dai servizi che lavorano su tabelle relazionali dello stesso progetto
Supabase (protocollo Drive, deposito HR) e non sull'archivio documentale
``gestionale.documents``, che passa dal runtime a RPC.

Il DSN viene letto ad ogni chiamata dalle stesse variabili gia' usate dal
deposito cedolini HR: dopo la fusione del 14/09/2026 c'e' un solo database,
quindi ``HR_SUPABASE_DB_URL`` punta allo stesso Postgres dell'ERP.
"""
from __future__ import annotations

import os
from typing import Optional

ENV_DSN = ("SUPABASE_DB_URL", "HR_SUPABASE_DB_URL", "APPDIPENDENTI_DB_URL")
TIMEOUT_CONNESSIONE = 10
TIMEOUT_COMANDO = 120


def dsn() -> Optional[str]:
    """DSN Postgres, mai cachata: le env di Render possono cambiare a caldo."""
    for nome in ENV_DSN:
        valore = os.environ.get(nome)
        if valore:
            return valore
    return None


async def connetti(dsn_valore: str):
    """Apre una connessione asyncpg con timeout. Punto unico sostituito nei test."""
    import asyncpg

    return await asyncpg.connect(
        dsn_valore, timeout=TIMEOUT_CONNESSIONE, command_timeout=TIMEOUT_COMANDO
    )
