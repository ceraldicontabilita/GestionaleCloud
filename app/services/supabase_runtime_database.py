"""Runtime documentale Supabase del gestionale.

Mantiene la stessa interfaccia in memoria del precedente registro Sheets, ma
persiste ogni modifica nella tabella privata ``gestionale.documents``. Il
server non usa la password Postgres né la service-role: chiama esclusivamente
quattro RPC minimali protette da una chiave applicativa separata, conservata
nel secret store di Render.

La logica applicativa resta invariata: all'avvio i documenti vengono idratati
in memoria e le mutazioni sono propagate immediatamente a Supabase. Gli
upsert sono idempotenti sulla coppia ``(collection, id)``.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

import aiohttp

from app.services.sheets_document_store import SheetDatabase

logger = logging.getLogger(__name__)

_PAGE_SIZE = 1000
_WRITE_CHUNK_SIZE = 200


def _json_default(value: Any) -> str:
    from datetime import date, datetime
    from decimal import Decimal

    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _normalise_document(document: dict[str, Any]) -> dict[str, Any]:
    """Converte il documento nello stesso JSON che verra' salvato da Postgres."""
    return json.loads(json.dumps(document, ensure_ascii=False, default=_json_default))


def documents_digest(documents: list[dict[str, Any]]) -> str:
    """Impronta deterministica usata per il collaudo della migrazione."""
    canonical = [
        json.dumps(
            _normalise_document(document),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for document in sorted(documents, key=lambda item: str(item.get("_id", "")))
    ]
    return hashlib.sha256("\n".join(canonical).encode("utf-8")).hexdigest()


class SupabaseRuntimeDatabase(SheetDatabase):
    """Archivio documentale con persistenza write-through su Supabase."""

    def __init__(self, name: str, config: dict[str, Any]):
        super().__init__(name, mutation_hook=self._write_through)
        self._url = str(config.get("SUPABASE_URL") or "").strip().rstrip("/")
        self._publishable_key = str(
            config.get("SUPABASE_PUBLISHABLE_KEY") or ""
        ).strip()
        self._runtime_secret = str(
            config.get("SUPABASE_RUNTIME_SECRET") or ""
        ).strip()
        missing = [
            name
            for name, value in (
                ("SUPABASE_URL", self._url),
                ("SUPABASE_PUBLISHABLE_KEY", self._publishable_key),
                ("SUPABASE_RUNTIME_SECRET", self._runtime_secret),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Configurazione runtime Supabase incompleta: " + ", ".join(missing)
            )

        self._session: aiohttp.ClientSession | None = None
        self._known_collections: set[str] = set()
        self._remote_write_lock = asyncio.Lock()
        self._write_batch: ContextVar[dict[str, dict[str, Any]] | None] = (
            ContextVar(f"supabase_write_batch_{id(self)}", default=None)
        )
        self.hydration_result: dict[str, Any] | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=120),
                headers={
                    "apikey": self._publishable_key,
                    "x-gc-api-key": self._runtime_secret,
                    "Content-Type": "application/json",
                },
            )
        return self._session

    async def _rpc(self, function_name: str, payload: dict[str, Any]) -> Any:
        session = await self._get_session()
        url = f"{self._url}/rest/v1/rpc/{function_name}"
        async with session.post(url, json=payload) as response:
            body = await response.text()
            if response.status >= 400:
                try:
                    detail = (json.loads(body).get("message") or "errore remoto")[:240]
                except (TypeError, ValueError, AttributeError):
                    detail = "errore remoto"
                raise RuntimeError(
                    f"Supabase RPC {function_name} fallita "
                    f"(HTTP {response.status}): {detail}"
                )
            if not body:
                return None
            return json.loads(body)

    async def _manifest(self) -> list[dict[str, Any]]:
        result = await self._rpc("gc_collection_manifest", {})
        if not isinstance(result, list):
            raise RuntimeError("Manifest Supabase non valido")
        return result

    async def _fetch_collection_documents(
        self, collection_name: str, *, expected_count: int | None = None,
    ) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        offset = 0
        while expected_count is None or offset < expected_count:
            page = await self._rpc(
                "gc_fetch_collection",
                {
                    "p_collection": collection_name,
                    "p_offset": offset,
                    "p_limit": _PAGE_SIZE,
                },
            )
            if not isinstance(page, list):
                raise RuntimeError(
                    f"Risposta Supabase non valida per {collection_name}"
                )
            documents.extend(page)
            if len(page) < _PAGE_SIZE:
                break
            offset += len(page)
        return documents

    async def hydrate(self) -> dict[str, Any]:
        """Carica tutte le collezioni Supabase nella cache applicativa."""
        manifest = await self._manifest()
        self.loading = True
        totale_righe = 0
        dettaglio: list[dict[str, Any]] = []
        try:
            for item in manifest:
                collection_name = str(item.get("collection") or "").strip()
                expected_count = int(item.get("row_count") or 0)
                if not collection_name:
                    continue
                documents = await self._fetch_collection_documents(
                    collection_name, expected_count=expected_count,
                )
                if len(documents) != expected_count:
                    raise RuntimeError(
                        f"Idratazione incompleta per {collection_name}: "
                        f"attese {expected_count}, lette {len(documents)}"
                    )
                if documents:
                    await self[collection_name].hydrate_documents(
                        documents, copy_documents=False,
                    )
                self._known_collections.add(collection_name)
                totale_righe += len(documents)
                dettaglio.append({
                    "collezione": collection_name,
                    "valide": len(documents),
                    "numero_errori": 0,
                })
        finally:
            self.loading = False
        logger.info(
            "Archivio Supabase idratato: %s righe in %s collezioni",
            totale_righe,
            len(dettaglio),
        )
        result = {"fogli": dettaglio, "righe": totale_righe}
        self.hydration_result = result
        return result

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
            await self._delete_ids(
                collection_name,
                [str(document.get("_id")) for document in before],
            )
            return
        await self._upsert_documents(collection_name, after)

    async def bulk_seed(
        self, collection_name: str, documents: list[dict[str, Any]],
    ) -> int:
        """Upsert idempotente in blocchi, usato dalla migrazione controllata."""
        await self._upsert_documents(collection_name, documents)
        return len(documents)

    async def mirror_collection(
        self, collection_name: str, documents: list[dict[str, Any]],
    ) -> int:
        """Allinea esattamente una collezione, eliminando solo gli ID obsoleti.

        Serve alla copia di preparazione: una seconda esecuzione produce la
        stessa destinazione anche quando la sorgente ha cancellato record.
        """
        remote_documents = await self._fetch_collection_documents(collection_name)
        source_ids = {str(item.get("_id")) for item in documents}
        stale_ids = [
            str(item.get("_id"))
            for item in remote_documents
            if str(item.get("_id")) not in source_ids
        ]
        for start in range(0, len(stale_ids), _WRITE_CHUNK_SIZE):
            await self._delete_ids(
                collection_name,
                stale_ids[start:start + _WRITE_CHUNK_SIZE],
            )
        await self._upsert_documents(collection_name, documents)
        return len(documents)

    async def verify_collection(
        self, collection_name: str, source_documents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Rilegge la destinazione e confronta conteggio e contenuto canonico."""
        remote_documents = await self._fetch_collection_documents(collection_name)
        source_digest = documents_digest(source_documents)
        remote_digest = documents_digest(remote_documents)
        return {
            "righe_origine": len(source_documents),
            "righe_destinazione": len(remote_documents),
            "impronta_origine": source_digest,
            "impronta_destinazione": remote_digest,
            "coincide": (
                len(source_documents) == len(remote_documents)
                and source_digest == remote_digest
            ),
        }

    async def _upsert_documents(
        self, collection_name: str, documents: list[dict[str, Any]],
    ) -> None:
        if not documents:
            return
        normalised = [_normalise_document(document) for document in documents]
        for start in range(0, len(normalised), _WRITE_CHUNK_SIZE):
            chunk = normalised[start:start + _WRITE_CHUNK_SIZE]
            await self._rpc(
                "gc_upsert_documents",
                {"p_collection": collection_name, "p_documents": chunk},
            )

    async def _delete_ids(self, collection_name: str, ids: list[str]) -> None:
        clean_ids = [item for item in ids if item and item != "None"]
        if not clean_ids:
            return
        await self._rpc(
            "gc_delete_documents",
            {"p_collection": collection_name, "p_ids": clean_ids},
        )

    @asynccontextmanager
    async def batch_writes(self):
        """Accorpa le mutazioni di uno stesso job per collezione."""
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
        if self._session is not None and not self._session.closed:
            session, self._session = self._session, None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(session.close())
            else:
                loop.create_task(session.close())
