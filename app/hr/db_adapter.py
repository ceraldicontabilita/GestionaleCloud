"""Adattatore tra il codice HR (scritto contro l'API di motor) e il runtime
documentale del gestionale.

Due compiti, entrambi trasparenti per i router:

1. **Spazio dei nomi** — ogni collezione HR diventa ``hr_<nome>`` nel
   runtime del gestionale, cosi' ``dipendenti``/``cedolini``/``users`` del
   modulo HR non si sovrappongono alle omonime collezioni contabili gia'
   presenti (la fusione delle due anagrafiche e' il passo successivo, non
   una collisione silenziosa).

2. **Scarico dei binari** — i campi in ``BLOB_FIELDS`` (PDF/DOCX in base64)
   non entrano mai nel documento in memoria: vengono salvati nel
   ``BlobStore`` (chiave = impronta del contenuto: un PDF identico citato da
   piu' documenti e' salvato una volta sola) e il documento conserva solo un
   marcatore ``_blobs = {campo: chiave}``. In lettura il contenuto viene
   riagganciato documento per documento, solo se la proiezione lo richiede.
   Le proiezioni ``{"pdf_data": 0}`` gia' presenti ovunque nel codice HR
   diventano quindi anche il modo per non leggere i blob.

Copre il sottoinsieme dell'API motor realmente usato dal modulo HR
(``find``, ``find_one``, ``insert_one/many``, ``update_one/many``,
``replace_one``, ``delete_one/many``, ``count_documents``, ``distinct``,
``aggregate``, ``create_index``). Il resto e' delegato al runtime cosi' com'e'.
"""
from __future__ import annotations

import uuid
from typing import Any, AsyncIterator, Dict, Iterable, List, Optional, Tuple

from app.services.blob_store import BlobStore, blob_key

PREFIX = "hr_"
BLOB_FIELDS: Tuple[str, ...] = ("pdf_data", "file_data", "pdf_firmato_dipendente", "pdf_definitivo")
MARKER = "_blobs"
_UPDATE_OPERATORS = ("$set", "$setOnInsert", "$unset", "$inc", "$push", "$addToSet", "$pull")


def _new_id() -> str:
    return uuid.uuid4().hex


def _projection_mode(projection: Optional[Dict[str, Any]]) -> Tuple[str, set]:
    """('all', set()) senza proiezione; ('include', campi) o ('exclude', campi)."""
    if not projection:
        return "all", set()
    includes = {k for k, v in projection.items() if v not in (0, False) and k != "_id"}
    if includes:
        return "include", includes
    return "exclude", {k for k, v in projection.items() if v in (0, False)}


def wanted_blob_fields(projection: Optional[Dict[str, Any]]) -> set:
    mode, fields = _projection_mode(projection)
    if mode == "all":
        return set(BLOB_FIELDS)
    if mode == "include":
        return fields & set(BLOB_FIELDS)
    return set(BLOB_FIELDS) - fields


def inner_projection(projection: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """La proiezione passata al runtime: i blob non esistono nel documento,
    ma il marcatore serve per riagganciarli quando sono richiesti."""
    if not projection:
        return None
    mode, _ = _projection_mode(projection)
    cleaned = {k: v for k, v in projection.items() if k not in BLOB_FIELDS}
    if mode == "include":
        if wanted_blob_fields(projection):
            cleaned[MARKER] = 1
        if not cleaned or set(cleaned) <= {"_id", MARKER}:
            # Proiezione di soli blob: il runtime deve comunque restituire
            # il marcatore (e l'_id se non escluso).
            cleaned.setdefault(MARKER, 1)
    return cleaned


def _blob_condition(field: str, value: Any) -> Dict[str, Any]:
    marker = f"{MARKER}.{field}"
    if value is None:
        return {marker: {"$exists": False}}
    if isinstance(value, dict):
        ops = set(value)
        if ops == {"$exists"}:
            return {marker: {"$exists": bool(value["$exists"])}}
        if ops == {"$ne"} and value["$ne"] is None:
            return {marker: {"$exists": True}}
        if ops == {"$eq"} and value["$eq"] is None:
            return {marker: {"$exists": False}}
    raise NotImplementedError(
        f"Filtro su campo binario '{field}' non supportato: {value!r}. "
        "Sono ammessi solo $exists, None, {$ne: None}."
    )


def rewrite_selector(selector: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Traduce le condizioni sui campi blob in condizioni sul marcatore."""
    if not selector:
        return selector
    out: Dict[str, Any] = {}
    for key, value in selector.items():
        if key in ("$or", "$and", "$nor") and isinstance(value, list):
            out[key] = [rewrite_selector(item) for item in value]
        elif key in BLOB_FIELDS:
            out.update(_blob_condition(key, value))
        else:
            out[key] = value
    return out


def strip_blobs(document: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Separa i campi binari dal documento. Ritorna (documento_pulito, blob)."""
    blobs: Dict[str, str] = {}
    cleaned: Dict[str, Any] = {}
    for key, value in document.items():
        if key in BLOB_FIELDS and value is not None:
            blobs[key] = value
        else:
            cleaned[key] = value
    return cleaned, blobs


class HRCursor:
    """Cursore che riaggancia i blob mentre i documenti vengono consumati."""

    def __init__(self, inner: Any, collection: "HRCollection", wanted: set):
        self._inner = inner
        self._collection = collection
        self._wanted = wanted

    def sort(self, *args, **kwargs) -> "HRCursor":
        self._inner = self._inner.sort(*args, **kwargs)
        return self

    def skip(self, count: int) -> "HRCursor":
        self._inner = self._inner.skip(count)
        return self

    def limit(self, count: int) -> "HRCursor":
        self._inner = self._inner.limit(count)
        return self

    async def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
        documents = await self._inner.to_list(length)
        return [await self._collection._attach(doc, self._wanted) for doc in documents]

    def __aiter__(self) -> AsyncIterator[Dict[str, Any]]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[Dict[str, Any]]:
        async for document in self._inner:
            yield await self._collection._attach(document, self._wanted)


class HRCollection:
    def __init__(self, inner: Any, name: str, blobs: BlobStore):
        self._inner = inner
        self.name = name
        self._blobs = blobs

    # ------------------------------------------------------------------ lettura
    async def _attach(self, document: Optional[Dict[str, Any]], wanted: set) -> Optional[Dict[str, Any]]:
        if document is None:
            return None
        markers = document.pop(MARKER, None)
        if isinstance(markers, dict):
            for field, key in markers.items():
                if field in wanted:
                    document[field] = await self._blobs.get(key)
        return document

    def find(self, selector: Optional[Dict[str, Any]] = None, projection: Optional[Dict[str, Any]] = None, *args, **kwargs) -> HRCursor:
        cursor = self._inner.find(rewrite_selector(selector), inner_projection(projection), *args, **kwargs)
        return HRCursor(cursor, self, wanted_blob_fields(projection))

    async def find_one(self, selector: Optional[Dict[str, Any]] = None, projection: Optional[Dict[str, Any]] = None, *args, **kwargs) -> Optional[Dict[str, Any]]:
        document = await self._inner.find_one(rewrite_selector(selector), inner_projection(projection), *args, **kwargs)
        return await self._attach(document, wanted_blob_fields(projection))

    async def count_documents(self, selector: Optional[Dict[str, Any]] = None, *args, **kwargs) -> int:
        return await self._inner.count_documents(rewrite_selector(selector), *args, **kwargs)

    async def estimated_document_count(self, *args, **kwargs) -> int:
        return await self._inner.estimated_document_count(*args, **kwargs)

    async def count_with_blobs(self) -> int:
        """Documenti che citano almeno un binario (le chiavi sono condivise,
        quindi non si contano i blob per collezione ma i documenti)."""
        return await self._inner.count_documents({MARKER: {"$exists": True}})

    async def distinct(self, key: str, selector: Optional[Dict[str, Any]] = None, *args, **kwargs) -> List[Any]:
        if key in BLOB_FIELDS:
            raise NotImplementedError(f"distinct su campo binario '{key}' non supportato")
        return await self._inner.distinct(key, rewrite_selector(selector), *args, **kwargs)

    def aggregate(self, pipeline: List[Dict[str, Any]], *args, **kwargs) -> Any:
        rewritten = []
        for stage in pipeline:
            if "$match" in stage:
                rewritten.append({"$match": rewrite_selector(stage["$match"])})
            else:
                rewritten.append(stage)
        return self._inner.aggregate(rewritten, *args, **kwargs)

    # ---------------------------------------------------------------- scrittura
    async def _store_new(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Prepara un documento nuovo: assegna _id, scarica i blob, mette il marcatore."""
        cleaned, blobs = strip_blobs(document)
        cleaned.setdefault("_id", cleaned.get("id") or _new_id())
        if blobs:
            markers = dict(cleaned.get(MARKER) or {})
            for field, data in blobs.items():
                key = blob_key(data)
                await self._blobs.put(key, data)
                markers[field] = key
            cleaned[MARKER] = markers
        return cleaned

    async def insert_one(self, document: Dict[str, Any], *args, **kwargs) -> Any:
        stored = await self._store_new(document)
        result = await self._inner.insert_one(stored, *args, **kwargs)
        document.setdefault("_id", stored["_id"])
        return result

    async def insert_many(self, documents: Iterable[Dict[str, Any]], *args, **kwargs) -> Any:
        stored = [await self._store_new(document) for document in documents]
        return await self._inner.insert_many(stored, *args, **kwargs)

    @staticmethod
    def _is_replacement(update: Dict[str, Any]) -> bool:
        return not any(key.startswith("$") for key in update)

    @staticmethod
    def _touches_blobs(update: Dict[str, Any]) -> bool:
        if HRCollection._is_replacement(update):
            return any(field in update for field in BLOB_FIELDS)
        for op in ("$set", "$setOnInsert", "$unset"):
            if any(field in (update.get(op) or {}) for field in BLOB_FIELDS):
                return True
        return False

    async def _ids_and_markers(self, selector: Optional[Dict[str, Any]], many: bool) -> List[Dict[str, Any]]:
        cursor = self._inner.find(rewrite_selector(selector), {"_id": 1, MARKER: 1})
        if not many:
            cursor = cursor.limit(1)
        return await cursor.to_list(None)

    async def _apply_blob_update(self, target: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
        """Applica a UN documento la parte blob dell'update e ritorna l'update
        equivalente senza campi binari (con il marcatore aggiornato)."""
        markers = dict(target.get(MARKER) or {})
        rewritten: Dict[str, Any] = {}
        for op, payload in update.items():
            if op in ("$set", "$setOnInsert") and isinstance(payload, dict):
                cleaned, blobs = strip_blobs(payload)
                for field, data in blobs.items():
                    key = blob_key(data)
                    old = markers.get(field)
                    if old == key:
                        continue  # stesso contenuto: nessun nuovo riferimento
                    await self._blobs.put(key, data)
                    markers[field] = key
                    if old:
                        await self._blobs.delete([old])
                # Un $set esplicito a None equivale a rimuovere il binario.
                for field in BLOB_FIELDS:
                    if field in payload and payload[field] is None:
                        cleaned.pop(field, None)
                        old = markers.pop(field, None)
                        if old:
                            await self._blobs.delete([old])
                if cleaned:
                    rewritten[op] = cleaned
            elif op == "$unset" and isinstance(payload, dict):
                cleaned = {k: v for k, v in payload.items() if k not in BLOB_FIELDS}
                stale = [markers.pop(f) for f in BLOB_FIELDS if f in payload and f in markers]
                if stale:
                    await self._blobs.delete(stale)
                if cleaned:
                    rewritten[op] = cleaned
            else:
                rewritten[op] = payload
        rewritten.setdefault("$set", {})[MARKER] = markers
        if not markers:
            rewritten["$set"].pop(MARKER, None)
            rewritten.setdefault("$unset", {})[MARKER] = ""
            if not rewritten["$set"]:
                rewritten.pop("$set")
        return rewritten

    async def _upsert_missing(self, selector: Dict[str, Any], update: Dict[str, Any]) -> Any:
        """Upsert senza documento corrispondente: costruisce il documento come
        Mongo (uguaglianze del filtro + $set + $setOnInsert) e lo inserisce."""
        document: Dict[str, Any] = {
            k: v for k, v in (selector or {}).items()
            if not k.startswith("$") and not (isinstance(v, dict) and any(str(x).startswith("$") for x in v))
        }
        if self._is_replacement(update):
            document.update(update)
        else:
            document.update(update.get("$setOnInsert") or {})
            document.update(update.get("$set") or {})
            for key, delta in (update.get("$inc") or {}).items():
                document[key] = document.get(key, 0) + delta
            for key, value in (update.get("$push") or {}).items():
                document.setdefault(key, []).append(value)
        stored = await self._store_new(document)
        result = await self._inner.insert_one(stored)
        return _UpsertResult(result.inserted_id)

    async def _update(self, selector: Optional[Dict[str, Any]], update: Dict[str, Any], *, many: bool, upsert: bool, **kwargs) -> Any:
        if not self._touches_blobs(update):
            method = self._inner.update_many if many else self._inner.update_one
            return await method(rewrite_selector(selector), update, upsert=upsert, **kwargs)

        targets = await self._ids_and_markers(selector, many)
        if not targets:
            if upsert:
                return await self._upsert_missing(selector or {}, update)
            return _UpsertResult(None, matched=0)

        if self._is_replacement(update):
            return await self._replace(targets[0], update)

        last = None
        for target in targets:
            rewritten = await self._apply_blob_update(target, update)
            last = await self._inner.update_one({"_id": target["_id"]}, rewritten)
        if many:
            return _UpsertResult(None, matched=len(targets), modified=len(targets))
        return last

    async def update_one(self, selector: Optional[Dict[str, Any]], update: Dict[str, Any], *args, upsert: bool = False, **kwargs) -> Any:
        return await self._update(selector, update, many=False, upsert=upsert, **kwargs)

    async def update_many(self, selector: Optional[Dict[str, Any]], update: Dict[str, Any], *args, upsert: bool = False, **kwargs) -> Any:
        return await self._update(selector, update, many=True, upsert=upsert, **kwargs)

    async def _replace(self, target: Dict[str, Any], replacement: Dict[str, Any]) -> Any:
        old_markers = dict(target.get(MARKER) or {})
        cleaned, blobs = strip_blobs(replacement)
        cleaned["_id"] = target["_id"]
        markers: Dict[str, str] = {}
        for field, data in blobs.items():
            key = blob_key(data)
            markers[field] = key
            if old_markers.get(field) != key:
                await self._blobs.put(key, data)
        stale = [key for field, key in old_markers.items() if markers.get(field) != key]
        if stale:
            await self._blobs.delete(stale)
        if markers:
            cleaned[MARKER] = markers
        return await self._inner.replace_one({"_id": target["_id"]}, cleaned)

    async def replace_one(self, selector: Optional[Dict[str, Any]], replacement: Dict[str, Any], *args, upsert: bool = False, **kwargs) -> Any:
        targets = await self._ids_and_markers(selector, many=False)
        if not targets:
            if upsert:
                return await self._upsert_missing(selector or {}, replacement)
            return _UpsertResult(None, matched=0)
        return await self._replace(targets[0], replacement)

    async def _delete(self, selector: Optional[Dict[str, Any]], *, many: bool) -> Any:
        targets = await self._ids_and_markers(selector, many)
        keys = [key for target in targets for key in (target.get(MARKER) or {}).values()]
        if not targets:
            return _UpsertResult(None, deleted=0)
        ids = [target["_id"] for target in targets]
        result = await self._inner.delete_many({"_id": {"$in": ids}})
        if keys:
            await self._blobs.delete(keys)
        return result

    async def delete_one(self, selector: Optional[Dict[str, Any]] = None, *args, **kwargs) -> Any:
        return await self._delete(selector, many=False)

    async def delete_many(self, selector: Optional[Dict[str, Any]] = None, *args, **kwargs) -> Any:
        return await self._delete(selector, many=True)

    # ------------------------------------------------------------------- resto
    async def create_index(self, *args, **kwargs) -> Any:
        return await self._inner.create_index(*args, **kwargs)

    def __getattr__(self, item: str) -> Any:
        # Metodi non intercettati (index_information, drop_index, ...):
        # delega diretta al runtime. I metodi che toccano dati passano tutti
        # dalle implementazioni esplicite qui sopra.
        return getattr(self._inner, item)


class _UpsertResult:
    """Risultato minimo compatibile con UpdateResult/DeleteResult di motor."""

    def __init__(self, upserted_id: Any, matched: int = 0, modified: int = 0, deleted: int = 0):
        self.upserted_id = upserted_id
        self.matched_count = matched
        self.modified_count = modified
        self.deleted_count = deleted
        self.acknowledged = True


class HRDatabase:
    """Vista ``hr_*`` sul runtime documentale del gestionale."""

    def __init__(self, inner: Any, blobs: BlobStore):
        self._inner = inner
        self._blobs = blobs
        self.blobs = blobs

    def __getitem__(self, name: str) -> HRCollection:
        return HRCollection(self._inner[PREFIX + name], name, self._blobs)

    def __getattr__(self, name: str) -> HRCollection:
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]

    async def list_collection_names(self, *args, **kwargs) -> List[str]:
        names = await self._inner.list_collection_names(*args, **kwargs)
        return sorted(n[len(PREFIX):] for n in names if n.startswith(PREFIX))
