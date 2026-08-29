"""Runtime Supabase (Postgres) del gestionale.

Sostituto write-through di ``SheetsRuntimeDatabase``: stesso modello
documentale (una "collezione" e' un insieme di documenti JSON, interrogati
in memoria con la stessa semantica find/update_one/insert_one già usata da
tutto il codice applicativo), ma persistito su una tabella Postgres reale
(``gestionale.documents``) invece che su Google Sheets.

Deliberatamente NON cambia la semantica di interrogazione: all'avvio l'intera
collezione viene caricata in memoria (come oggi con Sheets) e ogni mutazione
viene scritta subito su Postgres. Questo rende lo scambio di backend a basso
rischio — la logica applicativa esistente (fuzzy matching fornitori,
classificazione movimenti bancari, regole F24/IVA, ecc.) non cambia di una
riga. Una futura ottimizzazione (query SQL dirette su jsonb invece di
caricare tutto in RAM) è possibile in un secondo momento, senza toccare
ancora il resto del codice, cambiando solo questa classe.

ATTENZIONE — non ancora verificato contro il progetto Supabase reale da
questa sessione: qui non è disponibile la connection string (va impostata
solo su Render, mai in questo codice o in chat). Prima di usarlo in
produzione: test con dati reali, `python -m pytest -q`, verifica live di
almeno una collezione critica (es. `estratto_conto_movimenti`) in modalità
lettura, poi cutover secondo la checklist di CLAUDE.md.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

from app.services.sheets_document_store import SheetDatabase, SheetTable

try:
    import asyncpg
except ImportError:  # pragma: no cover - dipendenza opzionale finché non attivata
    asyncpg = None

logger = logging.getLogger(__name__)

_SCHEMA = "gestionale"
_TABLE = f"{_SCHEMA}.documents"


def _json_default(value: Any) -> str:
    from datetime import date, datetime
    from decimal import Decimal
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _encode(document: dict[str, Any]) -> str:
    payload = {k: v for k, v in document.items() if k != "_id"}
    return json.dumps(payload, ensure_ascii=False, default=_json_default)


class SupabaseRuntimeDatabase(SheetDatabase):
    """Archivio documentale con persistenza write-through su Postgres/Supabase."""

    def __init__(self, name: str, config: dict[str, Any]):
        super().__init__(name, mutation_hook=self._write_through)
        if asyncpg is None:
            raise RuntimeError(
                "Pacchetto 'asyncpg' mancante: aggiungerlo a backend/requirements.txt "
                "prima di usare DATA_BACKEND=supabase."
            )
        self._dsn = str(config.get("SUPABASE_DB_URL") or "").strip()
        if not self._dsn:
            raise RuntimeError("SUPABASE_DB_URL mancante per il runtime Supabase.")
        self._pool: "asyncpg.Pool | None" = None
        self._known_collections: set[str] = set()
        self._remote_write_lock = asyncio.Lock()
        self._write_batch: ContextVar[dict[str, dict[str, Any]] | None] = (
            ContextVar(f"supabase_write_batch_{id(self)}", default=None)
        )

    async def _get_pool(self) -> "asyncpg.Pool":
        if self._pool is None:
            # statement_cache_size=0: i pgbouncer/pooler di Supabase in modalità
            # transazione non supportano prepared statement persistenti.
            self._pool = await asyncpg.create_pool(
                dsn=self._dsn, min_size=1, max_size=10, statement_cache_size=0,
            )
        return self._pool

    async def hydrate(self) -> dict[str, Any]:
        """Carica ogni collezione presente su Postgres nella cache in memoria.

        Stesso contratto di ``SheetsRuntimeDatabase.hydrate()``: al termine,
        ``self[collection]`` risponde a find/update_one/insert_one dalla
        cache, con ogni scrittura successiva propagata subito su Postgres.
        """
        pool = await self._get_pool()
        self.loading = True
        totale_righe = 0
        dettaglio: list[dict[str, Any]] = []
        try:
            async with pool.acquire() as conn:
                collections = [
                    r["collection"] for r in await conn.fetch(
                        f"SELECT DISTINCT collection FROM {_TABLE} ORDER BY collection"
                    )
                ]
                for collection_name in collections:
                    rows = await conn.fetch(
                        f"SELECT id, data FROM {_TABLE} WHERE collection = $1",
                        collection_name,
                    )
                    documents = []
                    errori = 0
                    for row in rows:
                        try:
                            payload = json.loads(row["data"])
                        except (TypeError, ValueError):
                            errori += 1
                            continue
                        payload["_id"] = row["id"]
                        documents.append(payload)
                    if documents:
                        await self[collection_name].hydrate_documents(
                            documents, copy_documents=False,
                        )
                    self._known_collections.add(collection_name)
                    totale_righe += len(documents)
                    dettaglio.append({
                        "collezione": collection_name,
                        "valide": len(documents),
                        "numero_errori": errori,
                    })
        finally:
            self.loading = False
        logger.info(
            "Archivio Supabase idratato: %s righe in %s collezioni",
            totale_righe, len(dettaglio),
        )
        return {"fogli": dettaglio, "righe": totale_righe}

    async def _write_through(
        self,
        collection_name: str,
        method: str,
        before: list[dict[str, Any]],
        after: list[dict[str, Any]],
    ) -> None:
        self._known_collections.add(collection_name)
        batch = self._write_batch.get()
        if batch is not None:
            pending = batch.setdefault(collection_name, {"upserts": {}, "deletes": set()})
            if method in {"delete_one", "delete_many", "find_one_and_delete"}:
                for document in before:
                    doc_id = str(document.get("_id"))
                    pending["upserts"].pop(doc_id, None)
                    pending["deletes"].add(doc_id)
                return
            for document in after:
                doc_id = str(document.get("_id"))
                pending["deletes"].discard(doc_id)
                pending["upserts"][doc_id] = document
            return

        async with self._remote_write_lock:
            await self._persist_mutation(collection_name, method, before, after)

    async def _persist_mutation(
        self,
        collection_name: str,
        method: str,
        before: list[dict[str, Any]],
        after: list[dict[str, Any]],
    ) -> None:
        if method in {"delete_one", "delete_many", "find_one_and_delete"}:
            ids = [str(document.get("_id")) for document in before]
            await self._delete_ids(collection_name, ids)
            return
        await self._upsert_documents(collection_name, after)

    async def _upsert_documents(self, collection_name: str, documents: list[dict[str, Any]]) -> None:
        if not documents:
            return
        pool = await self._get_pool()
        rows = [
            (collection_name, str(document.get("_id")), _encode(document))
            for document in documents
        ]
        async with pool.acquire() as conn:
            await conn.executemany(
                f"""
                INSERT INTO {_TABLE} (collection, id, data)
                VALUES ($1, $2, $3::jsonb)
                ON CONFLICT (collection, id)
                DO UPDATE SET data = EXCLUDED.data
                """,
                rows,
            )

    async def _delete_ids(self, collection_name: str, ids: list[str]) -> None:
        ids = [i for i in ids if i and i != "None"]
        if not ids:
            return
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"DELETE FROM {_TABLE} WHERE collection = $1 AND id = ANY($2::text[])",
                collection_name, ids,
            )

    @asynccontextmanager
    async def batch_writes(self):
        """Accorpa le mutazioni di uno stesso job in una sola scrittura per
        collezione — stessa semantica di ``SheetsRuntimeDatabase.batch_writes``."""
        current = self._write_batch.get()
        if current is not None:
            yield None
            return

        async with self._remote_write_lock:
            batch: dict[str, dict[str, Any]] = {}
            token = self._write_batch.set(batch)
            try:
                yield None
            finally:
                try:
                    for collection_name, pending in batch.items():
                        deletes = sorted(pending["deletes"])
                        upserts = list(pending["upserts"].values())
                        if deletes:
                            await self._delete_ids(collection_name, deletes)
                        if upserts:
                            await self._upsert_documents(collection_name, upserts)
                finally:
                    self._write_batch.reset(token)

    async def list_collection_names(self, *args, **kwargs) -> list[str]:
        return sorted(self._known_collections | set(self._tables))

    def close(self) -> None:
        super().close()
        if self._pool is not None:
            pool, self._pool = self._pool, None
            asyncio.ensure_future(pool.close())
