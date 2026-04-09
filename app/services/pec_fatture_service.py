"""
PEC Fatture Service
====================
Scarica automaticamente le fatture XML dal SDI via PEC Aruba.
Mittente attendibile: @pec.fatturapa.it

Flusso:
  1. IMAP → INBOX PEC Aruba
  2. Filtra email da @pec.fatturapa.it
  3. Estrae allegati XML (o ZIP con XML dentro)
  4. Chiama parse_fattura_xml + upsert in DB
  5. Marca email come letta (flag \\Seen)

REGOLA ASSOLUTA: IMAP sempre in asyncio.to_thread()
"""
import asyncio
import imaplib
import email
import zipfile
import io
import logging
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional
from email.header import decode_header

logger = logging.getLogger(__name__)

# Mittenti SDI attendibili
SDI_SENDERS = [
    "@pec.fatturapa.it",
    "sdi@pec.fatturapa.it",
    "noreply@pec.fatturapa.it",
]


def _decode_str(s) -> str:
    if s is None:
        return ""
    parts = decode_header(s)
    result = []
    for part, enc in parts:
        if isinstance(part, bytes):
            result.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return " ".join(result)


def _is_sdi_sender(from_addr: str) -> bool:
    from_lower = from_addr.lower()
    return any(sdi in from_lower for sdi in SDI_SENDERS)


def _extract_xml_from_attachment(part) -> Optional[bytes]:
    """Estrae contenuto XML da allegato (diretto o dentro ZIP)."""
    filename = _decode_str(part.get_filename() or "")
    payload = part.get_payload(decode=True)
    if not payload:
        return None

    fname_lower = filename.lower()

    if fname_lower.endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                for name in zf.namelist():
                    if name.lower().endswith(".xml"):
                        return zf.read(name)
        except Exception as e:
            logger.warning(f"ZIP parse error: {e}")
        return None

    if fname_lower.endswith(".xml"):
        return payload

    if fname_lower.endswith(".p7m"):
        return payload

    return None


def _fetch_fatture_from_pec_sync(
    host: str,
    port: int,
    user: str,
    password: str,
    mark_seen: bool = True,
    only_unread: bool = True,
    since_date: str = None,
) -> List[Dict[str, Any]]:
    """
    Connessione IMAP sincrona (da chiamare in asyncio.to_thread).

    Args:
        only_unread: Se True cerca solo UNSEEN, se False cerca TUTTE le email
        since_date: Filtra email da questa data in poi (formato "01-Jan-2026")

    Ritorna lista di {filename, xml_bytes, subject, from, date, message_id}.
    """
    results = []

    mail = imaplib.IMAP4_SSL(host, port)
    mail.login(user, password)
    mail.select("INBOX")

    # Costruisci criteri di ricerca IMAP
    criteria = []
    if only_unread:
        criteria.append("UNSEEN")
    if since_date:
        criteria.append(f'SINCE "{since_date}"')

    if criteria:
        search_str = " ".join(criteria)
    else:
        search_str = "ALL"

    logger.info(f"PEC IMAP search: {search_str}")
    status, message_ids = mail.search(None, search_str)
    if status != "OK":
        logger.warning("IMAP search failed")
        mail.logout()
        return results

    ids = message_ids[0].split()
    logger.info(f"PEC: {len(ids)} email trovate con criteri [{search_str}]")

    for mid in ids:
        try:
            status, data = mail.fetch(mid, "(RFC822)")
            if status != "OK" or not data or data[0] is None:
                continue

            raw = data[0][1]
            msg = email.message_from_bytes(raw)

            from_addr = _decode_str(msg.get("From", ""))
            subject = _decode_str(msg.get("Subject", ""))
            date_str = msg.get("Date", "")
            message_id = msg.get("Message-ID", "")

            # Filtra per mittente SDI
            if not _is_sdi_sender(from_addr):
                continue

            logger.info(f"SDI email: {subject[:60]} | from: {from_addr}")

            # Estrai allegati XML
            xml_found = False
            for part in msg.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                if part.get("Content-Disposition") is None and part.get_filename() is None:
                    continue

                xml_bytes = _extract_xml_from_attachment(part)
                if xml_bytes:
                    filename = _decode_str(part.get_filename() or f"fattura_{mid.decode()}.xml")
                    results.append({
                        "filename": filename,
                        "xml_bytes": xml_bytes,
                        "subject": subject,
                        "from": from_addr,
                        "date": date_str,
                        "message_id": message_id,
                        "imap_id": mid,
                    })
                    xml_found = True
                    logger.info(f"  → XML estratto: {filename} ({len(xml_bytes)} bytes)")

            # Marca come letta solo se richiesto e abbiamo estratto XML
            if xml_found and mark_seen:
                mail.store(mid, "+FLAGS", "\\Seen")

        except Exception as e:
            logger.error(f"Errore processando email {mid}: {e}")

    mail.logout()
    return results


async def fetch_fatture_from_pec(
    host: str,
    port: int,
    user: str,
    password: str,
    mark_seen: bool = True,
    only_unread: bool = True,
    since_date: str = None,
) -> List[Dict[str, Any]]:
    """Versione async — wrappa la chiamata IMAP sincrona."""
    return await asyncio.to_thread(
        _fetch_fatture_from_pec_sync,
        host, port, user, password, mark_seen, only_unread, since_date
    )
