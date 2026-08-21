"""Runtime Drive/Sheets del gestionale.

I fogli vengono letti in una cache documentale Python ricostruibile. Ogni
mutazione completata viene persistita nel foglio corrispondente prima che il
controllo torni al chiamante. Non esistono backend o driver alternativi.
"""
from __future__ import annotations

import asyncio
import logging
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
        if method in {"delete_one", "delete_many", "find_one_and_delete"}:
            keys = [
                canonical_id(portable_document(document))
                for document in before
            ]
            await self.remove_documents(collection_name, keys)
            return
        await self.persist_documents(collection_name, after)

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
