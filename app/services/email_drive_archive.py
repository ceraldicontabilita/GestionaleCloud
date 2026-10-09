"""Copia non distruttiva degli allegati email rilevanti su Drive.

Le copie vanno in ``ELABORATE`` della cartella unica «DATI SOCIETA CERALDI»
(``drive_cartella_unica``), accanto agli originali gia' registrati: il
documento e' gia' entrato dal canale email, quindi non passa da ``DA
ELABORARE`` (lo smistatore lo registrerebbe una seconda volta). Le cartelle
per sezione (F24, Cedolini, Verbali...) non esistono piu'.
"""

from __future__ import annotations

import base64
import hashlib
import io
import logging
import mimetypes
from datetime import datetime, timezone
from typing import Any


logger = logging.getLogger(__name__)


_ROUTES: dict[str, tuple[str, str]] = {
    "f24": ("f24", "F24"),
    "quietanza": ("quietanze", "Quietanze F24"),
    "busta_paga": ("cedolini", "Cedolini"),
    "cedolino": ("cedolini", "Cedolini"),
    "cartella_esattoriale": ("cartelle_esattoriali", "Cartelle esattoriali"),
    "avviso_bonario": ("avvisi_bonari", "Avvisi bonari"),
    "verbale": ("verbali", "Verbali"),
    "dichiarazione_iva": ("dichiarazioni_iva", "Dichiarazioni IVA"),
    "estratto_conto": ("estratti_conto", "Estratti conto"),
    "bonifico": ("bonifici_dipendenti", "Bonifici"),
    "fattura": ("fatture", "Fatture"),
    "fattura_xml": ("fatture", "Fatture"),
    "fattura_estera_pdf": ("fatture", "Fatture estere"),
    "pagopa": ("pagopa", "PagoPA"),
    "contributi_inps": ("inps", "INPS"),
    "inps": ("inps", "INPS"),
    "inail": ("inail", "INAIL"),
    "certificazione_unica": ("certificazioni_uniche", "Certificazioni uniche"),
    "paypal": ("paypal", "PayPal"),
    "satispay": ("satispay", "Satispay"),
    "bolletta_energia": ("utenze_energia", "Bollette energia"),
    "partenopay": ("partenopay", "PARTENOPAY"),
    "scheda_tecnica": ("schede_tecniche", "Schede tecniche"),
}


def route_for_document_type(tipo: str) -> tuple[str, str] | None:
    return _ROUTES.get(str(tipo or "").strip().lower())


def _decode_content(doc: dict[str, Any]) -> bytes:
    content = doc.get("content")
    if isinstance(content, bytes):
        return content
    if isinstance(content, str):
        return content.encode("utf-8")
    encoded = doc.get("pdf_data")
    if encoded:
        return base64.b64decode(encoded)
    return b""


def _drive_service():
    # Credenziale provata sulla cartella unica, come ogni servizio Drive
    # generico: la cartella cedolini su cui la provava non esiste piu'.
    from app.services.drive_cartella_unica import _service
    try:
        return _service()
    except RuntimeError as exc:
        logger.warning("Archivio email Drive non disponibile: %s: %s", type(exc).__name__, exc)
        return None


def _escape_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _already_archived(
    service, parent_id: str, filename: str, digest: str, content: bytes,
) -> dict[str, Any] | None:
    # Prima l'impronta forte, indipendente dal nome: due copie byte-identiche
    # devono riusare lo stesso originale Drive e lo stesso documento logico.
    by_sha = service.files().list(
        q=(f"'{parent_id}' in parents and trashed = false and "
           f"appProperties has {{ key='gestionale_sha256' and value='{_escape_query(digest)}' }}"),
        fields="files(id, name, appProperties, md5Checksum)", pageSize=20, supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    if by_sha.get("files"):
        return by_sha["files"][0]
    result = service.files().list(
        q=f"name = '{_escape_query(filename)}' and '{parent_id}' in parents and trashed = false",
        fields="files(id, name, appProperties, md5Checksum)", pageSize=20, supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    # I service account non dispongono sempre di quota propria. In quel caso il
    # titolare puo' depositare l'originale in ELABORATE dal proprio Drive: lo
    # riconosciamo soltanto se nome, MD5 Drive e SHA-256 dei byte riletti
    # coincidono. Il solo nome non e' mai prova d'identita'.
    content_md5 = hashlib.md5(content, usedforsecurity=False).hexdigest()
    for item in result.get("files", []):
        props = item.get("appProperties") or {}
        if props.get("gestionale_sha256") == digest:
            return item
        if item.get("md5Checksum") != content_md5:
            continue
        try:
            originale = service.files().get_media(fileId=item["id"]).execute()
        except Exception as exc:  # il candidato non verificabile non si riusa
            logger.warning("Originale Drive %s non verificabile: %s", item.get("id"), type(exc).__name__)
            continue
        if hashlib.sha256(originale).hexdigest() != digest:
            continue
        try:
            aggiornato = service.files().update(
                fileId=item["id"],
                body={"appProperties": {**props, "gestionale_sha256": digest,
                                        "gestionale_source": "caricato_titolare"}},
                fields="id,name,appProperties,md5Checksum", supportsAllDrives=True,
            ).execute()
            return aggiornato or item
        except Exception as exc:
            # La rilettura byte-per-byte basta per riusare l'originale; i
            # metadati sono un'ottimizzazione, non una scorciatoia d'identita'.
            logger.warning("Metadati originali Drive %s non aggiornati: %s",
                           item.get("id"), type(exc).__name__)
            return item
    return None


def archive_document_copy(doc: dict[str, Any], tipo: str) -> dict[str, Any]:
    """Archivia una copia; non elimina e non sposta mai il documento nell'app."""
    route = route_for_document_type(tipo)
    if route is None:
        return {"status": "ignored", "reason": "tipo_non_rilevante"}
    area, _label = route
    return archive_binary_copy(
        _decode_content(doc),
        str(doc.get("filename") or f"documento-{doc.get('id', 'email')}.pdf").strip(),
        source=str(doc.get("source") or "email"),
        area=area,
    )


def archive_binary_copy(
    content: bytes,
    filename: str,
    *,
    source: str = "gestionale",
    area: str = "documenti",
) -> dict[str, Any]:
    """Salva e verifica un originale binario nella cartella unica Drive.

    E' il percorso comune usato anche dal runtime Drive-only: un upload senza
    id, MD5 o rilettura identica non e' considerato riuscito.
    """
    from app.services import drive_cartella_unica as cu

    root_id = cu.radice()
    if not root_id:
        return {"status": "not_configured", "area": area}
    if not content:
        return {"status": "error", "area": area, "reason": "contenuto_mancante"}
    service = _drive_service()
    if service is None:
        return {"status": "not_configured", "area": area}
    folder_id = cu._cartella(service, root_id, cu.ARCHIVIO)

    filename = str(filename or "documento.pdf").strip()
    digest = hashlib.sha256(content).hexdigest()
    content_md5 = hashlib.md5(content, usedforsecurity=False).hexdigest()
    existing = _already_archived(service, folder_id, filename, digest, content)
    if existing:
        return {"status": "duplicate", "area": area, "drive_file_id": existing.get("id"),
                "sha256": digest, "md5": content_md5, "bytes": len(content),
                "archived_at": datetime.now(timezone.utc).isoformat()}

    from googleapiclient.http import MediaIoBaseUpload
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type, resumable=False)
    try:
        created = service.files().create(
            body={
                "name": filename,
                "parents": [folder_id],
                "appProperties": {"gestionale_sha256": digest,
                                  "gestionale_source": str(source or "gestionale")[:40]},
            },
            media_body=media,
            fields="id,md5Checksum",
            supportsAllDrives=True,
        ).execute()
    except Exception as exc:
        status_code = getattr(getattr(exc, "resp", None), "status", None)
        message = str(exc).lower()
        if status_code == 403 and "storage quota" in message:
            return {"status": "blocked_owner_auth", "area": area,
                    "reason": "service_account_storage_quota"}
        if status_code == 403:
            return {"status": "blocked_owner_auth", "area": area,
                    "reason": "drive_permission_denied"}
        raise
    drive_id = created.get("id")
    drive_md5 = created.get("md5Checksum")
    if not drive_id or drive_md5 != content_md5:
        return {"status": "error", "area": area, "reason": "verifica_md5_fallita"}
    try:
        originale = service.files().get_media(fileId=drive_id).execute()
    except Exception as exc:
        logger.warning("Originale Drive %s non rileggibile: %s", drive_id, type(exc).__name__)
        return {"status": "error", "area": area, "reason": "rilettura_fallita"}
    if hashlib.sha256(originale).hexdigest() != digest:
        return {"status": "error", "area": area, "reason": "verifica_sha256_fallita"}
    return {"status": "archived", "area": area, "drive_file_id": drive_id,
            "sha256": digest, "md5": content_md5, "bytes": len(content),
            "archived_at": datetime.now(timezone.utc).isoformat()}
