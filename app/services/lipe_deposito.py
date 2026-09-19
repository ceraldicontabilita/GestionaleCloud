"""Le LIPE lette finiscono in una collezione sola, `lipe_periodi`.

Una riga per periodo (`YYYY-MM`), con i righi del quadro VP e la provenienza.
Il confronto col gestionale legge solo da qui: il PDF resta su Drive, non si
riparsa a ogni domanda.

**Un periodo che non quadra non entra.** `lipe_parser.quadra()` verifica
l'aritmetica del modulo; se non torna, la lettura non e' affidabile e la riga
viene contata fra gli scarti invece di diventare una fonte fiscale.

**Una LIPE piu' recente sostituisce la precedente sullo stesso periodo.** Una
comunicazione si puo' correggere e ritrasmettere: vince quella con il
protocollo piu' alto, e la precedente resta nello storico della riga.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.lipe_parser import parse_lipe

logger = logging.getLogger(__name__)

__all__ = [
    "COLL_LIPE",
    "protocollo_da_nome",
    "e_una_lipe",
    "deposita_lipe",
    "importa_lipe_archiviate",
]

COLL_LIPE = "lipe_periodi"
COLL_INBOX = "documents_inbox"

_NOME_LIPE = re.compile(r"lipe", re.IGNORECASE)
_PROTOCOLLO = re.compile(r"LIPE[_\- ]*(\d{4})[_\- ]*(\d+)", re.IGNORECASE)


def e_una_lipe(nome_file: Optional[str]) -> bool:
    return bool(nome_file) and bool(_NOME_LIPE.search(nome_file))


def protocollo_da_nome(nome_file: Optional[str]) -> Optional[int]:
    """Il numero di protocollo in `LIPE_2026_407141844.pdf`.

    Serve a decidere quale comunicazione vince su un periodo gia' presente:
    una ritrasmissione ha protocollo piu' alto.
    """
    trovato = _PROTOCOLLO.search(nome_file or "")
    return int(trovato.group(2)) if trovato else None


def _nome_documento(doc: Dict[str, Any]) -> str:
    """In archivio il nome del file sta sotto chiavi diverse a seconda della
    collezione: `documents_inbox` usa `filename`, altri `file_name`."""
    for chiave in ("filename", "file_name", "nome_file"):
        valore = doc.get(chiave)
        if valore:
            return str(valore)
    return ""


async def deposita_lipe(
    db, pdf_bytes: bytes, *, nome_file: str, origine: str,
    drive_file_id: Optional[str] = None, dry_run: bool = False,
) -> Dict[str, Any]:
    """Legge una LIPE e deposita i suoi periodi. Idempotente per periodo."""
    letto = parse_lipe(pdf_bytes)
    protocollo = protocollo_da_nome(nome_file)
    ora = datetime.now(timezone.utc).isoformat()

    depositati: List[str] = []
    scartati: List[Dict[str, Any]] = []
    ignorati: List[str] = []

    for periodo_letto in letto["periodi"]:
        periodo = periodo_letto.get("periodo")
        if not periodo:
            scartati.append({"pagina": periodo_letto.get("pagina"),
                             "motivo": "periodo non riconosciuto"})
            continue
        if not periodo_letto.get("quadratura_ok"):
            scartati.append({"periodo": periodo, "motivo": "l'aritmetica del modulo non torna"})
            continue

        esistente = await db[COLL_LIPE].find_one({"periodo": periodo}, {"_id": 0})
        if esistente:
            vecchio = esistente.get("protocollo")
            if protocollo is not None and vecchio is not None and protocollo < vecchio:
                ignorati.append(periodo)
                continue

        riga = {
            **{k: v for k, v in periodo_letto.items() if k != "pagina"},
            "periodo": periodo,
            "anno": letto.get("anno"),
            "protocollo": protocollo,
            "nome_file": nome_file,
            "drive_file_id": drive_file_id,
            "origine": origine,
            "aggiornato_at": ora,
        }
        if not dry_run:
            await db[COLL_LIPE].update_one(
                {"periodo": periodo}, {"$set": riga}, upsert=True,
            )
        depositati.append(periodo)

    return {
        "dry_run": dry_run,
        "nome_file": nome_file,
        "anno": letto.get("anno"),
        "protocollo": protocollo,
        "periodi_letti": letto["periodi_letti"],
        "depositati": depositati,
        "ignorati_perche_superati": ignorati,
        "scartati": scartati,
    }


async def importa_lipe_archiviate(db, *, dry_run: bool = True) -> Dict[str, Any]:
    """Rilegge le LIPE gia' inventariate e ne deposita i periodi.

    I PDF non stanno nel gestionale: `documents_inbox` ne conserva solo
    l'impronta e l'id Drive, quindi ognuno si riscarica al momento. Un solo
    prefetch dell'inventario, poi un download per file.
    """
    from app.services.drive_download import scarica_bytes
    from app.services.drive_fiscal_registry import build_drive_service

    candidati = []
    async for doc in db[COLL_INBOX].find({}, {"_id": 0}):
        nome = _nome_documento(doc)
        if e_una_lipe(nome) and doc.get("drive_file_id"):
            candidati.append((nome, str(doc["drive_file_id"])))

    # Le piu' recenti per ultime: cosi' una ritrasmissione sovrascrive.
    candidati.sort(key=lambda c: protocollo_da_nome(c[0]) or 0)

    esiti: List[Dict[str, Any]] = []
    errori: List[Dict[str, str]] = []
    service = None
    for nome, file_id in candidati:
        try:
            if service is None:
                service = build_drive_service()
            contenuto = scarica_bytes(service, file_id)
            esiti.append(await deposita_lipe(
                db, contenuto, nome_file=nome, origine="documents_inbox",
                drive_file_id=file_id, dry_run=dry_run,
            ))
        except Exception as exc:  # noqa: BLE001 — l'esito va riportato, non nascosto
            logger.exception("LIPE non leggibile: %s", nome)
            errori.append({"file": nome, "errore": str(exc)[:200]})

    depositati = sorted({p for e in esiti for p in e["depositati"]})
    return {
        "dry_run": dry_run,
        "lipe_trovate": len(candidati),
        "lipe_lette": len(esiti),
        "periodi_depositati": depositati,
        "periodi_scartati": [s for e in esiti for s in e["scartati"]],
        "errori": errori,
    }
