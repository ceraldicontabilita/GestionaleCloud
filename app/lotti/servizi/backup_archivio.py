"""Dove vivono i backup di Lotti: su Supabase, non nel disco del servizio.

Fino al 26/09/2026 il backup notturno scriveva in ``/tmp`` del container
Render, che sparisce a ogni deploy o riavvio: la pagina Backup mostrava file
che dopo il merge successivo non esistevano più, e un ripristino non aveva da
dove ripartire.

Il file compresso si spezza in parti da ``PARTE_BYTES`` e ogni parte va in
``gestionale.blobs`` (l'archivio binario già esistente, RPC protette dalla
chiave runtime; nessuna tabella nuova, nessun bucket pubblico). La chiave di
una parte porta il nome del backup e la sua impronta SHA-256. Il **manifesto**
(impronta del file intero, parti, conteggi per collezione) si salva due volte:
come blob ``lotti-backup-manifest:<nome>`` — sopravvive anche se l'archivio di
Lotti va perso — e nella collezione ``backup_registro``, che la pagina legge
e che backup e ripristino **non** toccano.

Un backup vale solo se, dopo l'upload, ogni parte riletta dall'archivio ha la
stessa impronta: ``verificato=True``. Altrimenti le parti si tolgono e il
backup è un errore, non un file in elenco.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.blob_store import BlobStore, blob_store_per_runtime

logger = logging.getLogger(__name__)

PARTE_BYTES = 3 * 1024 * 1024
PREFISSO_PARTE = "lotti-backup:"
PREFISSO_MANIFESTO = "lotti-backup-manifest:"
REGISTRO = "backup_registro"
MAX_BACKUPS = 7


class BackupNonPersistente(RuntimeError):
    """L'archivio persistente non è disponibile o il dato riletto non combacia."""


def archivio() -> BlobStore:
    from app.database import Database

    return blob_store_per_runtime(Database.db)


def _sha256_file(percorso: str) -> str:
    h = hashlib.sha256()
    with open(percorso, "rb") as fh:
        for blocco in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(blocco)
    return h.hexdigest()


async def salva(nome: str, percorso: str, riepilogo: Dict[str, Any], *,
                store: Optional[BlobStore] = None, richiedi_persistenza: bool = True) -> Dict[str, Any]:
    """Carica il file in parti, rilegge ogni parte e restituisce il manifesto verificato."""
    store = store or archivio()
    if richiedi_persistenza and not store.persistent:
        raise BackupNonPersistente("archivio Supabase non disponibile: il backup non sopravviverebbe")
    parti: List[Dict[str, Any]] = []
    caricate: List[str] = []
    try:
        with open(percorso, "rb") as fh:
            indice = 0
            for blocco in iter(lambda: fh.read(PARTE_BYTES), b""):
                impronta = hashlib.sha256(blocco).hexdigest()
                chiave = f"{PREFISSO_PARTE}{nome}:{indice:04d}:sha256:{impronta}"
                testo = base64.b64encode(blocco).decode("ascii")
                await store.put(chiave, testo)
                caricate.append(chiave)
                riletto = await store.get(chiave)
                if riletto is None or hashlib.sha256(base64.b64decode(riletto)).hexdigest() != impronta:
                    raise BackupNonPersistente(f"parte {indice} riletta diversa dall'originale")
                parti.append({"chiave": chiave, "sha256": impronta, "bytes": len(blocco)})
                indice += 1
        manifesto = {
            "nome": nome,
            "sha256": _sha256_file(percorso),
            "bytes": os.path.getsize(percorso),
            "parti": parti,
            "verificato": True,
            "verificato_at": datetime.now(timezone.utc).isoformat(),
            **riepilogo,
        }
        chiave_manifesto = PREFISSO_MANIFESTO + nome
        await store.put(chiave_manifesto, base64.b64encode(
            json.dumps(manifesto, ensure_ascii=False).encode("utf-8")).decode("ascii"))
        caricate.append(chiave_manifesto)
        return manifesto
    except Exception:
        if caricate:
            try:
                await store.delete(caricate)
            except Exception as exc:  # noqa: BLE001 - si segnala, l'errore vero è sopra
                logger.error("[backup] parti di %s non rimosse dopo l'errore: %s %s",
                             nome, type(exc).__name__, exc)
        raise


async def ricomponi(manifesto: Dict[str, Any], destinazione: str, *,
                    store: Optional[BlobStore] = None) -> str:
    """Riscrive il file da parti verificate; solleva se una parte manca o è diversa."""
    store = store or archivio()
    h = hashlib.sha256()
    with open(destinazione, "wb") as out:
        for parte in manifesto.get("parti") or []:
            testo = await store.get(parte["chiave"])
            if testo is None:
                raise BackupNonPersistente(f"parte mancante: {parte['chiave']}")
            dati = base64.b64decode(testo)
            if hashlib.sha256(dati).hexdigest() != parte["sha256"]:
                raise BackupNonPersistente(f"parte alterata: {parte['chiave']}")
            h.update(dati)
            out.write(dati)
    if h.hexdigest() != manifesto.get("sha256"):
        raise BackupNonPersistente("il file ricomposto non ha l'impronta del manifesto")
    return destinazione


async def elimina(manifesto: Dict[str, Any], *, store: Optional[BlobStore] = None) -> int:
    """Toglie parti e manifesto di un backup (per chiave, mai con filtro)."""
    store = store or archivio()
    chiavi = [p["chiave"] for p in manifesto.get("parti") or []]
    chiavi.append(PREFISSO_MANIFESTO + manifesto["nome"])
    return await store.delete(chiavi)
