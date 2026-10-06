"""Gli originali degli estratti conto, per rivederli e riscaricarli.

L'import dei movimenti bancari leggeva il file (CSV, Excel, PDF) e ne teneva
solo il nome sui movimenti: l'originale caricato a mano non si poteva piu'
riavere. Qui ogni file importato si conserva una volta sola, per impronta
SHA-256, in ``gestionale.blobs``; il registro ``estratti_conto_originali`` dice
nome, fonte e data. Gli estratti Nexi hanno gia' il loro PDF in
``estratto_conto_nexi``, e quelli passati dalla cartella unica restano su Drive:
l'elenco li mostra tutti insieme, ognuno col suo modo di riaverlo.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

COLL = "estratti_conto_originali"
PREFISSO_BLOB = "estratto-originale:"

_MIME = {
    ".pdf": "application/pdf", ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel", ".xml": "application/xml",
}


def mime_per_nome(nome: str) -> str:
    nome = (nome or "").lower()
    for estensione, mime in _MIME.items():
        if nome.endswith(estensione):
            return mime
    return "application/octet-stream"


def _archivio():
    from app.database import Database
    from app.services.blob_store import blob_store_per_runtime

    return blob_store_per_runtime(Database.db)


async def conserva_originale(
    db, contenuto: bytes, nome: str, *, fonte: str, drive_file_id: Optional[str] = None,
    righe: Optional[int] = None,
) -> Optional[str]:
    """Conserva il file una volta sola; ritorna il suo id (l'impronta SHA-256).

    Un guasto qui non ferma l'import dei movimenti: resta scritto nel log.
    """
    if not contenuto:
        return None
    impronta = hashlib.sha256(contenuto).hexdigest()
    ora = datetime.now(timezone.utc).isoformat()
    try:
        esistente = await db[COLL].find_one({"id": impronta}, {"_id": 0, "id": 1})
        if esistente:
            await db[COLL].update_one({"id": impronta}, {"$set": {"ultimo_caricamento": ora}})
            return impronta
        documento: Dict[str, Any] = {
            "id": impronta, "nome": nome, "fonte": fonte, "dimensione": len(contenuto),
            "mime": mime_per_nome(nome), "caricato_il": ora, "ultimo_caricamento": ora,
            "drive_file_id": drive_file_id, "righe": righe,
        }
        archivio = _archivio()
        if getattr(archivio, "persistent", False):
            if documento["mime"] == "application/pdf":
                if not drive_file_id:
                    from app.services.email_drive_archive import archive_binary_copy

                    esito = await asyncio.to_thread(
                        archive_binary_copy, contenuto, nome,
                        source="estratti_conto", area=COLL,
                    )
                    if esito.get("status") not in {"archived", "duplicate"}:
                        raise RuntimeError("Estratto PDF non verificato su Drive")
                    drive_file_id = esito["drive_file_id"]
                    documento["drive_md5"] = esito.get("md5")
                documento["drive_file_id"] = drive_file_id
                documento["drive_archive_status"] = "verified"
            else:
                chiave = PREFISSO_BLOB + impronta
                await archivio.put(chiave, base64.b64encode(contenuto).decode("ascii"))
                documento["blob_key"] = chiave
        else:
            # Senza Supabase (test, sviluppo) il contenuto resta nel registro.
            documento["contenuto_b64"] = base64.b64encode(contenuto).decode("ascii")
        await db[COLL].insert_one(documento)
        return impronta
    except Exception as exc:  # noqa: BLE001 - i movimenti restano importati
        logger.warning("Originale dell'estratto %s non conservato: %s: %s",
                       nome, type(exc).__name__, exc)
        return None


async def elenco(db, limite: int = 500) -> List[Dict[str, Any]]:
    """Tutti gli estratti riscaricabili, il piu' recente per primo."""
    voci: List[Dict[str, Any]] = []
    for doc in await db[COLL].find(
        {}, {"_id": 0, "id": 1, "nome": 1, "fonte": 1, "caricato_il": 1, "dimensione": 1, "righe": 1},
    ).to_list(limite):
        voci.append({**doc, "tipo": "banca", "data": doc.get("caricato_il")})
    for doc in await db["estratto_conto_nexi"].find(
        {}, {"_id": 0, "id": 1, "filename": 1, "metadata": 1, "import_date": 1},
    ).to_list(limite):
        meta = doc.get("metadata") or {}
        voci.append({
            "id": doc.get("id"), "nome": doc.get("filename"), "tipo": "nexi",
            "fonte": "Nexi", "data": meta.get("data_estratto_iso") or doc.get("import_date"),
            "periodo": meta.get("data_estratto"), "totale": meta.get("totale_addebito"),
        })
    voci.sort(key=lambda v: str(v.get("data") or ""), reverse=True)
    return voci


async def contenuto(db, voce_id: str) -> Optional[Tuple[bytes, str, str]]:
    """(byte, nome, tipo) dell'originale, o None se non c'e'."""
    doc = await db[COLL].find_one({"id": voce_id}, {"_id": 0})
    if doc:
        if doc.get("drive_file_id"):
            from app.services.drive_download import scarica_originale

            originale = await scarica_originale(str(doc["drive_file_id"]), md5=doc.get("drive_md5"))
            if originale:
                nome = doc.get("nome") or f"estratto_{voce_id[:12]}"
                return originale, nome, doc.get("mime") or mime_per_nome(nome)
        dati = doc.get("contenuto_b64")
        if not dati and doc.get("blob_key"):
            dati = await _archivio().get(doc["blob_key"])
        if not dati:
            return None
        nome = doc.get("nome") or f"estratto_{voce_id[:12]}"
        return base64.b64decode(dati), nome, doc.get("mime") or mime_per_nome(nome)
    nexi = await db["estratto_conto_nexi"].find_one({"id": voce_id}, {"_id": 0})
    if nexi and nexi.get("drive_file_id"):
        from app.services.drive_download import scarica_originale

        originale = await scarica_originale(str(nexi["drive_file_id"]), md5=nexi.get("drive_md5"))
        if originale:
            return originale, nexi.get("filename") or "estratto_nexi.pdf", "application/pdf"
    if nexi and nexi.get("pdf_data"):
        nome = nexi.get("filename") or "estratto_nexi.pdf"
        return base64.b64decode(nexi["pdf_data"]), nome, "application/pdf"
    return None
