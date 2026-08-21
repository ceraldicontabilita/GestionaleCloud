"""Runtime Drive/Sheets del gestionale.

I fogli vengono letti in una cache documentale Python ricostruibile. Ogni
mutazione completata viene persistita nel foglio corrispondente prima che il
controllo torni al chiamante. Non esistono backend o driver alternativi.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

from app.services.google_sheets_ledger import (
    LedgerSheet,
    SHEETS,
    canonical_id,
    ensure_collection_sheet,
    portable_document,
    remove_documents,
    restore_all,
    sync_collection_streaming,
    upsert_documents,
)
from app.services.sheets_document_store import SheetDatabase


logger = logging.getLogger(__name__)


class SheetsRuntimeDatabase(SheetDatabase):
    """Archivio documentale con persistenza write-through su Google Sheets."""

    def __init__(self, name: str, config: dict[str, Any]):
        super().__init__(name, mutation_hook=self._write_through)
        self._config = dict(config)
        self._by_collection = {sheet.collection: sheet for sheet in SHEETS}
        self._write_ready_collections = {sheet.collection for sheet in SHEETS}
        self._schema_lock = asyncio.Lock()
        self._remote_write_lock = asyncio.Lock()
        self._write_batch: ContextVar[dict[str, dict[str, Any]] | None] = (
            ContextVar(f"sheets_write_batch_{id(self)}", default=None)
        )
        self.hydration_result: dict[str, Any] | None = None

    async def hydrate(self) -> dict[str, Any]:
        provision = not bool(
            str(self._config.get("GOOGLE_SHEETS_LEDGER_ID") or "").strip()
        )
        self.loading = True
        try:
            result = await restore_all(
                self, self._config, apply=True, provision=provision,
            )
        finally:
            self.loading = False
        discovered_spreadsheet_id = str(result.get("spreadsheet_id") or "").strip()
        if discovered_spreadsheet_id:
            self._config["GOOGLE_SHEETS_LEDGER_ID"] = discovered_spreadsheet_id
        errors = sum(int(item.get("numero_errori") or 0) for item in result["fogli"])
        self._by_collection = {
            item["collezione"]: LedgerSheet(
                item["foglio"], item["collezione"], item["prefisso"],
            )
            for item in result["fogli"]
        }
        self.hydration_result = result
        if errors:
            # Una singola riga storica malformata non deve rendere invisibili
            # tutte le altre registrazioni valide. ``restore_all`` conserva la
            # riga originale nel foglio, la esclude dalla cache e ne mantiene
            # il dettaglio in ``hydration_result`` per l'audit amministrativo.
            logger.warning(
                "Archivio Sheets idratato con %s righe non valide escluse",
                errors,
            )
        logger.info(
            "Archivio Sheets idratato: %s righe in %s fogli",
            sum(int(item.get("valide") or 0) for item in result["fogli"]),
            len(result["fogli"]),
        )
        return result

    async def ensure_collection(self, collection_name: str) -> LedgerSheet:
        sheet = self._by_collection.get(collection_name)
        if sheet is not None and collection_name in self._write_ready_collections:
            return sheet
        async with self._schema_lock:
            sheet = self._by_collection.get(collection_name)
            if sheet is not None and collection_name in self._write_ready_collections:
                return sheet
            spreadsheet_id = str(self._config.get("GOOGLE_SHEETS_LEDGER_ID") or "")
            if not spreadsheet_id:
                raise RuntimeError("GOOGLE_SHEETS_LEDGER_ID mancante")
            sheet = await ensure_collection_sheet(spreadsheet_id, collection_name)
            self._by_collection[collection_name] = sheet
            self._write_ready_collections.add(collection_name)
            logger.info(
                "Foglio Drive dinamico predisposto: %s -> %s",
                collection_name,
                sheet.title,
            )
            return sheet

    async def _write_through(
        self,
        collection_name: str,
        method: str,
        before: list[dict[str, Any]],
        after: list[dict[str, Any]],
    ) -> None:
        batch = self._write_batch.get()
        if batch is not None:
            pending = batch.setdefault(
                collection_name, {"upserts": {}, "deletes": set()},
            )
            upserts = pending["upserts"]
            deletes = pending["deletes"]
            if method in {"delete_one", "delete_many", "find_one_and_delete"}:
                for document in before:
                    key = canonical_id(portable_document(document))
                    if key:
                        upserts.pop(key, None)
                        deletes.add(key)
                return
            for document in after:
                portable = portable_document(document)
                key = canonical_id(portable)
                if key:
                    deletes.discard(key)
                    upserts[key] = portable
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
            keys = [
                canonical_id(portable_document(document))
                for document in before
            ]
            await self.remove_documents(collection_name, keys)
            return
        await self.persist_documents(collection_name, after)

    @asynccontextmanager
    async def batch_writes(self):
        """Accorpa le mutazioni di uno stesso job in una chiamata per foglio.

        La cache documentale continua ad aggiornarsi subito, quindi le letture
        eseguite durante il job vedono lo stato corrente. Soltanto il traffico
        remoto verso Google Sheets viene rinviato alla fine e deduplicato per
        ``canonical_id``. Questo evita che un recupero storico di centinaia di
        corrispettivi rilegga l'indice del medesimo foglio centinaia di volte,
        saturando la memoria del servizio Render.
        """
        current = self._write_batch.get()
        if current is not None:
            # Un batch annidato partecipa alla stessa unita' di flush.
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
                            await self.remove_documents(collection_name, deletes)
                        if upserts:
                            await self.persist_documents(collection_name, upserts)
                finally:
                    self._write_batch.reset(token)

    async def flush_collection(self, collection_name: str) -> dict[str, Any]:
        sheet = await self.ensure_collection(collection_name)
        spreadsheet_id = str(self._config.get("GOOGLE_SHEETS_LEDGER_ID") or "")
        if not spreadsheet_id:
            raise RuntimeError("GOOGLE_SHEETS_LEDGER_ID mancante")
        return await sync_collection_streaming(self, sheet, spreadsheet_id)

    async def persist_documents(
        self, collection_name: str, documents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not documents:
            return {"aggiornati": 0, "inseriti": 0}
        sheet = await self.ensure_collection(collection_name)
        spreadsheet_id = str(self._config.get("GOOGLE_SHEETS_LEDGER_ID") or "")
        if not spreadsheet_id:
            raise RuntimeError("GOOGLE_SHEETS_LEDGER_ID mancante")
        return await upsert_documents(sheet, spreadsheet_id, documents)

    async def remove_documents(
        self, collection_name: str, canonical_ids: list[str],
    ) -> dict[str, Any]:
        if not canonical_ids:
            return {"rimossi": 0}
        sheet = await self.ensure_collection(collection_name)
        spreadsheet_id = str(self._config.get("GOOGLE_SHEETS_LEDGER_ID") or "")
        if not spreadsheet_id:
            raise RuntimeError("GOOGLE_SHEETS_LEDGER_ID mancante")
        return await remove_documents(sheet, spreadsheet_id, canonical_ids)

    async def list_collection_names(self, *args, **kwargs) -> list[str]:
        return sorted(set(self._by_collection) | set(self._tables))
