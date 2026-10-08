"""Connessione Postgres diretta (asyncpg) del gestionale.

Usata dai servizi che lavorano su tabelle relazionali dello stesso progetto
Supabase (protocollo Drive, deposito HR) e non sull'archivio documentale
``gestionale.documents``, che passa dal runtime a RPC.

Il DSN viene letto ad ogni chiamata dalle stesse variabili, nello stesso
ordine, del deposito cedolini HR (``hr_cedolini_deposito.ENV_DSN_HR``): dopo la
fusione del 14/09/2026 c'e' un solo database e ``HR_SUPABASE_DB_URL`` (ruolo
``hr_app``, che ha i grant sulle tabelle del protocollo) e' la DSN viva.
``SUPABASE_DB_URL`` resta ultima: in produzione il 14/09 puntava ancora al
vecchio progetto (``tenant/user postgres.jqguwrahxeilcikplaxi not found``) e
il primo giro del protocollo e' fallito per questo.
"""
from __future__ import annotations

import os
from typing import Optional

ENV_DSN = ("HR_SUPABASE_DB_URL", "APPDIPENDENTI_DB_URL", "SUPABASE_DB_URL")
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
