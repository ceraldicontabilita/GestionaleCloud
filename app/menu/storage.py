"""Accesso ai dati del modulo Menu nel registro unico del gestionale.

Le collezioni riprendono i nomi delle vecchie tabelle Supabase dell'app Menu
(``menu_categories``, ``menu_products``...). Il magazzino bar e' la
collezione ``magazzino_bar_prodotti`` di Lotti: era gia' condivisa tra le
due app e resta unica anche qui.

Le immagini (categorie, sottocategorie, prodotti) vivono nell'archivio
binari a contenuto (``app/services/blob_store.py``) e sono servite da
``GET /api/menu/pubblico/immagini/{id}``: nessun bucket esterno.
"""
from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.database import Database
from app.services.blob_store import BlobStore, blob_key, blob_store_per_runtime

COLL_CATEGORIE = "menu_categories"
COLL_SOTTOCATEGORIE = "menu_subcategories"
COLL_PRODOTTI = "menu_products"
COLL_ALLERGENI = "menu_allergens"
COLL_QRCODE = "menu_qrcode_config"
COLL_ORDINI = "menu_orders"
COLL_SALE = "menu_sale"
COLL_MOVIMENTI = "menu_warehouse_movements"
COLL_IMMAGINI = "menu_immagini"
COLL_MAGAZZINO_BAR = "magazzino_bar_prodotti"

# Collezioni esportate/ripristinate dal backup del menu (il magazzino bar e'
# di Lotti e resta fuori, come nella vecchia app).
COLLEZIONI_BACKUP = [
    COLL_CATEGORIE, COLL_SOTTOCATEGORIE, COLL_PRODOTTI, COLL_ALLERGENI,
    COLL_QRCODE, COLL_ORDINI, COLL_SALE, COLL_MOVIMENTI, COLL_IMMAGINI,
]

PERCORSO_IMMAGINI = "/api/menu/pubblico/immagini/"
ID_CONFIG_QR = "qrcode_config"
FORMATO_BACKUP = "gestionalecloud-menu/1"


def db():
    runtime = Database.db
    if runtime is None:
        raise RuntimeError("Registro dati del gestionale non connesso")
    return runtime


_blob_cache: Dict[int, BlobStore] = {}


def blobs() -> BlobStore:
    runtime = db()
    store = _blob_cache.get(id(runtime))
    if store is None:
        _blob_cache.clear()
        store = blob_store_per_runtime(runtime)
        _blob_cache[id(runtime)] = store
    return store


def adesso() -> str:
    return datetime.now(timezone.utc).isoformat()


def nuovo_id() -> str:
    return uuid.uuid4().hex[:12]


def senza_id(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if doc is None:
        return None
    doc = dict(doc)
    doc.pop("_id", None)
    return doc


async def tutti(collezione: str, filtro: Optional[Dict[str, Any]] = None, ordina: Optional[str] = None) -> List[Dict[str, Any]]:
    cursor = db()[collezione].find(filtro or {})
    if ordina:
        cursor = cursor.sort(ordina, 1)
    return [senza_id(d) for d in await cursor.to_list(None)]


async def uno(collezione: str, filtro: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return senza_id(await db()[collezione].find_one(filtro))


async def prossimo_id_intero(collezione: str, minimo: int) -> int:
    ids = [int(d.get("id") or 0) for d in await db()[collezione].find({}, {"id": 1}).to_list(None)]
    return (max(ids) + 1) if ids else minimo


async def inserisci(collezione: str, doc: Dict[str, Any]) -> Dict[str, Any]:
    stored = dict(doc)
    stored["_id"] = str(stored.get("id"))
    await db()[collezione].insert_one(stored)
    return senza_id(stored)


async def aggiorna(collezione: str, filtro: Dict[str, Any], valori: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    result = await db()[collezione].update_one(filtro, {"$set": valori})
    if result.matched_count == 0:
        return None
    return await uno(collezione, filtro)


async def elimina(collezione: str, filtro: Dict[str, Any]) -> int:
    result = await db()[collezione].delete_many(filtro)
    return int(result.deleted_count)


# ------------------------------------------------------------------ immagini

def id_immagine(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()[:24]


async def salva_immagine(content: bytes, filename: str, content_type: str) -> Dict[str, Any]:
    """Salva i byte nell'archivio binari (deduplicato per contenuto) e la
    scheda in ``menu_immagini``. Ricaricare lo stesso file non duplica nulla."""
    immagine_id = id_immagine(content)
    esistente = await uno(COLL_IMMAGINI, {"id": immagine_id})
    if esistente:
        return esistente
    dati = base64.b64encode(content).decode("ascii")
    key = blob_key(dati)
    await blobs().put(key, dati)
    doc = {
        "id": immagine_id,
        "filename": filename,
        "content_type": content_type,
        "size": len(content),
        "blob_key": key,
        "url": PERCORSO_IMMAGINI + immagine_id,
        "uploaded_at": adesso(),
    }
    return await inserisci(COLL_IMMAGINI, doc)


async def leggi_immagine(immagine_id: str) -> Optional[Dict[str, Any]]:
    doc = await uno(COLL_IMMAGINI, {"id": immagine_id})
    if not doc:
        return None
    dati = await blobs().get(doc["blob_key"])
    if dati is None:
        return None
    return {"content": base64.b64decode(dati), "content_type": doc.get("content_type") or "application/octet-stream", "filename": doc.get("filename")}


async def elimina_immagine(immagine_id: str) -> bool:
    doc = await uno(COLL_IMMAGINI, {"id": immagine_id})
    if not doc:
        return False
    await elimina(COLL_IMMAGINI, {"id": immagine_id})
    await blobs().delete([doc["blob_key"]])
    return True


# ------------------------------------------------------------------ backup e stato

async def stato_dati() -> Dict[str, Any]:
    conteggi = {c: await db()[c].count_documents({}) for c in COLLEZIONI_BACKUP + [COLL_MAGAZZINO_BAR]}
    immagini = await tutti(COLL_IMMAGINI)
    return {"collezioni": conteggi, "immagini": {"count": len(immagini), "bytes": sum(int(i.get("size") or 0) for i in immagini)}}


async def esporta_backup() -> Dict[str, Any]:
    """Tutto il menu in un solo JSON, immagini comprese (base64): un file da
    scaricare e conservare, nessun archivio sul disco effimero di Render."""
    dati = {c: await tutti(c) for c in COLLEZIONI_BACKUP}
    immagini: Dict[str, str] = {}
    for doc in dati.get(COLL_IMMAGINI, []):
        key = doc.get("blob_key")
        if key and key not in immagini:
            contenuto = await blobs().get(key)
            if contenuto is not None:
                immagini[key] = contenuto
    return {
        "formato": FORMATO_BACKUP,
        "esportato_il": adesso(),
        "collezioni": dati,
        "blob_immagini": immagini,
    }


async def ripristina_backup(payload: Dict[str, Any]) -> Dict[str, int]:
    """Sostituisce le collezioni del menu con quelle del backup (il magazzino
    bar di Lotti non e' toccato). Le immagini rientrano nell'archivio binari
    con la stessa chiave a contenuto: quelle identiche non si duplicano."""
    collezioni = payload.get("collezioni") or {}
    esito: Dict[str, int] = {}
    for key, contenuto in (payload.get("blob_immagini") or {}).items():
        if isinstance(contenuto, str) and key == blob_key(contenuto):
            await blobs().put(key, contenuto)
    for nome in COLLEZIONI_BACKUP:
        docs = collezioni.get(nome)
        if not isinstance(docs, list):
            continue
        await elimina(nome, {})
        for doc in docs:
            if isinstance(doc, dict) and doc.get("id") is not None:
                await inserisci(nome, doc)
        esito[nome] = len(docs)
    return esito
