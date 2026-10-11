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

from typing import Any, Dict, Optional

from app.services.blob_store import BlobStore, blob_store_per_runtime

PARTE_BYTES = 3 * 1024 * 1024
PREFISSO_PARTE = "lotti-backup:"
PREFISSO_MANIFESTO = "lotti-backup-manifest:"
REGISTRO = "backup_registro"
MAX_BACKUPS = 7


from app.services.verified_backup_archive import (
    BackupNonPersistente, salva_file, ricomponi_file, elimina_file,
)


def archivio() -> BlobStore:
    from app.database import Database
    return blob_store_per_runtime(Database.db)


async def salva(nome: str, percorso: str, riepilogo: Dict[str, Any], *,
                store: Optional[BlobStore] = None, richiedi_persistenza: bool = True) -> Dict[str, Any]:
    return await salva_file(nome, percorso, riepilogo, store=store or archivio(),
                            namespace="lotti", part_bytes=PARTE_BYTES,
                            richiedi_persistenza=richiedi_persistenza)


async def ricomponi(manifesto: Dict[str, Any], destinazione: str, *,
                    store: Optional[BlobStore] = None) -> str:
    return await ricomponi_file(manifesto, destinazione, store=store or archivio())


async def elimina(manifesto: Dict[str, Any], *, store: Optional[BlobStore] = None) -> int:
    return await elimina_file(manifesto, store=store or archivio(), namespace="lotti")
