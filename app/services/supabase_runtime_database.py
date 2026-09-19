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

from app.services.archivio_documenti_memoria import (
    MISSING, SheetCursor, SheetDatabase, SheetTable, apply_projection, matches_filter,
)
from app.document_repository import DOCUMENT_PAYLOAD_FIELDS, metadata_projection

logger = logging.getLogger(__name__)

_PAGE_SIZE = 500
_MIN_READ_PAGE_SIZE = 10
_READ_RETRIES = 5
# 17/09/2026: con 3 tentativi (0,5 s + 1 s di pausa) il processo usciva con
# "Catalogo Supabase non disponibile" quando il database era sotto carico per
# qualche decina di secondi (statement timeout sul catalogo): il deploy Render
# falliva e l'istanza vecchia, riavviata, cadeva nello stesso errore →
# produzione giu' (osservato 00:18-00:21 UTC). L'avvio ora insiste per circa
# un minuto e mezzo prima di arrendersi: la regola "mai un archivio parziale"
# resta identica, cambia solo quanto aspettiamo un catalogo completo.
_MANIFEST_RETRIES = 12
_MANIFEST_DELAY_MAX_SECONDS = 8.0
_WRITE_CHUNK_SIZE = 50
_KEYSET_COLLECTIONS = {"documents_inbox"}
_EXACT_LOOKUP_FIELDS = (
    "_id",
    "id",
    "idempotency_key",
    "sha256",
    "file_hash",
    "content_hash",
    "pdf_hash",
    "version_id",
)
_MAX_EXACT_LOOKUP_VALUES = 500
_STATUS_ALIGNMENT_BATCH_SIZE = 250
_STATUS_ALIGNMENT_MAX_BATCHES = 40

# 17/09/2026 — cache incrementale (richiesta del titolare: "il sito deve
# lasciare i dati scritti, non ricaricarli ogni volta da Supabase").
# Ogni collezione letta almeno una volta resta in memoria nella versione
# leggera (senza i campi payload di DOCUMENT_PAYLOAD_FIELDS: XML, PDF, foto).
# Prima di servirla si chiede a Supabase la firma di tutte le collezioni con
# UNA RPC (`gc_collection_versions`: conteggio + ultimo updated_at), al piu'
# ogni _CACHE_VERSIONS_TTL secondi: firma uguale → nessuna lettura; firma
# diversa → solo i documenti modificati dopo l'ultima lettura
# (`gc_fetch_collection_since`), rilettura completa solo se il conteggio non
# torna (cancellazioni). Le scritture di questo processo aggiornano la cache
# subito dopo l'esito positivo dell'RPC. Un documento con payload viene
# scaricato per id soltanto quando la lettura lo richiede davvero. Se le RPC
# nuove non esistono (rolling deploy) o falliscono, si torna alla lettura
# completa di prima: mai un risultato parziale.
_CACHE_VERSIONS_TTL_SECONDS = 15.0
# Firma fallita in modo transitorio: la cache resta valida per questo tempo
# dall'ultima firma buona, invece di ripiegare su letture complete.
_CACHE_VERSIONS_GRACE_SECONDS = 120.0
_CACHE_MAX_DOCUMENTS_PER_COLLECTION = 150_000
_CACHE_ENV_FLAG = "GC_RUNTIME_CACHE"
# Presenza del payload nella versione leggera: le RPC proiettate (migrazione
# 20260917073000) e _light_document per le scritture locali aggiungono
# `_payload_stato` = {campo: assente|nullo|vuoto|pieno} per ogni campo escluso.
# Cosi' i filtri «ha il PDF» / «senza XML» (pdf_data $exists, $ne None,
# $nin [None, ""]) si decidono dalla cache senza scaricare gli allegati. Il
# marcatore non esce mai dall'adattatore.
_PAYLOAD_STATO_KEY = "_payload_stato"
_STATI_PAYLOAD = frozenset({"assente", "nullo", "vuoto", "pieno"})
# Lotto di idratazione per id: ricordato per tabella, dimezzato a ogni timeout
# e raddoppiato dopo questo numero di lotti consecutivi riusciti.
_HYDRATE_GROWTH_AFTER = 8

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


def _excluded_projection_fields(projection: Any) -> list[str]:
    """Restituisce solo le proiezioni Mongo puramente esclusive e sicure."""
    if not isinstance(projection, dict) or not projection:
        return []
    excluded = [str(key) for key, value in projection.items() if not value and key != "_id"]
    included = [key for key, value in projection.items() if value and key != "_id"]
    if included or not excluded:
        return []
    return sorted(set(excluded))


def _exact_lookup(selector: Any) -> tuple[str, list[str]] | None:
    """Trova un vincolo esatto indicizzabile senza cambiare la semantica Mongo."""
    if not isinstance(selector, dict):
        return None
    for field in _EXACT_LOOKUP_FIELDS:
        if field not in selector:
            continue
        condition = selector[field]
        if isinstance(condition, dict):
            if set(condition) != {"$in"} or not isinstance(condition["$in"], list):
                continue
            raw_values = condition["$in"]
        else:
            raw_values = [condition]
        values = [str(value) for value in raw_values if value is not None]
        if 0 < len(values) <= _MAX_EXACT_LOOKUP_VALUES:
            return field, sorted(set(values))
    return None


def _references_any_field(value: Any, fields: set[str]) -> bool:
    """Vero se filtro/pipeline usa uno dei campi che vorremmo escludere."""
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).split(".", 1)[0] in fields:
                return True
            if _references_any_field(nested, fields):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_references_any_field(item, fields) for item in value)
    if isinstance(value, str) and value.startswith("$"):
        return value[1:].split(".", 1)[0] in fields
    return False


def _metadata_projection_if_safe(collection: str, operation: Any) -> dict[str, Any] | None:
    fields = set(DOCUMENT_PAYLOAD_FIELDS.get(collection, ()))
    if not fields or _references_any_field(operation, fields):
        return None
    return metadata_projection(collection)


def _projection_needs_payload(projection: Any, payload_fields: set[str]) -> bool:
    """Vero se la lettura richiede almeno un campo payload della collezione."""
    if not payload_fields:
        return False
    if not isinstance(projection, dict) or not projection:
        return True
    included = [str(key) for key, value in projection.items() if value and key != "_id"]
    if included:
        return any(key.split(".", 1)[0] in payload_fields for key in included)
    excluded = {str(key).split(".", 1)[0] for key, value in projection.items()
                if not value and key != "_id" and "." not in str(key)}
    return not payload_fields.issubset(excluded)


def _stato_payload(value: Any) -> str:
    """Stesso calcolo di public.gc_payload_stato, per i documenti locali."""
    if value is MISSING:
        return "assente"
    if value is None:
        return "nullo"
    if isinstance(value, (str, list, dict)) and len(value) == 0:
        return "vuoto"
    return "pieno"


def _light_document(document: dict[str, Any], payload_fields: set[str]) -> dict[str, Any]:
    """Versione leggera di un documento COMPLETO: senza payload, con il
    marcatore di presenza calcolato dai campi presenti (un marcatore gia'
    presente vale per i campi che il documento non porta)."""
    if not payload_fields:
        return document
    precedente = document.get(_PAYLOAD_STATO_KEY)
    stato = dict(precedente) if isinstance(precedente, dict) else {}
    for field in payload_fields:
        if field in document:
            stato[field] = _stato_payload(document[field])
        elif field not in stato:
            stato[field] = "assente"
    light = {key: value for key, value in document.items() if key not in payload_fields}
    light[_PAYLOAD_STATO_KEY] = stato
    return light


def _senza_stato(document: dict[str, Any]) -> dict[str, Any]:
    if _PAYLOAD_STATO_KEY not in document:
        return document
    return {key: value for key, value in document.items() if key != _PAYLOAD_STATO_KEY}


def _stati_da_uguaglianza(value: Any) -> set[str] | None:
    if value is None:
        return {"assente", "nullo"}
    if value == "":
        return {"vuoto"}
    return None


def _stati_da_condizione(condition: Any) -> set[str] | None:
    """Stati del marcatore compatibili con una condizione Mongo di presenza;
    None se la condizione guarda il contenuto (regex, valore, ...)."""
    if not isinstance(condition, dict) or not any(str(key).startswith("$") for key in condition):
        return _stati_da_uguaglianza(condition)
    stati = set(_STATI_PAYLOAD)
    for operator, expected in condition.items():
        if operator == "$exists":
            consentiti = {"nullo", "vuoto", "pieno"} if expected else {"assente"}
        elif operator == "$eq":
            consentiti = _stati_da_uguaglianza(expected)
        elif operator == "$ne":
            esclusi = _stati_da_uguaglianza(expected)
            consentiti = None if esclusi is None else set(_STATI_PAYLOAD) - esclusi
        elif operator in {"$in", "$nin"}:
            if not isinstance(expected, (list, tuple)):
                return None
            unione: set[str] = set()
            for item in expected:
                parziale = _stati_da_uguaglianza(item)
                if parziale is None:
                    return None
                unione |= parziale
            consentiti = unione if operator == "$in" else set(_STATI_PAYLOAD) - unione
        else:
            return None
        if consentiti is None:
            return None
        stati &= consentiti
    return stati


def _riscrivi_presenza(selector: Any, payload_fields: set[str]) -> Any:
    """Selettore equivalente valutabile sulla versione leggera (i vincoli sui
    campi payload diventano vincoli sul marcatore), oppure None se almeno un
    vincolo richiede il contenuto del payload."""
    if not isinstance(selector, dict):
        return selector
    result: dict[str, Any] = {}
    for key, condition in selector.items():
        name = str(key)
        if name in {"$or", "$and", "$nor"}:
            if not isinstance(condition, list):
                return None
            branches = []
            for branch in condition:
                rewritten = _riscrivi_presenza(branch, payload_fields)
                if rewritten is None:
                    return None
                branches.append(rewritten)
            result[key] = branches
        elif name.split(".", 1)[0] in payload_fields:
            if "." in name:
                return None
            stati = _stati_da_condizione(condition)
            if stati is None:
                return None
            result[f"{_PAYLOAD_STATO_KEY}.{name}"] = {"$in": sorted(stati)}
        else:
            if _references_any_field(condition, payload_fields):
                return None
            result[key] = condition
    return result


def _cache_abilitata() -> bool:
    import os

    return os.environ.get(_CACHE_ENV_FLAG, "1").strip().lower() not in {"0", "false", "no", "off"}


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
    """Vista su Supabase con cache leggera incrementale (vedi _CACHE_* sopra).

    L'autorita' resta Supabase: la cache serve le letture che non hanno
    bisogno del payload documentale e filtra quelle che ne hanno bisogno,
    cosi' da scaricare per id soltanto i documenti coinvolti.
    """

    def __init__(self, database: "SupabaseRuntimeDatabase", name: str):
        super().__init__(database, name)
        self._remote_operation_lock = asyncio.Lock()
        self._payload_fields = set(DOCUMENT_PAYLOAD_FIELDS.get(name, ()))
        self._cache: dict[str, dict[str, Any]] | None = None
        self._cache_signature: tuple | None = None
        self._cache_watermark: dict[str, str | None] = {}
        # Lock separato dalle operazioni remote: una lettura servita dalla
        # cache non deve aspettare una scrittura o una lettura completa lenta
        # sulla stessa collezione (osservato il 17/09: liste bloccate per
        # minuti dietro il job di riconciliazione).
        self._cache_lock = asyncio.Lock()
        # Vero se ogni documento in cache porta il marcatore di presenza del
        # payload (RPC proiettate migrate): solo allora i filtri «ha il PDF»
        # si decidono in memoria.
        self._cache_stato_payload = False
        self._hydrate_chunk = _MAX_EXACT_LOOKUP_VALUES
        self._hydrate_successi = 0

    # ----- cache -----------------------------------------------------------

    def _cache_light(self, document: dict[str, Any]) -> dict[str, Any]:
        return _normalise_document(_light_document(document, self._payload_fields))

    def _selettore_cache(self, selector) -> tuple[Any, bool]:
        """(selettore valutabile sulla versione leggera, richiede il marcatore).
        Il selettore stesso se non tocca i campi payload; la riscrittura sul
        marcatore di presenza se li usa solo come «c'e' / non c'e'»; None se
        serve il contenuto del payload (o la cache e' spenta)."""
        if not self.database._cache_enabled:
            return None, False
        if not _references_any_field(selector, self._payload_fields):
            return (selector if selector is not None else {}), False
        leggero = _riscrivi_presenza(selector, self._payload_fields)
        return leggero, leggero is not None

    def _cache_can_filter(self, selector) -> bool:
        """Vero se la cache puo' decidere QUALI documenti servono."""
        return self._selettore_cache(selector)[0] is not None

    def _cache_can_serve(self, selector, projection) -> bool:
        """Vero se la lettura non ha bisogno del payload (filtro e proiezione)."""
        return self._cache_can_filter(selector) and not _projection_needs_payload(
            projection, self._payload_fields)

    async def _hydrate_by_ids(self, ids: list[str], excluded_fields: list[str] | None) -> list[dict[str, Any]]:
        """Documenti completi (payload incluso) per id, a lotti che si
        restringono sui timeout: mai una lettura completa della collezione,
        che sotto carico durava decine di minuti tenendo il lock operativo
        (osservato il 17/09: 10 fatture ogni 20 s, tutte le scritture ferme).
        Il lotto e' ricordato per tabella: dopo un timeout la lettura
        successiva parte gia' dalla misura che funzionava, invece di pagare
        di nuovo tutta la scala 500 → 250 → ... (20 s a gradino)."""
        documents: list[dict[str, Any]] = []
        index = 0
        while index < len(ids):
            chunk = self._hydrate_chunk
            batch = ids[index:index + chunk]
            try:
                rows = await self.database._fetch_logical_documents_exact(
                    self.name, field="_id", values=sorted(batch),
                    excluded_fields=excluded_fields,
                )
            except RuntimeError as exc:
                if _errore_lettura_transitorio(exc) and chunk > _MIN_READ_PAGE_SIZE:
                    self._hydrate_chunk = max(_MIN_READ_PAGE_SIZE, chunk // 2)
                    self._hydrate_successi = 0
                    logger.warning(
                        "Lettura per id di %s in timeout; lotto ridotto a %s",
                        self.name, self._hydrate_chunk,
                    )
                    continue
                raise
            documents.extend(rows)
            index += len(batch)
            if chunk < _MAX_EXACT_LOOKUP_VALUES:
                self._hydrate_successi += 1
                if self._hydrate_successi >= _HYDRATE_GROWTH_AFTER:
                    self._hydrate_chunk = min(_MAX_EXACT_LOOKUP_VALUES, chunk * 2)
                    self._hydrate_successi = 0
        return [_normalise_document(document) for document in documents]

    async def _cached_snapshot(self, *, richiede_stato: bool = False) -> list[dict[str, Any]] | None:
        """Documenti leggeri allineati allo stato remoto, senza il lock operativo.
        Con richiede_stato la cache vale solo se ogni documento porta il
        marcatore di presenza del payload (RPC gia' migrate)."""
        async with self._cache_lock:
            if not await self._cache_ready():
                return None
            assert self._cache is not None
            if richiede_stato and self._payload_fields and not self._cache_stato_payload:
                return None
            return list(self._cache.values())

    async def _cache_ready(self) -> bool:
        """Porta la cache allo stato remoto corrente. False = cache non usabile."""
        database = self.database
        if not database._cache_enabled:
            return False
        versions = await database._collection_versions()
        if versions is None:
            return False
        physical = database._physical_collections(self.name)
        signature = tuple(
            (name, *(versions.get(name) or (0, None))) for name in physical
        )
        total = sum(int(versions.get(name, (0, None))[0]) for name in physical)
        if total > _CACHE_MAX_DOCUMENTS_PER_COLLECTION:
            self._cache = None
            return False
        if self._cache is not None and signature == self._cache_signature:
            return True
        if self._cache is None:
            await self._cache_load_all()
        else:
            await self._cache_apply_delta(versions, physical)
            if len(self._cache) != total:
                # Cancellazioni (o conteggio cambiato durante il delta): la
                # rilettura completa e' l'unico modo per essere esatti.
                await self._cache_load_all()
        self._cache_signature = signature
        for name in physical:
            self._cache_watermark[name] = (versions.get(name) or (0, None))[1]
        return True

    async def _cache_load_all(self) -> None:
        documents = await self.database._fetch_logical_collection_documents(
            self.name, excluded_fields=sorted(self._payload_fields) or None,
        )
        self._cache = {
            str(document.get("_id")): _normalise_document(document)
            for document in documents if document.get("_id") is not None
        }
        self._cache_stato_payload = all(
            _PAYLOAD_STATO_KEY in document for document in self._cache.values()
        )

    async def _cache_apply_delta(self, versions, physical) -> None:
        assert self._cache is not None
        for name in physical:
            remote = versions.get(name)
            if remote is None:
                continue
            since = self._cache_watermark.get(name)
            if remote[1] is not None and since is not None and remote[1] <= since:
                continue
            for document in await self.database._fetch_collection_since(
                name, since, excluded_fields=sorted(self._payload_fields) or None,
            ):
                if document.get("_id") is None:
                    continue
                if _PAYLOAD_STATO_KEY not in document:
                    self._cache_stato_payload = False
                self._cache[str(document["_id"])] = _normalise_document(document)
                self.database._document_locations.setdefault(self.name, {})[
                    str(document["_id"])] = name

    def _cache_apply_mutation(self, method: str, before, after) -> None:
        """Scrittura di questo processo gia' confermata da Supabase."""
        if self._cache is None:
            return
        if method in {"delete_one", "delete_many", "find_one_and_delete"}:
            for document in before:
                self._cache.pop(str(document.get("_id")), None)
            return
        for document in after:
            if document.get("_id") is not None:
                self._cache[str(document["_id"])] = self._cache_light(document)

    def cache_stats(self) -> dict[str, Any]:
        return {
            "collection": self.name,
            "documenti_in_cache": None if self._cache is None else len(self._cache),
            "payload_escluso": sorted(self._payload_fields),
        }

    # ----- letture ---------------------------------------------------------

    async def _refresh_unlocked(self, projection=None, selector=None) -> None:
        lookup = _exact_lookup(selector)
        leggero, richiede_stato = self._selettore_cache(selector)
        if lookup:
            if leggero is not None and not _projection_needs_payload(projection, self._payload_fields):
                documents = await self._cached_snapshot(richiede_stato=richiede_stato)
                if documents is not None:
                    self._documents = [
                        _senza_stato(d) for d in documents if matches_filter(d, leggero)]
                    return
            field, values = lookup
            documents = await self.database._fetch_logical_documents_exact(
                self.name,
                field=field,
                values=values,
                excluded_fields=_excluded_projection_fields(projection),
            )
            self._documents = [_normalise_document(document) for document in documents]
            return
        if leggero is not None:
            documents = await self._cached_snapshot(richiede_stato=richiede_stato)
            if documents is not None:
                if not _projection_needs_payload(projection, self._payload_fields):
                    self._documents = [_senza_stato(d) for d in documents]
                    return
                # La cache decide QUALI documenti servono; Supabase fornisce
                # il payload solo per quelli (lookup esatto per id, a lotti).
                matched = [
                    str(document["_id"]) for document in documents
                    if document.get("_id") is not None and matches_filter(document, leggero)
                ]
                self._documents = await self._hydrate_by_ids(
                    matched, _excluded_projection_fields(projection))
                return
        # Lettura completa: un campo payload citato dal filtro deve arrivare
        # anche se la proiezione lo esclude, altrimenti il filtro locale
        # vedrebbe «assente» per tutti (conteggio sbagliato in silenzio).
        excluded = [
            field for field in _excluded_projection_fields(projection)
            if not _references_any_field(selector, {field})
        ]
        documents = await self.database._fetch_logical_collection_documents(
            self.name,
            excluded_fields=excluded,
        )
        # Con esclusioni la RPC allega il marcatore di presenza: resta un
        # dettaglio dell'adattatore, mai nei documenti restituiti.
        self._documents = [_senza_stato(_normalise_document(document)) for document in documents]
        if self._cache is not None and not _excluded_projection_fields(projection):
            # Lettura completa gia' pagata: aggiorna la cache gratis.
            for document in self._documents:
                if document.get("_id") is not None:
                    self._cache[str(document["_id"])] = self._cache_light(document)

    async def _prepare_insert_unlocked(
        self, documents: list[dict[str, Any]],
    ) -> None:
        """Carica soltanto conflitti di ID o idempotenza prima dell'INSERT."""
        lookups = [
            ("_id", [str(document["_id"]) for document in documents]),
            (
                "idempotency_key",
                [
                    str(document["idempotency_key"])
                    for document in documents
                    if document.get("idempotency_key")
                ],
            ),
        ]
        found: dict[str, dict[str, Any]] = {}
        for field, values in lookups:
            if not values:
                continue
            rows = await self.database._fetch_logical_documents_exact(
                self.name, field=field, values=sorted(set(values)),
            )
            for row in rows:
                if row.get("_id") is not None:
                    found[str(row["_id"])] = row
        self._documents = [_normalise_document(row) for row in found.values()]

    def find(self, selector=None, projection=None, *args, **kwargs):
        async def load():
            needs_payload = _projection_needs_payload(projection, self._payload_fields)
            lookup = _exact_lookup(selector)
            if lookup and needs_payload:
                # Lookup puntuale con payload (es. find_one({"id": ...})):
                # l'indice remoto basta, la cache non aggiungerebbe nulla e la
                # firma costerebbe una RPC in piu'. Senza lock operativo.
                field, values = lookup
                rows = await self.database._fetch_logical_documents_exact(
                    self.name, field=field, values=values,
                    excluded_fields=_excluded_projection_fields(projection),
                )
                return SheetCursor([
                    apply_projection(document, projection)
                    for document in (_normalise_document(row) for row in rows)
                    if matches_filter(document, selector)
                ])
            leggero, richiede_stato = self._selettore_cache(selector)
            if leggero is not None:
                # Lettura senza lock operativo: una pagina non aspetta il job
                # che sta scrivendo la stessa collezione. Senza payload arriva
                # tutto dalla cache (anche i lookup puntuali); con payload la
                # cache sceglie i documenti e Supabase li manda per id.
                documents = await self._cached_snapshot(richiede_stato=richiede_stato)
                if documents is not None:
                    if needs_payload:
                        matched = [
                            str(document["_id"]) for document in documents
                            if document.get("_id") is not None
                            and matches_filter(document, leggero)
                        ]
                        documents = await self._hydrate_by_ids(
                            matched, _excluded_projection_fields(projection))
                        return SheetCursor([
                            apply_projection(document, projection) for document in documents
                        ])
                    return SheetCursor([
                        apply_projection(_senza_stato(document), projection)
                        for document in documents
                        if matches_filter(document, leggero)
                    ])
            async with self._remote_operation_lock:
                await self._refresh_unlocked(projection, selector)
                return SheetTable.find(self, selector, projection, *args, **kwargs)

        return _ReadThroughCursor(load)

    async def find_one(self, selector=None, projection=None, *args, **kwargs):
        cursor = self.find(selector, projection, *args, **kwargs)
        if kwargs.get("sort"):
            cursor.sort(kwargs["sort"])
        documents = await cursor.limit(1).to_list(1)
        return documents[0] if documents else None

    async def count_documents(self, selector=None, *args, **kwargs) -> int:
        projection = _metadata_projection_if_safe(self.name, selector)
        if projection is None and self._payload_fields and self._cache_can_filter(selector):
            # Filtro di sola presenza sul payload («ha il PDF»): il conteggio
            # non ha bisogno del contenuto, la cache risponde dal marcatore.
            projection = metadata_projection(self.name)
        return len(await self.find(selector, projection).to_list(None))

    async def estimated_document_count(self, *args, **kwargs) -> int:
        projection = _metadata_projection_if_safe(self.name, {})
        return len(await self.find({}, projection).to_list(None))

    async def distinct(self, key, selector=None, *args, **kwargs):
        async with self._remote_operation_lock:
            await self._refresh_unlocked(selector=selector)
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
                await self._refresh_unlocked(
                    projection=_metadata_projection_if_safe(self.name, pipeline)
                )
                return SheetTable.aggregate(self, pipeline, *args, **kwargs)

        return _ReadThroughCursor(load)

    async def _mutate(self, method_name: str, *args, **kwargs):
        async with self._remote_operation_lock:
            selector = args[0] if method_name not in {"insert_one", "insert_many"} else None
            if method_name == "insert_one":
                document = args[0]
                document.setdefault("_id", str(uuid.uuid4()))
                await self._prepare_insert_unlocked([document])
            elif method_name == "insert_many":
                documents = list(args[0])
                for document in documents:
                    document.setdefault("_id", str(uuid.uuid4()))
                args = (documents, *args[1:])
                await self._prepare_insert_unlocked(documents)
            else:
                await self._refresh_unlocked(selector=selector)
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
        #: I job di cui questa istanza tiene il lease adesso: servono a
        #: rilasciarli allo spegnimento invece di lasciarli scadere.
        self._lease_attive: set[str] = set()
        self._cache_enabled = _cache_abilitata()
        self._versions: dict[str, tuple[int, str | None]] = {}
        self._versions_checked_at: float | None = None
        self._versions_good_at: float | None = None
        self._versions_lock = asyncio.Lock()

    async def _collection_versions(self) -> dict[str, tuple[int, str | None]] | None:
        """Firma (conteggio, ultimo updated_at) di ogni collezione fisica.

        Una sola RPC per tutte le collezioni, al piu' ogni
        _CACHE_VERSIONS_TTL_SECONDS. None = firma non disponibile: il
        chiamante legge da Supabase come prima (mai un dato parziale).
        """
        if not self._cache_enabled:
            return None
        loop = asyncio.get_running_loop()
        async with self._versions_lock:
            now = loop.time()
            if (
                self._versions_checked_at is not None
                and now - self._versions_checked_at < _CACHE_VERSIONS_TTL_SECONDS
            ):
                return self._versions
            try:
                rows = await self._rpc("gc_collection_versions", {})
            except SupabaseRPCError as exc:
                if exc.status == 404 and exc.code == "PGRST202":
                    logger.warning("RPC gc_collection_versions assente: cache disattivata")
                    self._cache_enabled = False
                    return None
                return self._versions_stantie(now, exc)
            except Exception as exc:  # noqa: BLE001 - la cache non deve mai bloccare una lettura
                return self._versions_stantie(now, exc)
            if not isinstance(rows, list):
                return self._versions_stantie(now, "risposta non valida")
            versions: dict[str, tuple[int, str | None]] = {}
            for row in rows:
                if not isinstance(row, dict) or not row.get("collection"):
                    continue
                updated = row.get("max_updated_at")
                versions[str(row["collection"])] = (
                    int(row.get("row_count") or 0),
                    str(updated) if updated is not None else None,
                )
            self._versions = versions
            self._versions_checked_at = now
            self._versions_good_at = now
            return versions

    def _versions_stantie(self, now: float, motivo: Any):
        """Firma fallita in modo transitorio (timeout, 503 durante una ricarica
        dello schema di PostgREST). Entro _CACHE_VERSIONS_GRACE_SECONDS
        dall'ultima firma buona la cache resta valida cosi' com'e' (dati al
        piu' vecchi di quel tanto, le scritture di questo processo sono
        comunque gia' dentro) invece di ripiegare su letture complete: a
        database saturo sono proprio quelle a far fallire la firma
        (17/09 07:43-07:45: 30 fallimenti → 30 letture complete in 2 minuti)."""
        eta = None if self._versions_good_at is None else now - self._versions_good_at
        if self._versions and eta is not None and eta < _CACHE_VERSIONS_GRACE_SECONDS:
            logger.warning(
                "Firma collezioni non disponibile (%s): cache mantenuta (firma di %.0f s fa)",
                motivo, eta,
            )
            self._versions_checked_at = now
            return self._versions
        logger.warning("Firma collezioni non disponibile (%s): lettura completa", motivo)
        return None

    def invalidate_versions(self) -> None:
        """Forza una nuova firma alla prossima lettura (dopo scritture esterne note)."""
        self._versions_checked_at = None

    async def _fetch_collection_since(
        self, physical_name: str, since: str | None, *, excluded_fields: list[str] | None,
    ) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = await self._rpc(
                "gc_fetch_collection_since",
                {
                    "p_collection": physical_name,
                    "p_since": since,
                    "p_offset": offset,
                    "p_limit": _PAGE_SIZE,
                    "p_exclude_fields": excluded_fields or [],
                },
            )
            if not isinstance(page, list):
                raise RuntimeError(f"Risposta Supabase delta non valida per {physical_name}")
            documents.extend(page)
            if len(page) < _PAGE_SIZE:
                return documents
            offset += len(page)

    def cache_stats(self) -> dict[str, Any]:
        return {
            "abilitata": self._cache_enabled,
            "collezioni": [
                table.cache_stats() for table in self._tables.values()
                if isinstance(table, SupabaseTable) and table._cache is not None
            ],
        }

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
                delay = min(0.5 * (2 ** attempt), _MANIFEST_DELAY_MAX_SECONDS)
                logger.warning(
                    "Manifest Supabase in timeout; nuovo tentativo %s/%s tra %.1fs",
                    attempt + 2, _MANIFEST_RETRIES, delay,
                )
                await asyncio.sleep(delay)
        if not isinstance(result, list):
            raise RuntimeError("Manifest Supabase non valido")
        return result

    async def _fetch_collection_documents(
        self,
        collection_name: str,
        *,
        expected_count: int | None = None,
        excluded_fields: list[str] | None = None,
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
                    projected_keyset = bool(use_keyset and excluded_fields)
                    projected_offset = bool(not use_keyset and excluded_fields)
                    function_name = (
                        "gc_fetch_collection_after_projected"
                        if projected_keyset
                        else "gc_fetch_collection_projected"
                        if projected_offset
                        else "gc_fetch_collection_after"
                        if use_keyset
                        else "gc_fetch_collection"
                    )
                    payload = {
                        "p_collection": collection_name,
                        "p_limit": page_size,
                    }
                    if use_keyset:
                        payload["p_after_id"] = after_id
                        if projected_keyset:
                            payload["p_exclude_fields"] = excluded_fields
                    else:
                        payload["p_offset"] = offset
                        if projected_offset:
                            payload["p_exclude_fields"] = excluded_fields
                    try:
                        page = await self._rpc(function_name, payload)
                    except SupabaseRPCError as exc:
                        # Solo una RPC assente prima della prima pagina consente
                        # il fallback. Timeout e permessi devono mantenere la
                        # paginazione scelta e la gestione degli errori originale.
                        if (projected_keyset or projected_offset) and not documents and (
                            exc.status == 404 and exc.code == "PGRST202"
                        ):
                            excluded_fields = None
                            logger.warning(
                                "RPC proiezione assente; lettura completa per %s",
                                collection_name,
                            )
                            continue
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
        self, collection_name: str, *, excluded_fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        without_id: list[dict[str, Any]] = []
        locations = self._document_locations.setdefault(collection_name, {})
        for physical_name in self._physical_collections(collection_name):
            for document in await self._fetch_collection_documents(
                physical_name, excluded_fields=excluded_fields,
            ):
                document_id = document.get("_id")
                if document_id is None:
                    without_id.append(document)
                    continue
                key = str(document_id)
                merged[key] = document
                locations[key] = physical_name
        return [*merged.values(), *without_id]

    async def _fetch_logical_documents_exact(
        self,
        collection_name: str,
        *,
        field: str,
        values: list[str],
        excluded_fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Legge soltanto i documenti identificati da un vincolo esatto."""
        merged: dict[str, dict[str, Any]] = {}
        locations = self._document_locations.setdefault(collection_name, {})
        for physical_name in self._physical_collections(collection_name):
            result = await self._rpc(
                "gc_fetch_documents_exact",
                {
                    "p_collection": physical_name,
                    "p_field": field,
                    "p_values": values,
                    "p_exclude_fields": excluded_fields or [],
                },
            )
            if not isinstance(result, list):
                raise RuntimeError(
                    f"Risposta Supabase puntuale non valida per {collection_name}"
                )
            for document in result:
                document_id = document.get("_id")
                if document_id is None:
                    continue
                key = str(document_id)
                merged[key] = document
                locations[key] = physical_name
        return list(merged.values())

    async def align_processed_document_status(self) -> int:
        """Allinea i badge in transazioni brevi, senza scaricare i PDF."""
        total = 0
        for _ in range(_STATUS_ALIGNMENT_MAX_BATCHES):
            affected = int(
                await self._rpc("gc_align_processed_document_status", {}) or 0
            )
            total += affected
            if affected < _STATUS_ALIGNMENT_BATCH_SIZE:
                break
        return total

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
        """Prova scrittura e cancellazione atomiche senza lasciare dati."""
        probe_id = f"health:{self._instance_id}"
        result = await self._rpc(
            "gc_runtime_health_probe", {"p_probe_id": probe_id},
        )
        if result is not True:
            raise RuntimeError("Probe scrittura Supabase rifiutata")
        collections = len((self.hydration_result or {}).get("fogli") or [])
        return {"collections": collections, "write_path": "verified"}

    @asynccontextmanager
    async def scheduler_lease(self, job_id: str, ttl_seconds: int = 900):
        """Lease distribuita rinnovata finche il job resta in esecuzione.

        Se il processo muore col lease in mano, il job resta bloccato per
        tutto il TTL: l'istanza nuova lo trova occupato e salta il turno. Con
        900 secondi vuol dire un quarto d'ora di lavoro di fondo fermo dopo
        ogni deploy — misurato il 19/09/2026 sulla ricostruzione dell'archivio
        Drive, ferma a 57 file su 2.447 per venti minuti. Per questo i lease
        vivi si annotano e si rilasciano allo spegnimento.
        """
        payload = {
            "p_job_id": str(job_id),
            "p_owner_id": self._instance_id,
            "p_ttl_seconds": ttl_seconds,
        }
        acquired = bool(await self._rpc("gc_try_scheduler_lease", payload))
        if not acquired:
            yield False
            return
        self._lease_attive.add(str(job_id))

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
            await self._rilascia_lease(str(job_id))

    async def _rilascia_lease(self, job_id: str) -> None:
        self._lease_attive.discard(job_id)
        try:
            await self._rpc(
                "gc_release_scheduler_lease",
                {"p_job_id": job_id, "p_owner_id": self._instance_id},
            )
        except Exception:
            logger.exception("Rilascio lease scheduler fallito per %s", job_id)

    async def rilascia_lease_attive(self) -> list[str]:
        """Restituisce i lease che questa istanza ha ancora in mano.

        Va chiamata allo spegnimento: un lease abbandonato blocca il suo job
        per tutto il TTL, e l'istanza che subentra puo' solo saltare il turno.
        Si rilascia per `job_id`, con la stessa RPC del percorso normale:
        nessuna cancellazione con filtro.
        """
        rimasti = sorted(self._lease_attive)
        for job_id in rimasti:
            await self._rilascia_lease(job_id)
        return rimasti

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
        table = self._tables.get(collection_name)
        if isinstance(table, SupabaseTable):
            table._cache_apply_mutation(method, before, after)

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
