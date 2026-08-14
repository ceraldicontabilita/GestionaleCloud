"""Runtime asincrono con Google Sheets come archivio primario.

Il gestionale storico usa direttamente l'interfaccia Motor. Per migrare senza
riscrivere centinaia di servizi, i fogli canonici vengono caricati in un
database Mongo compatibile ma esclusivamente in memoria. Ogni mutazione viene
poi resa persistente nel foglio Drive corrispondente prima di restituire il
controllo al chiamante.

Nessuna connessione MongoDB esterna viene aperta in ``DATA_BACKEND=sheets``.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from mongomock_motor import AsyncMongoMockClient

from app.services.google_sheets_ledger import SHEETS, restore_all, sync_collection


logger = logging.getLogger(__name__)

MUTATING_METHODS = {
    "insert_one", "insert_many", "update_one", "update_many", "replace_one",
    "delete_one", "delete_many", "find_one_and_update", "find_one_and_replace",
    "find_one_and_delete", "bulk_write",
}


class SheetsRuntimeCollection:
    """Collection Motor-compatible con persistenza write-through su Drive."""

    def __init__(self, owner: "SheetsRuntimeDatabase", name: str):
        self._owner = owner
        self._name = name
        self._collection = owner._memory_db[name]

    def __getattr__(self, name: str) -> Any:
        target = getattr(self._collection, name)
        if name not in MUTATING_METHODS:
            return target

        async def write_through(*args, **kwargs):
            async with self._owner.lock_for(self._name):
                result = await target(*args, **kwargs)
                await self._owner.flush_collection(self._name)
                return result

        return write_through


class SheetsRuntimeDatabase:
    """Database in memoria idratato e persistito dai fogli Google Drive."""

    def __init__(self, name: str, config: dict[str, Any]):
        self._client = AsyncMongoMockClient()
        self._memory_db = self._client[name]
        self._config = dict(config)
        self._by_collection = {sheet.collection: sheet for sheet in SHEETS}
        self._collections: dict[str, SheetsRuntimeCollection] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self.hydration_result: dict[str, Any] | None = None

    async def hydrate(self) -> dict[str, Any]:
        result = await restore_all(self._memory_db, self._config, apply=True)
        errors = sum(int(item.get("numero_errori") or 0) for item in result["fogli"])
        if errors:
            raise RuntimeError(
                f"Registro Drive non avviabile: {errors} righe non valide"
            )
        self.hydration_result = result
        logger.info(
            "Archivio Sheets idratato: %s righe in %s fogli",
            sum(int(item.get("valide") or 0) for item in result["fogli"]),
            len(result["fogli"]),
        )
        return result

    def lock_for(self, collection_name: str) -> asyncio.Lock:
        return self._locks.setdefault(collection_name, asyncio.Lock())

    async def flush_collection(self, collection_name: str) -> dict[str, Any]:
        sheet = self._by_collection.get(collection_name)
        if sheet is None:
            raise RuntimeError(
                f"La collezione {collection_name} non ha un foglio Drive configurato"
            )
        spreadsheet_id = str(self._config.get("GOOGLE_SHEETS_LEDGER_ID") or "")
        if not spreadsheet_id:
            raise RuntimeError("GOOGLE_SHEETS_LEDGER_ID mancante")
        return await sync_collection(
            self._memory_db, sheet, spreadsheet_id, preserve_missing=False,
        )

    def __getitem__(self, collection_name: str):
        if collection_name not in self._by_collection:
            raise RuntimeError(
                f"Collezione {collection_name} non ancora migrata nel registro Drive"
            )
        return self._collections.setdefault(
            collection_name, SheetsRuntimeCollection(self, collection_name)
        )

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]

    async def list_collection_names(self, *args, **kwargs):
        return list(self._by_collection)

    def close(self) -> None:
        self._client.close()
