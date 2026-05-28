"""
Scanner Gmail filtrato per mittenti attendibili (non-fatture).

Regola CLAUDE.md (28/05/2026):
- Fatture XML/PDF -> SOLO upload manuale. Anche se trovate in email
  via whitelist, vanno messe in quarantena con alert, NON importate.
- Documenti NON-fattura -> importati automaticamente solo dai mittenti
  in `mittenti_attendibili` (whitelist), con categoria del mittente.

Il task viene eseguito dallo scheduler quando ENABLE_GMAIL_WHITELIST_SCAN=true.
Per la lista mittenti vedi: app/services/mittenti_attendibili.py
"""
from __future__ import annotations
import imaplib
import email as email_lib
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from email.header import decode_header
from typing import Any, Dict, List, Optional, Tuple

from app.services import mittenti_attendibili as mittenti_srv

logger = logging.getLogger(__name__)

# Collezione di quarantena per fatture trovate (non importate) in email
COLL_QUARANTENA = "fatture_in_quarantena_email"
# Collezione di destinazione per documenti non-fattura scaricati
COLL_DOC_INBOX = "documents_inbox"
# Collection alert
COLL_ALERTS = "alerts"


def _decodifica_header(raw_header: Optional[str]) -> str:
    if not raw_header:
        return ""
    try:
        parts = decode_header(raw_header)
        out = []
        for txt, enc in parts:
            if isinstance(txt, bytes):
                out.append(txt.decode(enc or "utf-8", errors="ignore"))
            else:
                out.append(txt)
        return "".join(out)
    except Exception:
        return str(raw_header)


def _estrai_mittente(msg: email_lib.message.Message) -> str:
    raw = _decodifica_header(msg.get("From", ""))
    # Estrae l'email tra <...> o ritorna l'intera stringa lowercased
    if "<" in raw and ">" in raw:
        return raw.split("<", 1)[1].split(">", 1)[0].strip().lower()
    return raw.strip().lower()


def _ora_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _genera_alert_fattura_in_email(
    db, mittente: str, filename: str, file_hash: str
) -> None:
    """Crea alert 'fattura trovata in email' (idempotente per hash)."""
    esistente = await db[COLL_ALERTS].find_one(
        {"codice": "FAT_TROVATA_IN_EMAIL", "entita_id": file_hash}
    )
    if esistente:
        return
    alert = {
        "id": f"al_{uuid.uuid4()}",
        "codice": "FAT_TROVATA_IN_EMAIL",
        "modulo": "fatture",
        "severita": "warning",
        "entita_id": file_hash,
        "entita_collection": COLL_QUARANTENA,
        "titolo": "Fattura trovata via email (non importata)",
        "dettaglio": (
            f"Allegato {filename} da {mittente} sembra una fattura XML/P7M. "
            "Per regola CLAUDE.md le fatture si importano SOLO via upload manuale. "
            "L'allegato e' stato messo in quarantena."
        ),
        "stato": "aperto",
        "created_at": _ora_utc(),
    }
    await db[COLL_ALERTS].insert_one(alert)


async def _salva_in_quarantena(
    db, mittente: str, filename: str, contenuto: bytes
) -> str:
    """Salva una fattura XML/P7M trovata via email in collezione quarantena."""
    file_hash = hashlib.sha256(contenuto).hexdigest()
    # Idempotenza per hash
    if await db[COLL_QUARANTENA].find_one({"file_hash": file_hash}):
        return file_hash
    await db[COLL_QUARANTENA].insert_one({
        "id": f"qf_{uuid.uuid4()}",
        "file_hash": file_hash,
        "filename": filename,
        "mittente": mittente,
        "dimensione_byte": len(contenuto),
        "stato": "in_quarantena",
        "motivo": "Fattura non importabile via email (regola: solo upload)",
        "created_at": _ora_utc(),
    })
    return file_hash


async def _salva_documento_inbox(
    db,
    mittente: str,
    filename: str,
    contenuto: bytes,
    mittente_info: Dict[str, Any],
) -> str:
    """Salva un documento NON-fattura nella inbox con metadati."""
    file_hash = hashlib.sha256(contenuto).hexdigest()
    if await db[COLL_DOC_INBOX].find_one({"file_hash": file_hash}):
        return file_hash
    await db[COLL_DOC_INBOX].insert_one({
        "id": f"doc_{uuid.uuid4()}",
        "file_hash": file_hash,
        "filename": filename,
        "mittente": mittente,
        "fonte": "gmail_auto",
        "categoria_auto": mittente_info.get("categoria_default"),
        "modulo_destinazione": mittente_info.get("modulo_destinazione"),
        "dimensione_byte": len(contenuto),
        "stato": "nuovo",
        "created_at": _ora_utc(),
    })
    return file_hash


async def processa_messaggio(
    db,
    msg: email_lib.message.Message,
) -> Tuple[int, int]:
    """Processa un singolo messaggio email. Restituisce (importati, in_quarantena)."""
    mittente = _estrai_mittente(msg)
    mittente_info = await mittenti_srv.trova_mittente(db, mittente)
    if not mittente_info:
        # Mittente NON in whitelist: ignorato
        return (0, 0)

    importati = 0
    in_quarantena = 0
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename_raw = part.get_filename()
        if not filename_raw:
            continue
        filename = _decodifica_header(filename_raw)
        try:
            payload = part.get_payload(decode=True)
        except Exception:
            continue
        if not payload:
            continue

        # REGOLA: se sembra una fattura -> QUARANTENA, niente import
        if mittenti_srv.e_fattura_xml(filename):
            file_hash = await _salva_in_quarantena(db, mittente, filename, payload)
            await _genera_alert_fattura_in_email(
                db, mittente, filename, file_hash
            )
            in_quarantena += 1
            continue

        # Documento non-fattura: salva in inbox con metadati
        await _salva_documento_inbox(
            db, mittente, filename, payload, mittente_info
        )
        importati += 1

    return (importati, in_quarantena)


async def scarica_da_gmail(db, host: str, user: str, password: str,
                           cartelle: Optional[List[str]] = None,
                           giorni_indietro: int = 7) -> Dict[str, int]:
    """Connette a Gmail IMAP e processa email dai mittenti in whitelist.

    Args:
        host:    indirizzo IMAP (es. "imap.gmail.com")
        user:    email account
        password: app password
        cartelle: cartelle IMAP da scansionare (default: ["INBOX"])
        giorni_indietro: finestra temporale per ridurre carico

    Returns:
        dict con: messaggi_visti, mittenti_match, documenti_importati,
                  fatture_in_quarantena, errori
    """
    cartelle = cartelle or ["INBOX"]
    stats = {
        "messaggi_visti": 0,
        "mittenti_match": 0,
        "documenti_importati": 0,
        "fatture_in_quarantena": 0,
        "errori": 0,
    }
    try:
        conn = imaplib.IMAP4_SSL(host)
        conn.login(user, password)
    except Exception as e:
        logger.error("[WHITELIST-SCAN] login IMAP fallito: %s", e)
        stats["errori"] += 1
        return stats

    try:
        for cartella in cartelle:
            try:
                conn.select(cartella)
            except Exception:
                continue
            criterio = "ALL"
            try:
                from datetime import timedelta
                data_da = (datetime.now() - timedelta(days=giorni_indietro)).strftime("%d-%b-%Y")
                criterio = f'(SINCE {data_da})'
            except Exception:
                pass
            try:
                _, msgnums = conn.search(None, criterio)
            except Exception:
                continue
            for num in (msgnums[0].split() if msgnums and msgnums[0] else []):
                stats["messaggi_visti"] += 1
                try:
                    _, data = conn.fetch(num, "(RFC822)")
                    if not data or not data[0]:
                        continue
                    msg = email_lib.message_from_bytes(data[0][1])
                except Exception:
                    stats["errori"] += 1
                    continue
                try:
                    imp, qua = await processa_messaggio(db, msg)
                    if imp > 0 or qua > 0:
                        stats["mittenti_match"] += 1
                    stats["documenti_importati"] += imp
                    stats["fatture_in_quarantena"] += qua
                except Exception as e:
                    logger.warning("[WHITELIST-SCAN] errore msg: %s", e)
                    stats["errori"] += 1
    finally:
        try:
            conn.logout()
        except Exception:
            pass

    logger.info("[WHITELIST-SCAN] stats: %s", stats)
    return stats
