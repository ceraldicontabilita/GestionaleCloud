"""Archivio documentale asincrono usato dal runtime Google Sheets.

Il modulo offre operazioni CRUD, cursori e aggregazioni sui documenti caricati
dai fogli.  E' implementato soltanto con la libreria standard: la sorgente
persistente resta Google Sheets e la memoria del processo e' esclusivamente
una cache ricostruibile all'avvio.
"""
from __future__ import annotations

import asyncio
import copy
import re
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import IntEnum
from functools import cmp_to_key
from typing import Any, AsyncIterator, Awaitable, Callable, Iterable, Sequence


MISSING = object()


class DuplicateRecordError(RuntimeError):
    """Un vincolo univoco del registro impedisce la scrittura."""


class ReturnRecord(IntEnum):
    BEFORE = 0
    AFTER = 1


@dataclass(frozen=True)
class UpdateOperation:
    selector: dict[str, Any]
    update: dict[str, Any]
    upsert: bool = False


@dataclass
class InsertOneResult:
    inserted_id: Any


@dataclass
class InsertManyResult:
    inserted_ids: list[Any]


@dataclass
class UpdateResult:
    matched_count: int
    modified_count: int
    upserted_id: Any = None


@dataclass
class DeleteResult:
    deleted_count: int


@dataclass
class BulkWriteResult:
    matched_count: int = 0
    modified_count: int = 0
    upserted_count: int = 0


def _clone(value: Any) -> Any:
    return copy.deepcopy(value)


def _hashable_unique_value(value: Any) -> Any:
    """Converte valori JSON-like in chiavi hashabili senza cambiarne l'uguaglianza."""
    if value is MISSING:
        return ("missing",)
    if isinstance(value, dict):
        return (
            "dict",
            tuple(
                sorted(
                    ((str(key), _hashable_unique_value(item)) for key, item in value.items()),
                    key=lambda item: item[0],
                )
            ),
        )
    if isinstance(value, list):
        return ("list", tuple(_hashable_unique_value(item) for item in value))
    if isinstance(value, tuple):
        return ("tuple", tuple(_hashable_unique_value(item) for item in value))
    if isinstance(value, set):
        return ("set", frozenset(_hashable_unique_value(item) for item in value))
    try:
        hash(value)
    except TypeError:
        return ("repr", repr(value))
    return ("scalar", value)


def _new_id() -> str:
    return uuid.uuid4().hex


def _path_parts(path: str) -> list[str]:
    return [part for part in str(path).split(".") if part]


def _path_values(value: Any, parts: Sequence[str]) -> list[Any]:
    if not parts:
        return [value]
    if isinstance(value, list):
        values: list[Any] = []
        for item in value:
            values.extend(_path_values(item, parts))
        return values or [MISSING]
    if not isinstance(value, dict):
        return [MISSING]
    head, *tail = parts
    if head not in value:
        return [MISSING]
    return _path_values(value[head], tail)


def get_path(document: dict[str, Any], path: str, default: Any = None) -> Any:
    values = _path_values(document, _path_parts(path))
    present = [value for value in values if value is not MISSING]
    if not present:
        return default
    return present[0] if len(present) == 1 else present


def set_path(document: dict[str, Any], path: str, value: Any) -> None:
    parts = _path_parts(path)
    if not parts:
        return
    target = document
    for part in parts[:-1]:
        child = target.get(part)
        if not isinstance(child, dict):
            child = {}
            target[part] = child
        target = child
    target[parts[-1]] = _clone(value)


def unset_path(document: dict[str, Any], path: str) -> None:
    parts = _path_parts(path)
    if not parts:
        return
    target: Any = document
    for part in parts[:-1]:
        if not isinstance(target, dict) or part not in target:
            return
        target = target[part]
    if isinstance(target, dict):
        target.pop(parts[-1], None)


def _comparable(value: Any) -> tuple[int, Any]:
    if value is MISSING or value is None:
        return (0, "")
    if isinstance(value, bool):
        return (1, int(value))
    if isinstance(value, (int, float)):
        return (2, value)
    if isinstance(value, (date, datetime)):
        return (3, value.isoformat())
    return (4, str(value))


def _equals(actual: Any, expected: Any) -> bool:
    if actual is MISSING:
        return expected is None
    if isinstance(actual, list) and not isinstance(expected, list):
        return any(_equals(item, expected) for item in actual)
    return actual == expected


def _regex_matches(actual: Any, pattern: Any, options: str = "") -> bool:
    flags = re.IGNORECASE if "i" in str(options).lower() else 0
    compiled = pattern if hasattr(pattern, "search") else re.compile(str(pattern), flags)
    values = actual if isinstance(actual, list) else [actual]
    return any(
        value is not MISSING and compiled.search(str(value or "")) is not None
        for value in values
    )


def _matches_condition(values: list[Any], condition: Any) -> bool:
    if not isinstance(condition, dict) or not any(str(key).startswith("$") for key in condition):
        return any(_equals(value, condition) for value in values)

    options = str(condition.get("$options") or "")
    for operator, expected in condition.items():
        if operator == "$options":
            continue
        present = [value for value in values if value is not MISSING]
        if operator == "$exists":
            if bool(present) != bool(expected):
                return False
        elif operator == "$eq":
            if not any(_equals(value, expected) for value in values):
                return False
        elif operator == "$ne":
            if any(_equals(value, expected) for value in values):
                return False
        elif operator == "$in":
            candidates = list(expected or [])
            candidate_markers = {
                _hashable_unique_value(candidate) for candidate in candidates
            }

            def included(value: Any) -> bool:
                if isinstance(value, list):
                    return any(
                        _hashable_unique_value(item) in candidate_markers
                        for item in value
                    )
                return _hashable_unique_value(value) in candidate_markers

            if not any(included(value) for value in values):
                return False
        elif operator == "$nin":
            candidates = list(expected or [])
            if any(any(_equals(value, candidate) for candidate in candidates) for value in values):
                return False
        elif operator in {"$gt", "$gte", "$lt", "$lte"}:
            def compare(value: Any) -> bool:
                if value is MISSING or value is None:
                    return False
                try:
                    if operator == "$gt":
                        return value > expected
                    if operator == "$gte":
                        return value >= expected
                    if operator == "$lt":
                        return value < expected
                    return value <= expected
                except TypeError:
                    left, right = _comparable(value), _comparable(expected)
                    return {
                        "$gt": left > right,
                        "$gte": left >= right,
                        "$lt": left < right,
                        "$lte": left <= right,
                    }[operator]
            if not any(compare(value) for value in values):
                return False
        elif operator == "$regex":
            if not any(_regex_matches(value, expected, options) for value in values):
                return False
        elif operator == "$not":
            if _matches_condition(values, expected):
                return False
        elif operator == "$size":
            if not any(isinstance(value, list) and len(value) == int(expected) for value in values):
                return False
        elif operator == "$all":
            if not any(
                isinstance(value, list)
                and all(any(_equals(item, candidate) for item in value) for candidate in expected)
                for value in values
            ):
                return False
        elif operator == "$elemMatch":
            if not any(
                isinstance(value, list)
                and any(
                    matches_filter(item, expected) if isinstance(item, dict)
                    else _matches_condition([item], expected)
                    for item in value
                )
                for value in values
            ):
                return False
        elif operator == "$type":
            wanted = str(expected).lower()
            type_map = {
                "string": str, "number": (int, float), "double": float,
                "int": int, "long": int, "array": list, "object": dict,
                "bool": bool, "date": (date, datetime), "null": type(None),
            }
            python_type = type_map.get(wanted)
            if python_type is not None and not any(isinstance(value, python_type) for value in present):
                return False
        else:
            return False
    return True


def matches_filter(document: dict[str, Any], selector: dict[str, Any] | None) -> bool:
    selector = selector or {}
    for key, condition in selector.items():
        if key == "$or":
            if not any(matches_filter(document, branch) for branch in condition or []):
                return False
        elif key == "$and":
            if not all(matches_filter(document, branch) for branch in condition or []):
                return False
        elif key == "$nor":
            if any(matches_filter(document, branch) for branch in condition or []):
                return False
        elif key == "$expr":
            if not bool(evaluate_expression(condition, document)):
                return False
        elif key == "$text":
            needle = str((condition or {}).get("$search") or "").casefold()
            if needle and needle not in str(document).casefold():
                return False
        elif str(key).startswith("$"):
            return False
        else:
            if not _matches_condition(_path_values(document, _path_parts(key)), condition):
                return False
    return True


def _convert_value(value: Any, target: str, on_error: Any = None, on_null: Any = None) -> Any:
    if value is None or value is MISSING:
        return on_null
    try:
        target = target.lower()
        if target in {"double", "decimal"}:
            return float(value)
        if target in {"int", "long"}:
            return int(float(value))
        if target == "string":
            return str(value)
        if target == "bool":
            return bool(value)
        if target == "date":
            if isinstance(value, datetime):
                return value
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        return on_error
    return value


def evaluate_expression(expression: Any, document: dict[str, Any], variables: dict[str, Any] | None = None) -> Any:
    variables = variables or {}
    if isinstance(expression, str):
        if expression.startswith("$$"):
            name, _, tail = expression[2:].partition(".")
            value = variables.get(name)
            return get_path(value, tail) if tail and isinstance(value, dict) else value
        if expression.startswith("$"):
            return get_path(document, expression[1:])
        return expression
    if isinstance(expression, list):
        return [evaluate_expression(item, document, variables) for item in expression]
    if not isinstance(expression, dict):
        return expression
    if len(expression) != 1 or not next(iter(expression)).startswith("$"):
        return {key: evaluate_expression(value, document, variables) for key, value in expression.items()}

    operator, raw = next(iter(expression.items()))
    values = raw if isinstance(raw, list) else [raw]
    resolved = [evaluate_expression(value, document, variables) for value in values]
    if operator == "$ifNull":
        return resolved[0] if resolved and resolved[0] is not None else (resolved[1] if len(resolved) > 1 else None)
    if operator == "$cond":
        if isinstance(raw, dict):
            condition = evaluate_expression(raw.get("if"), document, variables)
            branch = raw.get("then") if condition else raw.get("else")
            return evaluate_expression(branch, document, variables)
        return resolved[1] if resolved[0] else resolved[2]
    if operator in {"$eq", "$ne", "$gt", "$gte", "$lt", "$lte"}:
        left, right = resolved[0], resolved[1]
        return {
            "$eq": left == right, "$ne": left != right, "$gt": left > right,
            "$gte": left >= right, "$lt": left < right, "$lte": left <= right,
        }[operator]
    if operator == "$and":
        return all(resolved)
    if operator == "$or":
        return any(resolved)
    if operator == "$not":
        return not bool(resolved[0])
    if operator == "$in":
        return resolved[0] in (resolved[1] or [])
    if operator == "$add":
        return sum((value or 0) for value in resolved)
    if operator == "$subtract":
        return (resolved[0] or 0) - (resolved[1] or 0)
    if operator == "$multiply":
        total = 1
        for value in resolved:
            total *= value or 0
        return total
    if operator == "$divide":
        return (resolved[0] or 0) / resolved[1] if resolved[1] else None
    if operator == "$abs":
        return abs(resolved[0] or 0)
    if operator == "$round":
        return round(resolved[0] or 0, int(resolved[1] if len(resolved) > 1 else 0))
    if operator in {"$toDouble", "$toInt", "$toString"}:
        target = {"$toDouble": "double", "$toInt": "int", "$toString": "string"}[operator]
        return _convert_value(resolved[0], target)
    if operator == "$convert":
        return _convert_value(
            evaluate_expression(raw.get("input"), document, variables),
            str(raw.get("to") or "string"),
            evaluate_expression(raw.get("onError"), document, variables),
            evaluate_expression(raw.get("onNull"), document, variables),
        )
    if operator in {"$toLower", "$toUpper"}:
        text = str(resolved[0] or "")
        return text.lower() if operator == "$toLower" else text.upper()
    if operator == "$concat":
        return "".join(str(value or "") for value in resolved)
    if operator in {"$substr", "$substrCP"}:
        text, start, length = str(resolved[0] or ""), int(resolved[1]), int(resolved[2])
        return text[start:start + length]
    if operator == "$size":
        return len(resolved[0] or [])
    if operator == "$arrayElemAt":
        array, index = resolved[0] or [], int(resolved[1])
        try:
            return array[index]
        except (IndexError, TypeError):
            return None
    if operator in {"$year", "$month", "$dayOfMonth"}:
        value = resolved[0]
        if not isinstance(value, (date, datetime)):
            try:
                value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                return None
        return {"$year": value.year, "$month": value.month, "$dayOfMonth": value.day}[operator]
    if operator == "$filter":
        source = evaluate_expression(raw.get("input"), document, variables) or []
        alias = str(raw.get("as") or "this")
        return [
            item for item in source
            if evaluate_expression(raw.get("cond"), document, {**variables, alias: item})
        ]
    if operator == "$map":
        source = evaluate_expression(raw.get("input"), document, variables) or []
        alias = str(raw.get("as") or "this")
        return [
            evaluate_expression(raw.get("in"), document, {**variables, alias: item})
            for item in source
        ]
    return None


def apply_projection(document: dict[str, Any], projection: dict[str, Any] | None) -> dict[str, Any]:
    if not projection:
        return _clone(document)
    includes = [key for key, value in projection.items() if value not in (0, False) and key != "_id"]
    computed = any(isinstance(value, (dict, str)) and value not in (0, 1) for value in projection.values())
    if includes or computed:
        result: dict[str, Any] = {}
        for key, rule in projection.items():
            if rule in (0, False):
                continue
            if rule in (1, True):
                parts = _path_parts(key)
                top_level = document.get(parts[0], MISSING) if parts else MISSING
                if len(parts) > 1 and isinstance(top_level, list):
                    projected_items = result.setdefault(parts[0], [])
                    while len(projected_items) < len(top_level):
                        projected_items.append({})
                    for index, item in enumerate(top_level):
                        if not isinstance(item, dict):
                            continue
                        value = get_path(item, ".".join(parts[1:]), MISSING)
                        if value is not MISSING:
                            set_path(projected_items[index], ".".join(parts[1:]), value)
                    continue
                value = get_path(document, key, MISSING)
            else:
                value = evaluate_expression(rule, document)
            if value is not MISSING:
                set_path(result, key, value)
        if projection.get("_id", 1) not in (0, False) and "_id" in document:
            result.setdefault("_id", _clone(document["_id"]))
        return result
    result = _clone(document)
    for key, rule in projection.items():
        if rule in (0, False):
            unset_path(result, key)
    return result


def _seed_from_selector(selector: dict[str, Any]) -> dict[str, Any]:
    seed: dict[str, Any] = {}
    for key, value in (selector or {}).items():
        if str(key).startswith("$") or isinstance(value, dict) and any(str(item).startswith("$") for item in value):
            continue
        set_path(seed, key, value)
    return seed


def apply_update(document: dict[str, Any], update: dict[str, Any], *, inserting: bool = False) -> dict[str, Any]:
    if not any(str(key).startswith("$") for key in update):
        replacement = _clone(update)
        replacement.setdefault("_id", document.get("_id", _new_id()))
        return replacement
    result = _clone(document)
    for operator, fields in update.items():
        if operator == "$set" or operator == "$setOnInsert" and inserting:
            for path, value in fields.items():
                set_path(result, path, value)
        elif operator == "$unset":
            for path in fields:
                unset_path(result, path)
        elif operator == "$inc":
            for path, value in fields.items():
                set_path(result, path, (get_path(result, path, 0) or 0) + value)
        elif operator in {"$min", "$max"}:
            for path, value in fields.items():
                current = get_path(result, path, MISSING)
                if current is MISSING or (operator == "$min" and value < current) or (operator == "$max" and value > current):
                    set_path(result, path, value)
        elif operator == "$rename":
            for old, new in fields.items():
                value = get_path(result, old, MISSING)
                if value is not MISSING:
                    unset_path(result, old)
                    set_path(result, new, value)
        elif operator in {"$push", "$addToSet"}:
            for path, value in fields.items():
                current = list(get_path(result, path, []) or [])
                additions = list(value.get("$each") or []) if isinstance(value, dict) and "$each" in value else [value]
                for item in additions:
                    if operator == "$push" or item not in current:
                        current.append(_clone(item))
                set_path(result, path, current)
        elif operator == "$pull":
            for path, condition in fields.items():
                current = list(get_path(result, path, []) or [])
                kept = []
                for item in current:
                    matched = matches_filter(item, condition) if isinstance(item, dict) and isinstance(condition, dict) else _matches_condition([item], condition)
                    if not matched:
                        kept.append(item)
                set_path(result, path, kept)
        elif operator == "$currentDate":
            for path in fields:
                set_path(result, path, datetime.now(timezone.utc))
    result.setdefault("_id", document.get("_id", _new_id()))
    return result


class SheetCursor:
    def __init__(self, documents: Iterable[dict[str, Any]]):
        self._documents = [_clone(document) for document in documents]
        self._skip = 0
        self._limit: int | None = None

    def sort(self, key_or_list: Any, direction: int | None = None) -> "SheetCursor":
        fields = key_or_list if isinstance(key_or_list, list) else [(key_or_list, direction or 1)]

        def compare(left: dict[str, Any], right: dict[str, Any]) -> int:
            for path, order in fields:
                a, b = _comparable(get_path(left, path)), _comparable(get_path(right, path))
                if a == b:
                    continue
                result = -1 if a < b else 1
                return result if int(order or 1) >= 0 else -result
            return 0

        self._documents.sort(key=cmp_to_key(compare))
        return self

    def skip(self, count: int) -> "SheetCursor":
        self._skip = max(0, int(count))
        return self

    def limit(self, count: int) -> "SheetCursor":
        self._limit = max(0, int(count))
        return self

    def _page(self) -> list[dict[str, Any]]:
        documents = self._documents[self._skip:]
        if self._limit is not None:
            documents = documents[:self._limit]
        return [_clone(document) for document in documents]

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        documents = self._page()
        return documents if length is None else documents[:max(0, int(length))]

    def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        self._iterator = iter(self._page())
        return self

    async def __anext__(self) -> dict[str, Any]:
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


MutationHook = Callable[[str, str, list[dict[str, Any]], list[dict[str, Any]]], Awaitable[None]]


class SheetTable:
    def __init__(self, database: "SheetDatabase", name: str):
        self.database = database
        self.name = name
        self._documents: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._indexes: dict[str, dict[str, Any]] = {"_id_": {"key": [("_id", 1)], "unique": True}}

    async def _notify(self, method: str, before: list[dict[str, Any]], after: list[dict[str, Any]]) -> None:
        if self.database.mutation_hook is not None and not self.database.loading:
            await self.database.mutation_hook(self.name, method, _clone(before), _clone(after))

    def _check_unique(self, candidate: dict[str, Any], ignore_id: Any = MISSING) -> None:
        for metadata in self._indexes.values():
            if not metadata.get("unique"):
                continue
            fields = [item[0] if isinstance(item, (tuple, list)) else item for item in metadata.get("key", [])]
            if not fields:
                continue
            partial = metadata.get("partialFilterExpression")
            if partial and not matches_filter(candidate, partial):
                continue
            values = tuple(get_path(candidate, field, MISSING) for field in fields)
            if metadata.get("sparse") and any(value is MISSING or value is None for value in values):
                continue
            for document in self._documents:
                if ignore_id is not MISSING and document.get("_id") == ignore_id:
                    continue
                if partial and not matches_filter(document, partial):
                    continue
                if tuple(get_path(document, field, MISSING) for field in fields) == values:
                    raise DuplicateRecordError(f"Valore duplicato nel foglio {self.name}: {fields}")

    def find(self, selector: dict[str, Any] | None = None, projection: dict[str, Any] | None = None, *args, **kwargs) -> SheetCursor:
        documents = [apply_projection(document, projection) for document in self._documents if matches_filter(document, selector)]
        return SheetCursor(documents)

    async def find_one(self, selector: dict[str, Any] | None = None, projection: dict[str, Any] | None = None, *args, **kwargs) -> dict[str, Any] | None:
        cursor = self.find(selector, projection)
        if kwargs.get("sort"):
            cursor.sort(kwargs["sort"])
        documents = await cursor.limit(1).to_list(1)
        return documents[0] if documents else None

    async def count_documents(self, selector: dict[str, Any] | None = None, *args, **kwargs) -> int:
        return sum(1 for document in self._documents if matches_filter(document, selector))

    async def estimated_document_count(self, *args, **kwargs) -> int:
        return len(self._documents)

    async def hydrate_documents(
        self,
        documents: Iterable[dict[str, Any]],
        *,
        copy_documents: bool = True,
        append: bool = False,
    ) -> int:
        """Carica in blocco una tabella vuota durante l'avvio da Sheets.

        L'idratazione parte sempre da una cache effimera vuota. Usare gli
        upsert ordinari per ogni riga farebbe scandire ripetutamente la lista
        gia' caricata, con costo quadratico sui registri piu' grandi (per
        esempio le transazioni POS). Questo percorso e' deliberatamente
        disponibile soltanto mentre ``database.loading`` e non genera alcuna
        scrittura remota.
        """
        if not self.database.loading:
            raise RuntimeError("hydrate_documents consentito solo durante l'idratazione")
        async with self._lock:
            if self._documents and not append:
                raise RuntimeError("hydrate_documents richiede una tabella vuota")
            stored_documents: list[dict[str, Any]] = []
            seen_ids: set[str] = {
                str(document.get("_id")) for document in self._documents
            }
            for document in documents:
                # Durante restore_all il payload e' appena decodificato da
                # Sheets e viene ceduto alla cache: copiarlo nuovamente
                # raddoppiava il picco di memoria dei registri POS. Il default
                # resta difensivo per gli altri chiamanti.
                stored = _clone(document) if copy_documents else document
                stored.setdefault("_id", _new_id())
                record_id = str(stored["_id"])
                if record_id in seen_ids:
                    raise DuplicateRecordError(
                        f"Valore _id duplicato nel foglio {self.name}: {record_id}"
                    )
                seen_ids.add(record_id)
                stored_documents.append(stored)
            if append:
                self._documents.extend(stored_documents)
            else:
                self._documents = stored_documents
            return len(stored_documents)

    async def distinct(self, key: str, selector: dict[str, Any] | None = None, *args, **kwargs) -> list[Any]:
        values: list[Any] = []
        for document in self._documents:
            if not matches_filter(document, selector):
                continue
            for value in _path_values(document, _path_parts(key)):
                candidates = value if isinstance(value, list) else [value]
                for candidate in candidates:
                    if candidate is not MISSING and candidate not in values:
                        values.append(_clone(candidate))
        return values

    async def insert_one(self, document: dict[str, Any], *args, **kwargs) -> InsertOneResult:
        async with self._lock:
            stored = _clone(document)
            stored.setdefault("_id", _new_id())
            self._check_unique(stored)
            self._documents.append(stored)
            document.setdefault("_id", stored["_id"])
            await self._notify("insert_one", [], [stored])
            return InsertOneResult(stored["_id"])

    async def insert_many(self, documents: Iterable[dict[str, Any]], *args, **kwargs) -> InsertManyResult:
        async with self._lock:
            documents = list(documents)
            stored_documents = []
            for document in documents:
                stored = _clone(document)
                stored.setdefault("_id", _new_id())
                stored_documents.append(stored)

            # Convalida ogni indice univoco in O(righe esistenti + batch),
            # anziche' scandire tutte le righe per ogni nuovo documento. Il
            # percorso precedente diventava quadratico durante gli import POS
            # e bloccava l'health check di Render prima del completamento.
            for metadata in self._indexes.values():
                if not metadata.get("unique"):
                    continue
                fields = [
                    item[0] if isinstance(item, (tuple, list)) else item
                    for item in metadata.get("key", [])
                ]
                if not fields:
                    continue
                partial = metadata.get("partialFilterExpression")
                sparse = bool(metadata.get("sparse"))
                seen: set[Any] = set()
                for existing in self._documents:
                    if partial and not matches_filter(existing, partial):
                        continue
                    values = tuple(get_path(existing, field, MISSING) for field in fields)
                    if sparse and any(value is MISSING or value is None for value in values):
                        continue
                    seen.add(tuple(_hashable_unique_value(value) for value in values))
                for stored in stored_documents:
                    if partial and not matches_filter(stored, partial):
                        continue
                    values = tuple(get_path(stored, field, MISSING) for field in fields)
                    if sparse and any(value is MISSING or value is None for value in values):
                        continue
                    marker = tuple(_hashable_unique_value(value) for value in values)
                    if marker in seen:
                        raise DuplicateRecordError(
                            f"Valore duplicato nel foglio {self.name}: {fields}"
                        )
                    seen.add(marker)
            for original, stored in zip(documents, stored_documents):
                original.setdefault("_id", stored["_id"])
            self._documents.extend(stored_documents)
            await self._notify("insert_many", [], stored_documents)
            return InsertManyResult([document["_id"] for document in stored_documents])

    async def _update(self, selector: dict[str, Any], update: dict[str, Any], *, many: bool, upsert: bool) -> tuple[UpdateResult, list[dict[str, Any]], list[dict[str, Any]]]:
        indexes = [index for index, document in enumerate(self._documents) if matches_filter(document, selector)]
        if not many:
            indexes = indexes[:1]
        before: list[dict[str, Any]] = []
        after: list[dict[str, Any]] = []
        modified = 0
        upserted_id = None
        for index in indexes:
            old = _clone(self._documents[index])
            new = apply_update(old, update)
            self._check_unique(new, ignore_id=old.get("_id"))
            before.append(old)
            after.append(new)
            if new != old:
                modified += 1
            self._documents[index] = new
        if not indexes and upsert:
            seed = _seed_from_selector(selector)
            new = apply_update(seed, update, inserting=True)
            new.setdefault("_id", _new_id())
            self._check_unique(new)
            self._documents.append(new)
            after.append(new)
            upserted_id = new["_id"]
        return UpdateResult(len(indexes), modified, upserted_id), before, after

    async def update_one(self, selector: dict[str, Any], update: dict[str, Any], *args, upsert: bool = False, **kwargs) -> UpdateResult:
        async with self._lock:
            result, before, after = await self._update(selector, update, many=False, upsert=upsert)
            await self._notify("update_one", before, after)
            return result

    async def update_many(self, selector: dict[str, Any], update: dict[str, Any], *args, upsert: bool = False, **kwargs) -> UpdateResult:
        async with self._lock:
            result, before, after = await self._update(selector, update, many=True, upsert=upsert)
            await self._notify("update_many", before, after)
            return result

    async def replace_one(self, selector: dict[str, Any], replacement: dict[str, Any], *args, upsert: bool = False, **kwargs) -> UpdateResult:
        return await self.update_one(selector, _clone(replacement), upsert=upsert, **kwargs)

    async def _delete(self, selector: dict[str, Any], *, many: bool) -> tuple[DeleteResult, list[dict[str, Any]]]:
        indexes = [index for index, document in enumerate(self._documents) if matches_filter(document, selector)]
        if not many:
            indexes = indexes[:1]
        before = [_clone(self._documents[index]) for index in indexes]
        for index in reversed(indexes):
            del self._documents[index]
        return DeleteResult(len(indexes)), before

    async def delete_one(self, selector: dict[str, Any], *args, **kwargs) -> DeleteResult:
        async with self._lock:
            result, before = await self._delete(selector, many=False)
            await self._notify("delete_one", before, [])
            return result

    async def delete_many(self, selector: dict[str, Any], *args, **kwargs) -> DeleteResult:
        async with self._lock:
            result, before = await self._delete(selector, many=True)
            await self._notify("delete_many", before, [])
            return result

    @staticmethod
    def _return_after(value: Any) -> bool:
        if value is None:
            return False
        name = str(getattr(value, "name", "")).upper()
        return name == "AFTER" or value is True or value == 1

    async def find_one_and_update(self, selector: dict[str, Any], update: dict[str, Any], *args, upsert: bool = False, return_document: Any = ReturnRecord.BEFORE, projection: dict[str, Any] | None = None, **kwargs) -> dict[str, Any] | None:
        async with self._lock:
            result, before, after = await self._update(selector, update, many=False, upsert=upsert)
            await self._notify("find_one_and_update", before, after)
            chosen = after[0] if self._return_after(return_document) and after else (before[0] if before else None)
            return apply_projection(chosen, projection) if chosen is not None else None

    async def find_one_and_replace(self, selector: dict[str, Any], replacement: dict[str, Any], *args, **kwargs) -> dict[str, Any] | None:
        return await self.find_one_and_update(selector, replacement, *args, **kwargs)

    async def find_one_and_delete(self, selector: dict[str, Any], *args, projection: dict[str, Any] | None = None, **kwargs) -> dict[str, Any] | None:
        async with self._lock:
            _, before = await self._delete(selector, many=False)
            await self._notify("find_one_and_delete", before, [])
            return apply_projection(before[0], projection) if before else None

    async def bulk_write(self, operations: Iterable[Any], *args, **kwargs) -> BulkWriteResult:
        result = BulkWriteResult()
        for operation in operations:
            selector = getattr(operation, "selector", getattr(operation, "_filter", {}))
            update = getattr(operation, "update", getattr(operation, "_doc", {}))
            upsert = bool(getattr(operation, "upsert", getattr(operation, "_upsert", False)))
            item = await self.update_one(selector, update, upsert=upsert)
            result.matched_count += item.matched_count
            result.modified_count += item.modified_count
            result.upserted_count += int(item.upserted_id is not None)
        return result

    async def create_index(self, keys: Any, *args, **kwargs) -> str:
        normalized = [(keys, 1)] if isinstance(keys, str) else list(keys)
        name = kwargs.get("name") or "_".join(f"{key}_{direction}" for key, direction in normalized)
        metadata = {"key": normalized, **kwargs}
        if metadata.get("unique"):
            for index, document in enumerate(self._documents):
                self._check_unique(document, ignore_id=document.get("_id"))
        self._indexes[name] = metadata
        return name

    async def index_information(self, *args, **kwargs) -> dict[str, dict[str, Any]]:
        return _clone(self._indexes)

    async def drop_index(self, name: str, *args, **kwargs) -> None:
        self._indexes.pop(name, None)

    def aggregate(self, pipeline: list[dict[str, Any]], *args, **kwargs) -> SheetCursor:
        documents = [_clone(document) for document in self._documents]
        for stage in pipeline:
            operator, value = next(iter(stage.items()))
            if operator == "$match":
                documents = [document for document in documents if matches_filter(document, value)]
            elif operator == "$sort":
                documents = SheetCursor(documents).sort(list(value.items()))._page()
            elif operator == "$skip":
                documents = documents[int(value):]
            elif operator == "$limit":
                documents = documents[:int(value)]
            elif operator == "$project":
                documents = [apply_projection(document, value) for document in documents]
            elif operator in {"$addFields", "$set"}:
                updated = []
                for document in documents:
                    result = _clone(document)
                    for path, expression in value.items():
                        set_path(result, path, evaluate_expression(expression, document))
                    updated.append(result)
                documents = updated
            elif operator == "$unset":
                fields = [value] if isinstance(value, str) else list(value)
                for document in documents:
                    for path in fields:
                        unset_path(document, path)
            elif operator == "$unwind":
                config = {"path": value} if isinstance(value, str) else value
                path = str(config.get("path") or "").lstrip("$")
                preserve = bool(config.get("preserveNullAndEmptyArrays"))
                unwound = []
                for document in documents:
                    items = get_path(document, path, MISSING)
                    if isinstance(items, list) and items:
                        for item in items:
                            expanded = _clone(document)
                            set_path(expanded, path, item)
                            unwound.append(expanded)
                    elif preserve:
                        unwound.append(document)
                documents = unwound
            elif operator == "$group":
                grouped: dict[str, tuple[Any, list[dict[str, Any]]]] = {}
                for document in documents:
                    group_id = evaluate_expression(value.get("_id"), document)
                    marker = repr(group_id)
                    grouped.setdefault(marker, (_clone(group_id), []))[1].append(document)
                results = []
                for group_id, members in grouped.values():
                    result: dict[str, Any] = {"_id": group_id}
                    for field, accumulator in value.items():
                        if field == "_id":
                            continue
                        acc_operator, expression = next(iter(accumulator.items()))
                        values = [evaluate_expression(expression, member) for member in members]
                        if acc_operator == "$sum":
                            result[field] = sum((item or 0) for item in values)
                        elif acc_operator == "$avg":
                            numeric = [item for item in values if isinstance(item, (int, float))]
                            result[field] = sum(numeric) / len(numeric) if numeric else None
                        elif acc_operator == "$min":
                            present = [item for item in values if item is not None]
                            result[field] = min(present) if present else None
                        elif acc_operator == "$max":
                            present = [item for item in values if item is not None]
                            result[field] = max(present) if present else None
                        elif acc_operator == "$first":
                            result[field] = values[0] if values else None
                        elif acc_operator == "$last":
                            result[field] = values[-1] if values else None
                        elif acc_operator == "$push":
                            result[field] = values
                        elif acc_operator == "$addToSet":
                            result[field] = []
                            for item in values:
                                if item not in result[field]:
                                    result[field].append(item)
                    results.append(result)
                documents = results
            elif operator == "$count":
                documents = [{str(value): len(documents)}] if documents else []
            elif operator == "$lookup":
                foreign = self.database[str(value.get("from"))]._documents
                local_field, foreign_field = value.get("localField"), value.get("foreignField")
                alias = str(value.get("as") or "matches")
                joined = []
                for document in documents:
                    local_value = get_path(document, local_field)
                    result = _clone(document)
                    result[alias] = [_clone(item) for item in foreign if _equals(get_path(item, foreign_field), local_value)]
                    joined.append(result)
                documents = joined
            elif operator == "$facet":
                facet_result = {}
                source = [_clone(document) for document in documents]
                for name, sub_pipeline in value.items():
                    temporary = SheetTable(self.database, f"{self.name}:{name}")
                    temporary._documents = _clone(source)
                    facet_result[name] = temporary.aggregate(sub_pipeline)._page()
                documents = [facet_result]
            elif operator in {"$replaceRoot", "$replaceWith"}:
                expression = value.get("newRoot") if operator == "$replaceRoot" else value
                documents = [evaluate_expression(expression, document) or {} for document in documents]
            else:
                raise NotImplementedError(f"Fase di aggregazione non supportata: {operator}")
        return SheetCursor(documents)


class SheetDatabase:
    def __init__(self, name: str = "Gestionale", mutation_hook: MutationHook | None = None):
        self.name = name
        self.mutation_hook = mutation_hook
        self.loading = False
        self._tables: dict[str, SheetTable] = {}
        self._transaction_lock = asyncio.Lock()

    def __getitem__(self, name: str) -> SheetTable:
        return self._tables.setdefault(name, SheetTable(self, name))

    def __getattr__(self, name: str) -> SheetTable:
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]

    async def list_collection_names(self, *args, **kwargs) -> list[str]:
        return list(self._tables)

    @asynccontextmanager
    async def transaction(self):
        async with self._transaction_lock:
            yield None

    def close(self) -> None:
        for table in self._tables.values():
            closer = getattr(table, "close", None)
            if callable(closer):
                closer()
        self._tables.clear()


class MemorySheetsClient:
    """Client effimero per test: stessa API del registro, nessuna I/O remota."""

    def __init__(self):
        self._databases: dict[str, SheetDatabase] = {}

    def __getitem__(self, name: str) -> SheetDatabase:
        return self._databases.setdefault(name, SheetDatabase(name))

    def __getattr__(self, name: str) -> SheetDatabase:
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]

    async def list_database_names(self) -> list[str]:
        return list(self._databases)

    async def drop_database(self, name: str) -> None:
        database = self._databases.pop(name, None)
        if database is not None:
            database.close()

    def close(self) -> None:
        for database in self._databases.values():
            database.close()
        self._databases.clear()
