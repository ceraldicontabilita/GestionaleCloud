"""Cartella unica «DATI SOCIETA CERALDI»: l'unico ingresso Drive dei documenti.

Decisione del titolare (25/09/2026): tutto cio' che entra nel gestionale passa
da una sola cartella con tre sottocartelle, e il gestionale legge gli
originali **solo** da li'.

    DATI SOCIETA CERALDI/
        DA ELABORARE   ← si mette qui qualunque documento, di qualunque tipo
        ELABORATE      ← gli originali registrati (archivio piatto: tipo,
                          anno, fornitore stanno nel database)
        ERRORI         ← cio' che non si e' potuto registrare, col motivo

Il giro non ha un motore suo: ogni file passa dallo **stesso smistatore di
Documenti > Import** (``upload_documento_automatico`` →
``detect_document_type``), che riconosce il tipo dal contenuto e chiama il
motore esistente (fatture, corrispettivi, F24, quietanze, cedolini, estratti
conto, verbali, bonifici...). Ognuno di quei motori fa gia' la propria
deduplica sui dati.

Niente doppioni fra gli originali: prima di smistare, un file con la stessa
impronta Drive (md5) di un originale gia' in ELABORATE si confronta **byte per
byte**; se e' identico va nel **Cestino** (mai eliminazione permanente,
decisione del 23/09) e il registro dice di chi e' copia. Stesso md5 ma byte
diversi non e' un doppione.

Il registro ``drive_cartella_unica`` tiene una riga per originale
(``id`` = drive_file_id): SHA-256, tipo riconosciuto, esito e i riferimenti
restituiti dal motore. «Vedi documento» apre un originale solo se questo
registro lo conosce in ELABORATE.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

REGISTRO = "drive_cartella_unica"
CHIAVE_STATO = "drive_cartella_unica_last_sync"
INBOX, ARCHIVIO, ERRORI = "DA ELABORARE", "ELABORATE", "ERRORI"
# Copie esatte che il Cestino non accetta: un file di proprieta' del titolare
# puo' cestinarlo solo lui (Drive risponde 403 al service account). Restano
# qui, fuori dall'archivio, finche' il titolare non svuota la cartella.
DOPPIONI = "DOPPIONI"
CARTELLA_MIME = "application/vnd.google-apps.folder"
# Chiavi del risultato dello smistatore che identificano il record creato.
_CHIAVI_RIFERIMENTO = (
    "invoice_id", "fattura_id", "corrispettivo_id", "f24_id", "quietanza_id",
    "cedolino_id", "doc_id", "bonifico_transfer_id", "verbale_id", "movimento_id",
    "prima_nota_cassa_id", "prima_nota_banca_id",
)

_lock = asyncio.Lock()


def radice() -> Optional[str]:
    return os.getenv("GOOGLE_DRIVE_DATI_FOLDER_ID", "").strip() or None


def attivo() -> bool:
    return bool(radice())


def _batch() -> int:
    try:
        return max(1, min(int(os.getenv("DRIVE_CARTELLA_UNICA_BATCH", "25")), 200))
    except ValueError:
        return 25


def _service():
    # La credenziale si prova sulla radice della cartella unica, non sulla
    # cartella di un canale: sparita la vecchia cartella fatture, il loader
    # delle fatture falliva e fermava lo smistatore di tutto il resto.
    from app.services.drive_credential_probe import load_credentials_for_folder

    creds, errore = load_credentials_for_folder(radice())
    if creds is None:
        raise RuntimeError(f"credenziali Drive non disponibili: {errore}")
    from googleapiclient.discovery import build

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _cartelle(service, root: str) -> Dict[str, str]:
    from app.services.drive_invoice_ingest import _get_or_create_folder

    return {nome: _get_or_create_folder(service, root, nome) for nome in (INBOX, ARCHIVIO, ERRORI, DOPPIONI)}


def _elenca(service, parent_id: str, campi: str, limite: Optional[int] = None) -> List[Dict[str, Any]]:
    """Tutti i file (non cartelle) di una cartella, paginando fino in fondo."""
    trovati: List[Dict[str, Any]] = []
    token = None
    while True:
        risposta = service.files().list(
            q=f"'{parent_id}' in parents and trashed = false and mimeType != '{CARTELLA_MIME}'",
            fields=f"nextPageToken, files({campi})", pageSize=1000 if limite is None else min(limite, 1000),
            orderBy="createdTime", pageToken=token,
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        trovati.extend(risposta.get("files", []))
        token = risposta.get("nextPageToken")
        if not token or (limite is not None and len(trovati) >= limite):
            return trovati[:limite] if limite is not None else trovati


def _sposta(service, file_id: str, da: str, a: str, motivo: Optional[str] = None) -> None:
    corpo = {"description": f"Gestionale: {motivo}"[:1000]} if motivo else None
    service.files().update(
        fileId=file_id, addParents=a, removeParents=da, body=corpo,
        fields="id, parents", supportsAllDrives=True,
    ).execute()


def _cestina(service, file_id: str, copia_di: str) -> bool:
    """Cestino (mai eliminazione). Falso se Drive non lo consente (403)."""
    try:
        service.files().update(
            fileId=file_id, supportsAllDrives=True, fields="id, trashed",
            body={"trashed": True, "description": f"Gestionale: copia identica di {copia_di}"},
        ).execute()
        return True
    except Exception as exc:
        if getattr(getattr(exc, "resp", None), "status", None) == 403:
            return False
        raise


class _FileCaricato:
    """Lo stesso oggetto che riceve l'upload di Documenti > Import."""

    def __init__(self, nome: str, contenuto: bytes, source_context: Dict[str, Any]):
        self.filename = nome
        self.file = io.BytesIO(contenuto)
        self.source_context = source_context
        self._contenuto = contenuto

    async def read(self) -> bytes:
        return self._contenuto


async def _smista(nome: str, contenuto: bytes, contesto: Dict[str, Any]) -> Dict[str, Any]:
    from fastapi import HTTPException

    from app.routers.documenti import detect_document_type, upload_documento_automatico

    # Un tipo non riconosciuto resta su Drive in ERRORI: lo smistatore lo
    # copierebbe in base64 dentro documents_inbox, una seconda copia
    # dell'originale che la cartella unica esiste per evitare.
    if detect_document_type(nome, contenuto) == "auto":
        return {"success": False, "tipo_rilevato": "non_riconosciuto"}
    try:
        return await upload_documento_automatico(file=_FileCaricato(nome, contenuto, contesto))
    except HTTPException as exc:
        return {"success": False, "message": str(exc.detail), "http_status": exc.status_code}


def esito_del_risultato(risultato: Dict[str, Any]) -> tuple[str, str]:
    """(cartella di destinazione, motivo). Registrato o gia' presente → archivio."""
    if risultato.get("tipo_rilevato") == "non_riconosciuto":
        return ERRORI, "tipo di documento non riconosciuto"
    if risultato.get("success") or risultato.get("duplicate"):
        return ARCHIVIO, ""
    return ERRORI, str(risultato.get("message") or risultato.get("error") or "registrazione non riuscita")[:500]


async def _registra(db, file_id: str, **campi) -> None:
    campi["aggiornato_il"] = datetime.now(timezone.utc).isoformat()
    await db[REGISTRO].update_one(
        {"id": file_id}, {"$set": {"id": file_id, "drive_file_id": file_id, **campi}}, upsert=True,
    )


async def giro(db) -> Dict[str, Any]:
    """Un giro sulla cartella DA ELABORARE: al piu' ``DRIVE_CARTELLA_UNICA_BATCH`` file."""
    if not attivo():
        return {"saltato": "GOOGLE_DRIVE_DATI_FOLDER_ID non impostata"}
    if _lock.locked():
        return {"saltato": "giro_in_corso"}
    async with _lock:
        return await _giro(db)


async def _giro(db) -> Dict[str, Any]:
    from app.services.drive_download import scarica_bytes

    iniziato = datetime.now(timezone.utc).isoformat()
    esito: Dict[str, Any] = {"letti": 0, "elaborati": 0, "errori": 0, "doppioni_cestinati": 0,
                             "dettagli": [], "iniziato_at": iniziato}
    try:
        service = await asyncio.to_thread(_service)
        cartelle = await asyncio.to_thread(_cartelle, service, radice())
        in_coda = await asyncio.to_thread(
            _elenca, service, cartelle[INBOX], "id, name, md5Checksum, size, mimeType", _batch())
        archivio = await asyncio.to_thread(_elenca, service, cartelle[ARCHIVIO], "id, md5Checksum")
    except Exception as exc:
        esito["errore"] = f"{type(exc).__name__}: {exc}"
        logger.warning("[cartella-unica] giro non avviato: %s", esito["errore"])
        await _salva_stato(db, esito)
        return esito

    per_md5: Dict[str, List[str]] = {}
    for f in archivio:
        if f.get("md5Checksum"):
            per_md5.setdefault(f["md5Checksum"], []).append(f["id"])

    for f in in_coda:
        esito["letti"] += 1
        fid, nome = f["id"], f.get("name") or f["id"]
        try:
            contenuto = await asyncio.to_thread(scarica_bytes, service, fid)
            sha256 = hashlib.sha256(contenuto).hexdigest()
            copia_di = None
            for candidato in per_md5.get(f.get("md5Checksum") or "", []):
                if await asyncio.to_thread(scarica_bytes, service, candidato) == contenuto:
                    copia_di = candidato
                    break
            if copia_di:
                cartella = "CESTINO"
                if not await asyncio.to_thread(_cestina, service, fid, copia_di):
                    cartella = DOPPIONI
                    await asyncio.to_thread(_sposta, service, fid, cartelle[INBOX], cartelle[DOPPIONI],
                                            f"copia identica di {copia_di}")
                await _registra(db, fid, nome=nome, sha256=sha256, esito="doppione_cestinato",
                                cartella=cartella, duplicato_di=copia_di)
                esito["doppioni_cestinati"] += 1
                esito["dettagli"].append({"file": nome, "esito": "doppione", "copia_di": copia_di,
                                          "cartella": cartella})
                continue

            contesto = {"channel": "drive_cartella_unica", "drive_file_id": fid,
                        "drive_parent_id": cartelle[ARCHIVIO], "source_sha256": sha256}
            risultato = await _smista(nome, contenuto, contesto)
            destinazione, motivo = esito_del_risultato(risultato)
            await asyncio.to_thread(_sposta, service, fid, cartelle[INBOX], cartelle[destinazione], motivo or None)
            riferimenti = {k: risultato[k] for k in _CHIAVI_RIFERIMENTO if risultato.get(k)}
            await _registra(
                db, fid, nome=nome, sha256=sha256, md5=f.get("md5Checksum"),
                tipo=risultato.get("tipo_rilevato"), cartella=destinazione,
                esito="elaborato" if destinazione == ARCHIVIO else "errore",
                gia_presente=bool(risultato.get("duplicate")), motivo=motivo or None,
                riferimenti=riferimenti,
            )
            if destinazione == ARCHIVIO:
                esito["elaborati"] += 1
                if f.get("md5Checksum"):
                    per_md5.setdefault(f["md5Checksum"], []).append(fid)
            else:
                esito["errori"] += 1
            esito["dettagli"].append({"file": nome, "tipo": risultato.get("tipo_rilevato"),
                                      "esito": destinazione, "motivo": motivo or None})
        except Exception as exc:
            motivo = f"{type(exc).__name__}: {exc}"[:500]
            logger.warning("[cartella-unica] %s non elaborato: %s", nome, motivo)
            esito["errori"] += 1
            esito["dettagli"].append({"file": nome, "esito": ERRORI, "motivo": motivo})
            try:
                await asyncio.to_thread(_sposta, service, fid, cartelle[INBOX], cartelle[ERRORI], motivo)
                await _registra(db, fid, nome=nome, cartella=ERRORI, esito="errore", motivo=motivo)
            except Exception as exc2:
                logger.warning("[cartella-unica] %s non spostato in ERRORI: %s: %s",
                               nome, type(exc2).__name__, exc2)
    esito["dettagli"] = esito["dettagli"][:100]
    await _salva_stato(db, esito)
    return esito


async def _salva_stato(db, esito: Dict[str, Any]) -> None:
    ora = datetime.now(timezone.utc).isoformat()
    try:
        await db["sistema_stato"].update_one(
            {"chiave": CHIAVE_STATO},
            {"$set": {"chiave": CHIAVE_STATO, "valore": ora, "updated_at": ora,
                      "last_error": esito.get("errore"), "last_result": esito}},
            upsert=True,
        )
    except Exception as exc:
        logger.warning("[cartella-unica] stato non salvato: %s: %s", type(exc).__name__, exc)


async def originale(db, drive_file_id: Optional[str] = None,
                    sha256: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Il documento da aprire, solo se e' un originale della cartella unica.

    Si cerca per id Drive oppure per SHA-256 del contenuto (l'impronta che i
    motori conservano come ``source_sha256``): mai per nome.
    """
    if drive_file_id:
        filtro = {"id": drive_file_id, "cartella": ARCHIVIO}
    elif sha256:
        filtro = {"sha256": sha256.strip().lower(), "cartella": ARCHIVIO}
    else:
        return None
    riga = await db[REGISTRO].find_one(filtro, {"_id": 0})
    if not riga:
        return None
    drive_file_id = riga["id"]
    from app.services.drive_download import scarica_bytes

    service = await asyncio.to_thread(_service)
    try:
        meta = await asyncio.to_thread(
            lambda: service.files().get(fileId=drive_file_id, fields="name, mimeType, trashed",
                                        supportsAllDrives=True).execute())
    except Exception as exc:
        if getattr(getattr(exc, "resp", None), "status", None) != 404:
            raise
        meta = {"trashed": True}
    if meta.get("trashed"):
        # Un protocollo non dimentica: l'originale sparito da Drive resta nel
        # registro come «rimosso», con la data, e non si apre piu'.
        await _registra(db, drive_file_id, cartella="RIMOSSO", esito="rimosso",
                        rimosso_il=datetime.now(timezone.utc).isoformat())
        return None
    contenuto = await asyncio.to_thread(scarica_bytes, service, drive_file_id)
    return {"nome": meta.get("name") or riga.get("nome"), "mime": meta.get("mimeType"),
            "contenuto": contenuto}
