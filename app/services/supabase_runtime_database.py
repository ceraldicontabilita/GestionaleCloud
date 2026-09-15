"""Runtime documentale Supabase del gestionale.

Mantiene l'interfaccia compatibile con il precedente registro Sheets, ma usa
la tabella privata ``gestionale.documents`` come fonte autorevole. Il
server non usa la password Postgres né la service-role: chiama esclusivamente
quattro RPC minimali protette da una chiave applicativa separata, conservata
nel secret store di Render.

Il catalogo viene verificato all'avvio, mentre ogni lettura ricarica da
Supabase la sola collezione richiesta. Le mutazioni sono confermate dal
database prima di diventare osservabili da altre letture del processo. Gli
upsert sono idempotenti sulla coppia ``(collection, id)``.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

import aiohttp

from app.services.sheets_document_store import SheetCursor, SheetDatabase, SheetTable

logger = logging.getLogger(__name__)

_PAGE_SIZE = 500
_MIN_READ_PAGE_SIZE = 10
_READ_RETRIES = 5
_MANIFEST_RETRIES = 3
_WRITE_CHUNK_SIZE = 200
_KEYSET_COLLECTIONS = {"documents_inbox"}

# Le RPC runtime hanno un timeout molto stretto e la paginazione OFFSET diventa
# costosa oltre alcune migliaia di righe. Le collezioni elencate qui possono
# essere suddivise fisicamente senza cambiare il nome logico visto dall'app.
# Il mapping e' esplicito: nessun nome ricevuto dai dati decide dove scrivere.
_COLLECTION_SHARDS: dict[str, tuple[str, ...]] = {
    "documents_inbox": ("documents_inbox__shard_001",),
}
_SHARD_TO_COLLECTION = {
    shard: collection
    for collection, shards in _COLLECTION_SHARDS.items()
    for shard in shards
}



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


class DocumentoDuplicatoRemoto(RuntimeError):
    """Postgres ha rifiutato uno o piu' documenti per ``idempotency_key`` gia' usata.

    Viene sollevata prima che la mutazione possa essere considerata conclusa.
    Espone, per chiave, l'id e il documento gia' presenti in Supabase
    (``id_esistente_per_chiave``, ``documento_esistente_per_chiave``).
    """

    def __init__(self, collection_name: str, rifiuti: list[dict[str, Any]]):
        self.collection_name = collection_name
        self.rifiuti = rifiuti
        self.id_esistente_per_chiave = {
            str(item.get("idempotency_key")): item.get("id_esistente")
            for item in rifiuti
        }
        self.documento_esistente_per_chiave = {
            str(item.get("idempotency_key")): item.get("documento_esistente") or {}
            for item in rifiuti
        }
        dettaglio = ", ".join(
            f"{item.get('idempotency_key')} -> {item.get('id_esistente')}"
            for item in rifiuti
        )
        super().__init__(
            f"Supabase ha rifiutato {len(rifiuti)} documenti in "
            f"{collection_name} per idempotency_key gia' usata: {dettaglio}"
        )


def _rifiuti_da_risposta(result: Any) -> list[dict[str, Any]]:
    """Estrae l'elenco dei rifiuti dalla risposta di ``gc_upsert_documents``.

    La versione storica dell'RPC restituisce un intero (righe scritte) o
    nulla; quella con la regola di unicita' restituisce
    ``{"upserted": n, "rejected": [{id_rifiutato, id_esistente,
    idempotency_key, documento_esistente}]}``.
    """
    if not isinstance(result, dict):
        return []
    rejected = result.get("rejected")
    if not isinstance(rejected, list):
        return []
    return [item for item in rejected if isinstance(item, dict) and item.get("id_rifiutato")]


def _errore_lettura_transitorio(exc: RuntimeError) -> bool:
    message = str(exc).lower()
    return "statement timeout" in message or any(
        f"http {status}" in message for status in (502, 503, 504, 520)
    )


class SupabaseRPCError(RuntimeError):
    """Errore remoto con codice strutturato, senza esporre il payload."""

    def __init__(self, function_name: str, status: int, code: str, detail: str):
        self.status = status
        self.code = code
        super().__init__(
            f"Supabase RPC {function_name} fallita (HTTP {status}): {detail}"
        )


class _ReadThroughCursor:
    """Cursor Motor-compatibile che costruisce lo snapshot da Supabase al consumo."""

    def __init__(self, loader):
        self._loader = loader
        self._sort = None
        self._skip = 0
        self._limit: int | None = None
        self._iterator = None

    def sort(self, key_or_list: Any, direction: int | None = None):
        self._sort = (key_or_list, direction)
        return self

    def skip(self, count: int):
        self._skip = max(0, int(count))
        return self

    def limit(self, count: int):
        self._limit = max(0, int(count))
        return self

    async def _cursor(self) -> SheetCursor:
        cursor = await self._loader()
        if self._sort is not None:
            cursor.sort(*self._sort)
        if self._skip:
            cursor.skip(self._skip)
        if self._limit is not None:
            cursor.limit(self._limit)
        return cursor

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        return await (await self._cursor()).to_list(length)

    def __aiter__(self):
        self._iterator = None
        return self

    async def __anext__(self):
        if self._iterator is None:
            self._iterator = iter(await self.to_list(None))
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class SupabaseTable(SheetTable):
    """Vista senza cache autorevole: rilegge Supabase per ogni operazione."""

    def __init__(self, database: "SupabaseRuntimeDatabase", name: str):
        super().__init__(database, name)
        self._remote_operation_lock = asyncio.Lock()

    async def _refresh_unlocked(self) -> None:
        documents = await self.database._fetch_logical_collection_documents(self.name)
        self._documents = [_normalise_document(document) for document in documents]

    def find(self, selector=None, projection=None, *args, **kwargs):
        async def load():
            async with self._remote_operation_lock:
                await self._refresh_unlocked()
                return SheetTable.find(self, selector, projection, *args, **kwargs)

        return _ReadThroughCursor(load)

    async def find_one(self, selector=None, projection=None, *args, **kwargs):
        cursor = self.find(selector, projection, *args, **kwargs)
        if kwargs.get("sort"):
            cursor.sort(kwargs["sort"])
        documents = await cursor.limit(1).to_list(1)
        return documents[0] if documents else None

    async def count_documents(self, selector=None, *args, **kwargs) -> int:
        return len(await self.find(selector).to_list(None))

    async def estimated_document_count(self, *args, **kwargs) -> int:
        return len(await self.find({}).to_list(None))

    async def distinct(self, key, selector=None, *args, **kwargs):
        async with self._remote_operation_lock:
            await self._refresh_unlocked()
            return await SheetTable.distinct(self, key, selector, *args, **kwargs)

    def aggregate(self, pipeline, *args, **kwargs):
        async def load():
            # $lookup usa gli snapshot delle collezioni esterne: rileggerli
            # prima di calcolare evita join contro dati di un vecchio processo.
            for stage in pipeline:
                lookup = stage.get("$lookup") if isinstance(stage, dict) else None
                if isinstance(lookup, dict) and lookup.get("from"):
                    foreign = self.database[str(lookup["from"])]
                    async with foreign._remote_operation_lock:
                        await foreign._refresh_unlocked()
            async with self._remote_operation_lock:
                await self._refresh_unlocked()
                return SheetTable.aggregate(self, pipeline, *args, **kwargs)

        return _ReadThroughCursor(load)

    async def _mutate(self, method_name: str, *args, **kwargs):
        async with self._remote_operation_lock:
            await self._refresh_unlocked()
            snapshot = [_normalise_document(document) for document in self._documents]
            try:
                method = getattr(SheetTable, method_name)
                return await method(self, *args, **kwargs)
            except Exception:
                # L'RPC e' l'autorita': una scrittura rifiutata non deve mai
                # lasciare visibile nel processo il documento candidato.
                self._documents = snapshot
                raise

    async def insert_one(self, document, *args, **kwargs):
        return await self._mutate("insert_one", document, *args, **kwargs)

    async def insert_many(self, documents, *args, **kwargs):
        return await self._mutate("insert_many", documents, *args, **kwargs)

    async def update_one(self, selector, update, *args, **kwargs):
        return await self._mutate("update_one", selector, update, *args, **kwargs)

    async def update_many(self, selector, update, *args, **kwargs):
        return await self._mutate("update_many", selector, update, *args, **kwargs)

    async def replace_one(self, selector, replacement, *args, **kwargs):
        return await self._mutate("update_one", selector, replacement, *args, **kwargs)

    async def delete_one(self, selector, *args, **kwargs):
        return await self._mutate("delete_one", selector, *args, **kwargs)

    async def delete_many(self, selector, *args, **kwargs):
        return await self._mutate("delete_many", selector, *args, **kwargs)

    async def find_one_and_update(self, selector, update, *args, **kwargs):
        return await self._mutate(
            "find_one_and_update", selector, update, *args, **kwargs,
        )

    async def find_one_and_replace(self, selector, replacement, *args, **kwargs):
        return await self._mutate(
            "find_one_and_update", selector, replacement, *args, **kwargs,
        )

    async def find_one_and_delete(self, selector, *args, **kwargs):
        return await self._mutate("find_one_and_delete", selector, *args, **kwargs)


class SupabaseRuntimeDatabase(SheetDatabase):
    """Archivio documentale read-through e write-through su Supabase."""

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
        self._document_locations: dict[str, dict[str, str]] = {}
        self._remote_write_lock = asyncio.Lock()
        self.hydration_result: dict[str, Any] | None = None
        self._instance_id = str(uuid.uuid4())

    def __getitem__(self, name: str) -> SupabaseTable:
        return self._tables.setdefault(name, SupabaseTable(self, name))

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
                code = ""
                try:
                    error = json.loads(body)
                    detail = (error.get("message") or "errore remoto")[:240]
                    code = str(error.get("code") or "")
                except (TypeError, ValueError, AttributeError):
                    detail = "errore remoto"
                raise SupabaseRPCError(
                    function_name, response.status, code, detail,
                )
            if not body:
                return None
            return json.loads(body)

    async def _manifest(self) -> list[dict[str, Any]]:
        result = None
        function_name = "gc_collection_catalog"
        for attempt in range(_MANIFEST_RETRIES):
            try:
                try:
                    result = await self._rpc(function_name, {})
                except SupabaseRPCError as exc:
                    # Rolling deploy: only a missing new RPC permits the old
                    # dynamic manifest. Never substitute a static collection list.
                    if function_name != "gc_collection_catalog" or not (
                        exc.status == 404 and exc.code == "PGRST202"
                    ):
                        raise
                    function_name = "gc_collection_manifest"
                    result = await self._rpc(function_name, {})
                break
            except RuntimeError as exc:
                if not _errore_lettura_transitorio(exc):
                    raise
                if attempt == _MANIFEST_RETRIES - 1:
                    raise RuntimeError(
                        "Catalogo Supabase non disponibile: avvio interrotto "
                        "per evitare un archivio parziale"
                    ) from exc
                delay = min(0.5 * (2 ** attempt), 2.0)
                logger.warning(
                    "Manifest Supabase in timeout; nuovo tentativo %s/%s tra %.1fs",
                    attempt + 2, _MANIFEST_RETRIES, delay,
                )
                await asyncio.sleep(delay)
        if not isinstance(result, list):
            raise RuntimeError("Manifest Supabase non valido")
        return result

    async def _fetch_collection_documents(
        self, collection_name: str, *, expected_count: int | None = None,
    ) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        offset = 0
        after_id = ""
        use_keyset = _SHARD_TO_COLLECTION.get(collection_name, collection_name) in _KEYSET_COLLECTIONS
        page_size = _PAGE_SIZE
        # Leggi fino alla pagina corta anche quando esiste un conteggio atteso:
        # durante un deploy l'istanza precedente può aggiungere righe e rendere
        # instabile la paginazione a offset.
        while True:
            timeout_attempt = 0
            while True:
                try:
                    function_name = (
                        "gc_fetch_collection_after" if use_keyset
                        else "gc_fetch_collection"
                    )
                    payload = {
                        "p_collection": collection_name,
                        "p_limit": page_size,
                    }
                    if use_keyset:
                        payload["p_after_id"] = after_id
                    else:
                        payload["p_offset"] = offset
                    try:
                        page = await self._rpc(function_name, payload)
                    except SupabaseRPCError as exc:
                        # Solo una RPC assente prima della prima pagina consente
                        # il fallback. Timeout e permessi devono mantenere la
                        # paginazione scelta e la gestione degli errori originale.
                        if use_keyset and not documents and (
                            exc.status == 404 and exc.code == "PGRST202"
                        ):
                            use_keyset = False
                            logger.warning(
                                "RPC keyset assente; lettura OFFSET per %s",
                                collection_name,
                            )
                            continue
                        raise
                    break
                except RuntimeError as exc:
                    if not _errore_lettura_transitorio(exc):
                        raise
                    if page_size > _MIN_READ_PAGE_SIZE:
                        page_size = max(_MIN_READ_PAGE_SIZE, page_size // 2)
                        timeout_attempt = 0
                        logger.warning(
                            "Lettura %s in timeout all'offset %s; lotto ridotto a %s",
                            collection_name, offset, page_size,
                        )
                        continue
                    timeout_attempt += 1
                    if timeout_attempt >= _READ_RETRIES:
                        raise
                    delay = min(0.5 * (2 ** (timeout_attempt - 1)), 2.0)
                    logger.warning(
                        "Lettura %s in timeout all'offset %s con lotto minimo; "
                        "nuovo tentativo %s/%s tra %.1fs",
                        collection_name, offset, timeout_attempt + 1,
                        _READ_RETRIES, delay,
                    )
                    await asyncio.sleep(delay)
            if not isinstance(page, list):
                raise RuntimeError(
                    f"Risposta Supabase non valida per {collection_name}"
                )
            if use_keyset and page:
                next_id = str(page[-1].get("_id") or "")
                if not next_id or next_id == after_id:
                    raise RuntimeError(
                        f"Cursore keyset non avanzato per {collection_name}"
                    )
                after_id = next_id
            documents.extend(page)
            if len(page) < page_size:
                break
            if not use_keyset:
                offset += len(page)
        # Un inserimento prima dell'offset corrente può riproporre l'ultima riga
        # della pagina precedente. Lo snapshot della singola lettura richiede ID
        # univoci: conserviamo una sola copia senza fondere documenti diversi.
        unique_documents: dict[str, dict[str, Any]] = {}
        without_id: list[dict[str, Any]] = []
        for document in documents:
            document_id = document.get("_id")
            if document_id is None:
                without_id.append(document)
            else:
                unique_documents[str(document_id)] = document
        return [*unique_documents.values(), *without_id]

    def _physical_collections(self, collection_name: str) -> tuple[str, ...]:
        """Restituisce shard prima e collezione primaria per override deterministico."""
        return (*_COLLECTION_SHARDS.get(collection_name, ()), collection_name)

    async def _fetch_logical_collection_documents(
        self, collection_name: str,
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        without_id: list[dict[str, Any]] = []
        locations = self._document_locations.setdefault(collection_name, {})
        for physical_name in self._physical_collections(collection_name):
            for document in await self._fetch_collection_documents(physical_name):
                document_id = document.get("_id")
                if document_id is None:
                    without_id.append(document)
                    continue
                key = str(document_id)
                merged[key] = document
                locations[key] = physical_name
        return [*merged.values(), *without_id]

    async def hydrate(self) -> dict[str, Any]:
        """Verifica il catalogo senza copiare i documenti nel processo web."""
        manifest = await self._manifest()
        totale_righe = 0
        dettaglio: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        for item in manifest:
            physical_name = str(item.get("collection") or "").strip()
            if not physical_name:
                continue
            logical_name = _SHARD_TO_COLLECTION.get(physical_name, physical_name)
            counts[logical_name] = counts.get(logical_name, 0) + int(item.get("row_count") or 0)
        for collection_name, row_count in sorted(counts.items()):
            self._known_collections.add(collection_name)
            totale_righe += row_count
            dettaglio.append({
                "collezione": collection_name,
                "valide": row_count,
                "numero_errori": 0,
            })
        logger.info(
            "Catalogo Supabase verificato: %s righe in %s collezioni",
            totale_righe,
            len(dettaglio),
        )
        result = {"fogli": dettaglio, "righe": totale_righe}
        self.hydration_result = result
        return result

    async def health_probe(self) -> dict[str, Any]:
        """Prova in tempo reale sia la lettura sia l'RPC usata dalle scritture."""
        manifest = await self._manifest()
        await self._rpc(
            "gc_upsert_documents",
            {"p_collection": "runtime_health", "p_documents": []},
        )
        return {"collections": len(manifest), "write_path": "ok"}

    @asynccontextmanager
    async def scheduler_lease(self, job_id: str, ttl_seconds: int = 900):
        """Lease distribuita rinnovata finche il job resta in esecuzione."""
        payload = {
            "p_job_id": str(job_id),
            "p_owner_id": self._instance_id,
            "p_ttl_seconds": ttl_seconds,
        }
        acquired = bool(await self._rpc("gc_try_scheduler_lease", payload))
        if not acquired:
            yield False
            return

        stop = asyncio.Event()

        async def renew() -> None:
            while True:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=ttl_seconds / 3)
                    return
                except asyncio.TimeoutError:
                    renewed = await self._rpc("gc_renew_scheduler_lease", payload)
                    if not renewed:
                        logger.error("Lease scheduler persa durante il job %s", job_id)
                        return
                except Exception:
                    logger.exception("Rinnovo lease scheduler fallito per %s", job_id)
                    return

        heartbeat = asyncio.create_task(renew())
        try:
            yield True
        finally:
            stop.set()
            await heartbeat
            try:
                await self._rpc(
                    "gc_release_scheduler_lease",
                    {"p_job_id": str(job_id), "p_owner_id": self._instance_id},
                )
            except Exception:
                logger.exception("Rilascio lease scheduler fallito per %s", job_id)

    async def _write_through(
        self,
        collection_name: str,
        method: str,
        before: list[dict[str, Any]],
        after: list[dict[str, Any]],
    ) -> None:
        self._known_collections.add(collection_name)
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
        rifiuti = await self._upsert_documents(collection_name, after)
        if rifiuti:
            # Il chiamante e' ancora in attesa della mutazione: l'eccezione
            # consegna la riga autorevole gia' presente in Supabase.
            raise DocumentoDuplicatoRemoto(collection_name, rifiuti)

    async def bulk_seed(
        self, collection_name: str, documents: list[dict[str, Any]],
    ) -> int:
        """Upsert idempotente in blocchi, usato dalla migrazione controllata."""
        rifiuti = await self._upsert_documents(collection_name, documents)
        return len(documents) - len(rifiuti)

    async def mirror_collection(
        self, collection_name: str, documents: list[dict[str, Any]],
    ) -> int:
        """Allinea esattamente una collezione, eliminando solo gli ID obsoleti.

        Serve alla copia di preparazione: una seconda esecuzione produce la
        stessa destinazione anche quando la sorgente ha cancellato record.
        """
        remote_documents = await self._fetch_logical_collection_documents(collection_name)
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
        remote_documents = await self._fetch_logical_collection_documents(collection_name)
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
    ) -> list[dict[str, Any]]:
        """Upsert a blocchi; ritorna i documenti rifiutati per chiave doppia."""
        if not documents:
            return []
        normalised = [_normalise_document(document) for document in documents]
        rifiuti: list[dict[str, Any]] = []
        locations = self._document_locations.setdefault(collection_name, {})
        grouped: dict[str, list[dict[str, Any]]] = {}
        for document in normalised:
            document_id = str(document.get("_id"))
            physical_name = locations.get(document_id, collection_name)
            grouped.setdefault(physical_name, []).append(document)
        for physical_name, physical_documents in grouped.items():
            for start in range(0, len(physical_documents), _WRITE_CHUNK_SIZE):
                chunk = physical_documents[start:start + _WRITE_CHUNK_SIZE]
                result = await self._rpc(
                    "gc_upsert_documents",
                    {"p_collection": physical_name, "p_documents": chunk},
                )
                rifiuti.extend(_rifiuti_da_risposta(result))
                for document in chunk:
                    locations[str(document.get("_id"))] = physical_name
        return rifiuti

    async def _delete_ids(self, collection_name: str, ids: list[str]) -> None:
        clean_ids = [item for item in ids if item and item != "None"]
        if not clean_ids:
            return
        locations = self._document_locations.setdefault(collection_name, {})
        grouped: dict[str, list[str]] = {}
        for item_id in clean_ids:
            grouped.setdefault(locations.get(item_id, collection_name), []).append(item_id)
        for physical_name, physical_ids in grouped.items():
            await self._rpc(
                "gc_delete_documents",
                {"p_collection": physical_name, "p_ids": physical_ids},
            )
            for item_id in physical_ids:
                locations.pop(item_id, None)

    @asynccontextmanager
    async def batch_writes(self):
        """Compatibilita API: ogni mutazione Supabase resta immediata."""
        yield None

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
