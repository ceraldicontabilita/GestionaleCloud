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

from app.services.google_sheets_ledger import (
    LedgerSheet, SHEETS, canonical_id, ensure_collection_sheet,
    portable_document, remove_documents, restore_all, sync_collection_streaming,
    upsert_documents,
)


logger = logging.getLogger(__name__)

MUTATING_METHODS = {
    "insert_one", "insert_many", "update_one", "update_many", "replace_one",
    "delete_one", "delete_many", "find_one_and_update", "find_one_and_replace",
    "find_one_and_delete", "bulk_write",
}
DELETE_METHODS = {"delete_one", "delete_many", "find_one_and_delete"}
MANY_METHODS = {"update_many", "delete_many"}
FILTERED_METHODS = {
    "update_one", "update_many", "replace_one", "delete_one", "delete_many",
    "find_one_and_update", "find_one_and_replace", "find_one_and_delete",
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
                await self._owner.ensure_collection(self._name)
                before = []
                if name in FILTERED_METHODS:
                    selector = args[0] if args else kwargs.get("filter", {})
                    length = 100000 if name in MANY_METHODS else 1
                    before = await self._collection.find(selector or {}).to_list(length)
                result = await target(*args, **kwargs)
                if name == "bulk_write":
                    # Fallback raro: resta streaming e non materializza mai
                    # 100.000 documenti in una singola lista Python.
                    await self._owner.flush_collection(self._name)
                    return result

                if name in DELETE_METHODS:
                    keys = [
                        canonical_id(portable_document(document))
                        for document in before
                    ]
                    await self._owner.remove_documents(self._name, keys)
                    return result

                ids = []
                inserted_id = getattr(result, "inserted_id", None)
                if inserted_id is not None:
                    ids.append(inserted_id)
                ids.extend(getattr(result, "inserted_ids", None) or [])
                ids.extend(
                    document.get("_id") for document in before
                    if document.get("_id") is not None
                )
                upserted_id = getattr(result, "upserted_id", None)
                if upserted_id is not None:
                    ids.append(upserted_id)
                # Conserva l'ordine e rimuove gli ID ripetuti senza imporre
                # che siano hashable (alcuni test usano tipi compatibili BSON).
                unique_ids = []
                for candidate in ids:
                    if not any(candidate == current for current in unique_ids):
                        unique_ids.append(candidate)
                documents = []
                if unique_ids:
                    documents = await self._collection.find(
                        {"_id": {"$in": unique_ids}}
                    ).to_list(len(unique_ids))
                elif isinstance(result, dict) and result:
                    documents = [result]
                await self._owner.persist_documents(self._name, documents)
                return result

        return write_through


class SheetsRuntimeDatabase:
    """Database in memoria idratato e persistito dai fogli Google Drive."""

    def __init__(self, name: str, config: dict[str, Any]):
        self._client = AsyncMongoMockClient()
        self._memory_db = self._client[name]
        self._config = dict(config)
        self._by_collection = {sheet.collection: sheet for sheet in SHEETS}
        # I fogli canonici vengono predisposti insieme al registro. I fogli
        # dinamici gia' presenti, invece, possono essere stati creati in
        # anticipo e risultare ancora privi dell'intestazione. Prima della
        # prima scrittura del processo li ripassiamo quindi attraverso
        # ``ensure_collection_sheet``: in questo modo Sheets non interpreta la
        # prima riga dati come intestazione e non accoda le righe successive a
        # partire da una colonna errata.
        self._write_ready_collections = {sheet.collection for sheet in SHEETS}
        self._collections: dict[str, SheetsRuntimeCollection] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._schema_lock = asyncio.Lock()
        self.hydration_result: dict[str, Any] | None = None

    async def hydrate(self) -> dict[str, Any]:
        # Con un ID esplicito il registro e' gia' predisposto: l'avvio web deve
        # soltanto leggerlo, senza ricreare alberi Drive o riformattare 23 fogli.
        provision = not bool(
            str(self._config.get("GOOGLE_SHEETS_LEDGER_ID") or "").strip()
        )
        result = await restore_all(
            self._memory_db, self._config, apply=True, provision=provision,
        )
        discovered_spreadsheet_id = str(result.get("spreadsheet_id") or "").strip()
        if discovered_spreadsheet_id:
            self._config["GOOGLE_SHEETS_LEDGER_ID"] = discovered_spreadsheet_id
        errors = sum(int(item.get("numero_errori") or 0) for item in result["fogli"])
        if errors:
            raise RuntimeError(
                f"Registro Drive non avviabile: {errors} righe non valide"
            )
        self._by_collection = {
            item["collezione"]: LedgerSheet(
                item["foglio"], item["collezione"], item["prefisso"],
            )
            for item in result["fogli"]
        }
        self.hydration_result = result
        logger.info(
            "Archivio Sheets idratato: %s righe in %s fogli",
            sum(int(item.get("valide") or 0) for item in result["fogli"]),
            len(result["fogli"]),
        )
        return result

    def lock_for(self, collection_name: str) -> asyncio.Lock:
        return self._locks.setdefault(collection_name, asyncio.Lock())

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
                collection_name, sheet.title,
            )
            return sheet

    async def flush_collection(self, collection_name: str) -> dict[str, Any]:
        sheet = await self.ensure_collection(collection_name)
        spreadsheet_id = str(self._config.get("GOOGLE_SHEETS_LEDGER_ID") or "")
        if not spreadsheet_id:
            raise RuntimeError("GOOGLE_SHEETS_LEDGER_ID mancante")
        return await sync_collection_streaming(
            self._memory_db, sheet, spreadsheet_id,
        )

    async def persist_documents(
        self, collection_name: str, documents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        sheet = await self.ensure_collection(collection_name)
        spreadsheet_id = str(self._config.get("GOOGLE_SHEETS_LEDGER_ID") or "")
        if not spreadsheet_id:
            raise RuntimeError("GOOGLE_SHEETS_LEDGER_ID mancante")
        return await upsert_documents(sheet, spreadsheet_id, documents)

    async def remove_documents(
        self, collection_name: str, canonical_ids: list[str],
    ) -> dict[str, Any]:
        sheet = await self.ensure_collection(collection_name)
        spreadsheet_id = str(self._config.get("GOOGLE_SHEETS_LEDGER_ID") or "")
        if not spreadsheet_id:
            raise RuntimeError("GOOGLE_SHEETS_LEDGER_ID mancante")
        return await remove_documents(sheet, spreadsheet_id, canonical_ids)

    def __getitem__(self, collection_name: str):
        return self._collections.setdefault(
            collection_name, SheetsRuntimeCollection(self, collection_name)
        )

    @property
    def client(self):
        """Client compatibile Motor usato soltanto dal runtime in memoria.

        Senza questa proprieta' ``__getattr__`` interpreta ``db.client`` come
        una collection chiamata ``client``. I flussi storici che tentano di
        aprire una sessione ricevono quindi una Collection e falliscono prima
        ancora di poter usare il fallback senza transazioni.
        """
        return self._client

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]

    async def list_collection_names(self, *args, **kwargs):
        return list(self._by_collection)

    def close(self) -> None:
        self._client.close()
