"""Migrazione controllata dei dati di AppDipendenti nel registro del gestionale.

Sorgente: il Postgres/Supabase dell'app AppDipendenti (tabelle ``app_<nome>``
con colonne ``id text, doc jsonb``). Destinazione: il runtime documentale del
gestionale, collezioni ``hr_<nome>``, con i PDF spostati in
``gestionale.blobs`` dall'adattatore HR.

Regole (CLAUDE.md "cutover"): idempotente per identita' (stesso ``_id`` ->
stesso documento, mai un doppione), confronto dei conteggi sorgente/
destinazione per ogni tabella e per i documenti con binari, mai
cancellazione della sorgente. Si puo' rieseguire: ogni blocco cancella e
reinserisce i propri id. I PDF identici (stessa distinta su piu' bonifici,
stesso bonifico in piu' tabelle) finiscono nell'archivio una sola volta.

Uso da riga di comando (con le env del gestionale: DATA_BACKEND=supabase e
SUPABASE_*; la DSN sorgente e' la ``SUPABASE_DB_URL`` di AppDipendenti):

    python -m app.hr.migrazione_appdipendenti --sorgente "$APPDIPENDENTI_DB_URL"
    python -m app.hr.migrazione_appdipendenti --sorgente ... --dry-run
    python -m app.hr.migrazione_appdipendenti --sorgente ... --tabelle dipendenti,cedolini

Oppure dall'area amministrativa: ``POST /api/hr/admin/migrazione-appdipendenti``
(la DSN viene letta SOLO dall'env ``APPDIPENDENTI_DB_URL`` di Render).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from app.hr.db_adapter import BLOB_FIELDS, PREFIX

logger = logging.getLogger(__name__)

TABLE_PREFIX = "app_"
BATCH = 100


async def _connetti_sorgente(dsn: str):
    import asyncpg  # dipendenza usata solo dalla migrazione

    conn = await asyncpg.connect(dsn, timeout=30)
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    return conn


async def elenca_tabelle(conn) -> List[str]:
    rows = await conn.fetch(
        "select table_name from information_schema.tables "
        "where table_schema = 'public' and table_name like $1 order by table_name",
        TABLE_PREFIX + "%",
    )
    return [r["table_name"] for r in rows]


async def conta_sorgente(conn, tabella: str) -> Dict[str, int]:
    condizioni = " or ".join(f"doc ? '{campo}'" for campo in BLOB_FIELDS)
    row = await conn.fetchrow(
        f'select count(*) as n, count(*) filter (where {condizioni}) as con_blob from public."{tabella}"'
    )
    return {"documenti": int(row["n"]), "binari": int(row["con_blob"])}


async def _righe(conn, tabella: str) -> AsyncIterator[Dict[str, Any]]:
    async with conn.transaction():
        async for row in conn.cursor(f'select id, doc from public."{tabella}" order by id', prefetch=BATCH):
            doc = dict(row["doc"] or {})
            doc.setdefault("_id", str(row["id"]))
            doc.setdefault("id", doc["_id"])
            yield doc


@asynccontextmanager
async def _batch_remoto(runtime: Any):
    batch = getattr(runtime, "batch_writes", None)
    if callable(batch):
        async with batch():
            yield
    else:
        yield


async def migra_tabella(conn, hr_db: Any, runtime: Any, tabella: str, *, dry_run: bool, progress: Optional[Callable[[str, int], None]] = None) -> Dict[str, Any]:
    nome = tabella[len(TABLE_PREFIX):]
    collection = hr_db[nome]
    atteso = await conta_sorgente(conn, tabella)
    scritti = 0
    blocco: List[Dict[str, Any]] = []

    async def _scrivi(blocco: List[Dict[str, Any]]) -> None:
        nonlocal scritti
        if dry_run or not blocco:
            return
        ids = [d["_id"] for d in blocco]
        async with _batch_remoto(runtime):
            await collection.delete_many({"_id": {"$in": ids}})
            await collection.insert_many(blocco)
        scritti += len(blocco)
        if progress:
            progress(nome, scritti)

    async for doc in _righe(conn, tabella):
        blocco.append(doc)
        if len(blocco) >= BATCH:
            await _scrivi(blocco)
            blocco = []
    await _scrivi(blocco)

    if dry_run:
        return {"collezione": nome, "sorgente": atteso, "dry_run": True}

    destinazione = {
        "documenti": await collection.count_documents({}),
        "binari": await collection.count_with_blobs(),
    }
    coincide = destinazione == atteso
    return {"collezione": nome, "sorgente": atteso, "destinazione": destinazione, "coincide": coincide}


async def migra(dsn: str, *, tabelle: Optional[List[str]] = None, dry_run: bool = False, progress: Optional[Callable[[str, int], None]] = None) -> Dict[str, Any]:
    from app.database import Database as GestionaleDatabase
    from app.hr.database import Database as HRDatabaseAccess

    runtime = GestionaleDatabase.db
    if runtime is None:
        raise RuntimeError("Registro dati del gestionale non connesso")
    hr_db = HRDatabaseAccess.get_db()
    if not dry_run and not hr_db.blobs.persistent:
        raise RuntimeError("Migrazione consentita solo con DATA_BACKEND=supabase (archivio binari persistente)")

    conn = await _connetti_sorgente(dsn)
    try:
        disponibili = await elenca_tabelle(conn)
        if tabelle:
            richieste = [t if t.startswith(TABLE_PREFIX) else TABLE_PREFIX + t for t in tabelle]
            mancanti = sorted(set(richieste) - set(disponibili))
            if mancanti:
                raise ValueError(f"Tabelle non trovate nella sorgente: {', '.join(mancanti)}")
            da_migrare = richieste
        else:
            da_migrare = disponibili
        esiti = []
        for tabella in da_migrare:
            logger.info("Migrazione %s -> %s%s", tabella, PREFIX, tabella[len(TABLE_PREFIX):])
            esiti.append(await migra_tabella(conn, hr_db, runtime, tabella, dry_run=dry_run, progress=progress))
    finally:
        await conn.close()

    tutto_ok = all(e.get("coincide", True) for e in esiti)
    return {"dry_run": dry_run, "tabelle": esiti, "coincide": tutto_ok}


async def stato_destinazione() -> Dict[str, Any]:
    """Conteggi correnti delle collezioni HR (per la pagina di controllo)."""
    from app.database import Database as GestionaleDatabase
    from app.hr.database import Database as HRDatabaseAccess

    runtime = GestionaleDatabase.db
    if runtime is None:
        raise RuntimeError("Registro dati del gestionale non connesso")
    hr_db = HRDatabaseAccess.get_db()
    out = []
    for nome in await hr_db.list_collection_names():
        out.append({
            "collezione": nome,
            "documenti": await hr_db[nome].count_documents({}),
            "documenti_con_binari": await hr_db[nome].count_with_blobs(),
        })
    archivio = await hr_db.blobs.stats("")
    return {
        "collezioni": out,
        "binari_persistenti": hr_db.blobs.persistent,
        # file distinti salvati vs riferimenti dai documenti: la differenza
        # e' lo spazio risparmiato dalla deduplicazione a contenuto.
        "archivio_binari": archivio,
    }


def _main() -> None:
    parser = argparse.ArgumentParser(description="Migra i dati AppDipendenti nel gestionale")
    parser.add_argument("--sorgente", required=True, help="DSN Postgres di AppDipendenti (SUPABASE_DB_URL)")
    parser.add_argument("--tabelle", default="", help="elenco separato da virgole (default: tutte le app_*)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    async def _run():
        from app.database import Database as GestionaleDatabase
        await GestionaleDatabase.connect_db()
        tabelle = [t.strip() for t in args.tabelle.split(",") if t.strip()] or None
        esito = await migra(args.sorgente, tabelle=tabelle, dry_run=args.dry_run,
                            progress=lambda nome, n: print(f"  {nome}: {n} documenti"))
        print(json.dumps(esito, ensure_ascii=False, indent=2))
        if not esito["coincide"]:
            raise SystemExit(1)

    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run())


if __name__ == "__main__":
    _main()
