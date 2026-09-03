"""Archivio dei contenuti binari del gestionale (PDF e immagini in base64).

Il runtime documentale del gestionale tiene TUTTI i documenti in memoria e
li scrive su ``gestionale.documents``. I PDF di cedolini, bonifici e
documenti dei dipendenti pesano centinaia di MB: non possono stare nella
cache del processo (Render Starter, 512 MiB). Qui vivono in una tabella
separata ``gestionale.blobs`` letta solo su richiesta, tramite le stesse RPC
protette dalla chiave runtime.

La chiave di un blob e' l'impronta SHA-256 del suo contenuto
(``sha256:<hex>``): lo stesso PDF citato da piu' documenti (per esempio la
stessa distinta di bonifici copiata su ogni bonifico, o un bonifico presente
sia in ``bonifici`` sia in ``pagamenti_esiti``) occupa spazio UNA sola volta.
L'archivio conta i riferimenti: ``put`` ne aggiunge uno, ``delete`` ne toglie
uno e cancella davvero solo all'ultimo. Il documento conserva la chiave sotto
``_blobs`` (vedi ``db_adapter``), cosi' resta piccolo e il contenuto si
recupera anche quando la proiezione toglie ``_id``.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

Rpc = Callable[[str, Dict[str, Any]], Awaitable[Any]]


def blob_key(data: str) -> str:
    """Chiave a contenuto: stessa stringa base64 -> stessa chiave."""
    return "sha256:" + hashlib.sha256(data.encode("utf-8")).hexdigest()


class BlobStore:
    """Interfaccia minima: put (aggiunge un riferimento), get, delete (toglie
    un riferimento, cancella all'ultimo), stats."""

    persistent: bool = False

    async def put(self, key: str, data: str) -> None:
        raise NotImplementedError

    async def get(self, key: str) -> Optional[str]:
        raise NotImplementedError

    async def delete(self, keys: Iterable[str]) -> int:
        raise NotImplementedError

    async def stats(self, prefix: str) -> Dict[str, int]:
        raise NotImplementedError


class SupabaseBlobStore(BlobStore):
    """Persistenza su ``gestionale.blobs`` via RPC ``gc_*_blob``."""

    persistent = True

    def __init__(self, rpc: Rpc):
        self._rpc = rpc

    async def put(self, key: str, data: str) -> None:
        await self._rpc("gc_put_blob", {"p_key": key, "p_data": data})

    async def get(self, key: str) -> Optional[str]:
        result = await self._rpc("gc_get_blob", {"p_key": key})
        if result is None or result == "":
            return None
        return str(result)

    async def delete(self, keys: Iterable[str]) -> int:
        clean = [k for k in keys if k]
        if not clean:
            return 0
        result = await self._rpc("gc_delete_blobs", {"p_keys": clean})
        return int(result or 0)

    async def stats(self, prefix: str) -> Dict[str, int]:
        result = await self._rpc("gc_blob_stats", {"p_prefix": prefix}) or {}
        return {"count": int(result.get("count", 0)), "bytes": int(result.get("bytes", 0)),
                "refs": int(result.get("refs", 0))}


class MemoryBlobStore(BlobStore):
    """Solo per test e sviluppo locale senza Supabase: niente persistenza."""

    persistent = False

    def __init__(self):
        self._data: Dict[str, str] = {}
        self._refs: Dict[str, int] = {}

    async def put(self, key: str, data: str) -> None:
        self._data[key] = data
        self._refs[key] = self._refs.get(key, 0) + 1

    async def get(self, key: str) -> Optional[str]:
        return self._data.get(key)

    async def delete(self, keys: Iterable[str]) -> int:
        removed = 0
        for key in keys:
            if key not in self._refs:
                continue
            self._refs[key] -= 1
            if self._refs[key] <= 0:
                self._refs.pop(key, None)
                self._data.pop(key, None)
                removed += 1
        return removed

    async def stats(self, prefix: str) -> Dict[str, int]:
        keys: List[str] = [k for k in self._data if k.startswith(prefix)]
        return {"count": len(keys), "bytes": sum(len(self._data[k]) for k in keys),
                "refs": sum(self._refs[k] for k in keys)}


def blob_store_per_runtime(runtime: Any) -> BlobStore:
    """Sceglie l'archivio in base al runtime documentale attivo.

    Con ``DATA_BACKEND=supabase`` il runtime espone ``_rpc``: i blob vanno su
    ``gestionale.blobs``. Con il runtime Sheets (o nei test) resta la memoria,
    e lo si dice chiaramente nel log: i file caricati non sopravviverebbero a
    un riavvio.
    """
    rpc = getattr(runtime, "_rpc", None)
    if callable(rpc):
        return SupabaseBlobStore(rpc)
    logger.warning(
        "Modulo HR: archivio binari IN MEMORIA (runtime senza Supabase). "
        "PDF e documenti caricati non sono persistenti: impostare DATA_BACKEND=supabase."
    )
    return MemoryBlobStore()
