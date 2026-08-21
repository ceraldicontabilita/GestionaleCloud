"""Cache SQLite effimera per il registro voluminoso delle transazioni POS.

Google Sheets resta l'archivio operativo e la sola fonte persistente. Questa
tabella sostituisce esclusivamente la copia Python in RAM ricostruita a ogni
avvio: il file SQLite vive nella directory temporanea del processo e viene
eliminato alla chiusura.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from typing import Any, Iterable

from app.services.sheets_document_store import (
    DeleteResult,
    DuplicateRecordError,
    InsertManyResult,
    InsertOneResult,
    ReturnRecord,
    SheetCursor,
    SheetTable,
    UpdateResult,
    _clone,
    _new_id,
    _seed_from_selector,
    apply_projection,
    apply_update,
    get_path,
    matches_filter,
)


def _json_default(value: Any) -> Any:
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    return str(value)


class PosDiskTable(SheetTable):
    """API documentale compatibile, con payload POS indicizzati su SQLite."""

    _SEARCH_COLUMNS = {
        "_id": "record_id",
        "id": "document_id",
        "operation_key": "operation_key",
        "transaction_key": "transaction_key",
        "legacy_transaction_key": "legacy_transaction_key",
        "data": "operation_date",
    }

    def __init__(self, database, name: str):
        super().__init__(database, name)
        handle = tempfile.NamedTemporaryFile(
            prefix="gestionalecloud-pos-", suffix=".sqlite3", delete=False,
        )
        self.path = handle.name
        handle.close()
        self._connection = sqlite3.connect(self.path)
        self._connection.execute("PRAGMA journal_mode=MEMORY")
        self._connection.execute("PRAGMA synchronous=OFF")
        self._connection.execute("PRAGMA temp_store=FILE")
        self._connection.executescript(
            """
            CREATE TABLE documents (
                record_id TEXT PRIMARY KEY,
                document_id TEXT,
                operation_key TEXT,
                transaction_key TEXT,
                legacy_transaction_key TEXT,
                operation_date TEXT,
                payload TEXT NOT NULL
            );
            CREATE INDEX idx_pos_document_id ON documents(document_id);
            CREATE INDEX idx_pos_operation_key ON documents(operation_key);
            CREATE INDEX idx_pos_transaction_key ON documents(transaction_key);
            CREATE INDEX idx_pos_legacy_key ON documents(legacy_transaction_key);
            CREATE INDEX idx_pos_operation_date ON documents(operation_date);
            """
        )

    @staticmethod
    def _payload(document: dict[str, Any]) -> str:
        return json.dumps(
            document, ensure_ascii=False, separators=(",", ":"),
            default=_json_default,
        )

    @staticmethod
    def _decoded(payload: str) -> dict[str, Any]:
        value = json.loads(payload)
        return value if isinstance(value, dict) else {}

    @classmethod
    def _row(cls, document: dict[str, Any]) -> tuple[Any, ...]:
        return (
            str(document["_id"]),
            str(document.get("id") or "") or None,
            str(document.get("operation_key") or "") or None,
            str(document.get("transaction_key") or "") or None,
            str(document.get("legacy_transaction_key") or "") or None,
            str(document.get("data") or "") or None,
            cls._payload(document),
        )

    def _all_documents(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT payload FROM documents",
        ).fetchall()
        return [self._decoded(row[0]) for row in rows]

    @staticmethod
    def _chunks(values: list[str], size: int = 800):
        for offset in range(0, len(values), size):
            yield values[offset:offset + size]

    def _indexed_documents(
        self, selector: dict[str, Any] | None,
    ) -> list[dict[str, Any]] | None:
        selector = selector or {}
        searches: list[tuple[str, list[str]]] = []
        if set(selector) == {"$or"} and isinstance(selector.get("$or"), list):
            for condition in selector["$or"]:
                if not isinstance(condition, dict) or len(condition) != 1:
                    return None
                field, rule = next(iter(condition.items()))
                column = self._SEARCH_COLUMNS.get(str(field))
                values = rule.get("$in") if isinstance(rule, dict) else None
                if column is None or not isinstance(values, (list, tuple, set)):
                    return None
                searches.append((column, [str(value) for value in values]))
        elif len(selector) == 1:
            field, rule = next(iter(selector.items()))
            column = self._SEARCH_COLUMNS.get(str(field))
            if column is None:
                return None
            if isinstance(rule, dict) and isinstance(rule.get("$in"), (list, tuple, set)):
                searches.append((column, [str(value) for value in rule["$in"]]))
            elif not isinstance(rule, dict):
                searches.append((column, [str(rule)]))
            else:
                return None
        elif not selector:
            return self._all_documents()
        else:
            return None

        found: dict[str, dict[str, Any]] = {}
        for column, values in searches:
            for chunk in self._chunks(list(dict.fromkeys(values))):
                if not chunk:
                    continue
                placeholders = ",".join("?" for _ in chunk)
                rows = self._connection.execute(
                    f"SELECT record_id, payload FROM documents "
                    f"WHERE {column} IN ({placeholders})",
                    chunk,
                ).fetchall()
                for record_id, payload in rows:
                    found.setdefault(record_id, self._decoded(payload))
        return list(found.values())

    def find(
        self, selector: dict[str, Any] | None = None,
        projection: dict[str, Any] | None = None, *args, **kwargs,
    ) -> SheetCursor:
        documents = self._indexed_documents(selector)
        if documents is None:
            documents = self._all_documents()
        return SheetCursor(
            apply_projection(document, projection)
            for document in documents
            if matches_filter(document, selector)
        )

    async def find_one(
        self, selector: dict[str, Any] | None = None,
        projection: dict[str, Any] | None = None, *args, **kwargs,
    ) -> dict[str, Any] | None:
        cursor = self.find(selector, projection)
        if kwargs.get("sort"):
            cursor.sort(kwargs["sort"])
        documents = await cursor.limit(1).to_list(1)
        return documents[0] if documents else None

    async def count_documents(
        self, selector: dict[str, Any] | None = None, *args, **kwargs,
    ) -> int:
        if not selector:
            row = self._connection.execute(
                "SELECT COUNT(*) FROM documents",
            ).fetchone()
            return int(row[0] if row else 0)
        documents = self._indexed_documents(selector)
        if documents is None:
            documents = self._all_documents()
        return sum(1 for document in documents if matches_filter(document, selector))

    async def estimated_document_count(self, *args, **kwargs) -> int:
        return await self.count_documents({})

    async def hydrate_documents(
        self, documents: Iterable[dict[str, Any]], *,
        copy_documents: bool = True, append: bool = False,
    ) -> int:
        if not self.database.loading:
            raise RuntimeError("hydrate_documents consentito solo durante l'idratazione")
        async with self._lock:
            if not append and await self.estimated_document_count():
                raise RuntimeError("hydrate_documents richiede una tabella vuota")
            rows = []
            for document in documents:
                stored = _clone(document) if copy_documents else document
                stored.setdefault("_id", _new_id())
                rows.append(self._row(stored))
            try:
                self._connection.executemany(
                    "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)", rows,
                )
                self._connection.commit()
            except sqlite3.IntegrityError as exc:
                self._connection.rollback()
                raise DuplicateRecordError(
                    f"Valore _id duplicato nel foglio {self.name}",
                ) from exc
            return len(rows)

    async def insert_one(self, document: dict[str, Any], *args, **kwargs) -> InsertOneResult:
        result = await self.insert_many([document])
        return InsertOneResult(result.inserted_ids[0])

    async def insert_many(
        self, documents: Iterable[dict[str, Any]], *args, **kwargs,
    ) -> InsertManyResult:
        async with self._lock:
            originals = list(documents)
            stored_documents = []
            for original in originals:
                stored = _clone(original)
                stored.setdefault("_id", _new_id())
                original.setdefault("_id", stored["_id"])
                stored_documents.append(stored)
            try:
                self._connection.executemany(
                    "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [self._row(document) for document in stored_documents],
                )
                self._connection.commit()
            except sqlite3.IntegrityError as exc:
                self._connection.rollback()
                raise DuplicateRecordError(
                    f"Valore duplicato nel foglio {self.name}",
                ) from exc
            await self._notify("insert_many", [], stored_documents)
            return InsertManyResult([document["_id"] for document in stored_documents])

    async def update_one(
        self, selector: dict[str, Any], update: dict[str, Any], *args,
        upsert: bool = False, **kwargs,
    ) -> UpdateResult:
        async with self._lock:
            before_document = await self.find_one(selector)
            if before_document is None:
                if not upsert:
                    return UpdateResult(0, 0)
                after_document = apply_update(
                    _seed_from_selector(selector), update, inserting=True,
                )
                after_document.setdefault("_id", _new_id())
                self._connection.execute(
                    "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
                    self._row(after_document),
                )
                self._connection.commit()
                await self._notify("update_one", [], [after_document])
                return UpdateResult(0, 0, after_document["_id"])

            after_document = apply_update(before_document, update)
            self._connection.execute(
                "UPDATE documents SET document_id=?, operation_key=?, "
                "transaction_key=?, legacy_transaction_key=?, operation_date=?, "
                "payload=? WHERE record_id=?",
                (*self._row(after_document)[1:], str(before_document["_id"])),
            )
            self._connection.commit()
            modified = int(after_document != before_document)
            await self._notify(
                "update_one", [before_document], [after_document],
            )
            return UpdateResult(1, modified)

    async def replace_one(
        self, selector: dict[str, Any], replacement: dict[str, Any], *args,
        upsert: bool = False, **kwargs,
    ) -> UpdateResult:
        return await self.update_one(selector, replacement, upsert=upsert)

    async def delete_one(
        self, selector: dict[str, Any], *args, **kwargs,
    ) -> DeleteResult:
        async with self._lock:
            document = await self.find_one(selector)
            if document is None:
                return DeleteResult(0)
            self._connection.execute(
                "DELETE FROM documents WHERE record_id=?", (str(document["_id"]),),
            )
            self._connection.commit()
            await self._notify("delete_one", [document], [])
            return DeleteResult(1)

    async def delete_many(
        self, selector: dict[str, Any], *args, **kwargs,
    ) -> DeleteResult:
        documents = await self.find(selector).to_list(None)
        if not documents:
            return DeleteResult(0)
        async with self._lock:
            self._connection.executemany(
                "DELETE FROM documents WHERE record_id=?",
                [(str(document["_id"]),) for document in documents],
            )
            self._connection.commit()
            await self._notify("delete_many", documents, [])
            return DeleteResult(len(documents))

    async def find_one_and_update(
        self, selector: dict[str, Any], update: dict[str, Any], *args,
        upsert: bool = False, return_document: Any = ReturnRecord.BEFORE,
        projection: dict[str, Any] | None = None, **kwargs,
    ) -> dict[str, Any] | None:
        before = await self.find_one(selector)
        await self.update_one(selector, update, upsert=upsert)
        after = await self.find_one(selector)
        chosen = after if self._return_after(return_document) else before
        return apply_projection(chosen, projection) if chosen is not None else None

    async def find_one_and_delete(
        self, selector: dict[str, Any], *args,
        projection: dict[str, Any] | None = None, **kwargs,
    ) -> dict[str, Any] | None:
        before = await self.find_one(selector)
        if before is not None:
            await self.delete_one(selector)
        return apply_projection(before, projection) if before is not None else None

    async def distinct(
        self, key: str, selector: dict[str, Any] | None = None, *args, **kwargs,
    ) -> list[Any]:
        values = []
        for document in await self.find(selector).to_list(None):
            value = get_path(document, key, None)
            if value is not None and value not in values:
                values.append(_clone(value))
        return values

    def aggregate(self, pipeline: list[dict[str, Any]], *args, **kwargs) -> SheetCursor:
        temporary = SheetTable(self.database, f"{self.name}:aggregate")
        temporary._documents = self._all_documents()
        return temporary.aggregate(pipeline, *args, **kwargs)

    def close(self) -> None:
        try:
            self._connection.close()
        finally:
            try:
                os.unlink(self.path)
            except FileNotFoundError:
                pass
