"""
Scanner Gmail per verbali CdS. Legge SOLO da imap.gmail.com, NON da PEC Aruba.
Le PEC inoltrate da Aruba Legalmail arrivano già su Gmail.

Trigger A del workflow bidirezionale:
email verbale ricevuta → scanner Gmail → crea/aggiorna verbali_noleggio.
"""
import imaplib
import email as email_lib
import re
import os
import uuid
import logging
import asyncio
import base64
import hashlib
from datetime import datetime, timezone, timedelta
from email.header import decode_header
from email.parser import BytesParser
from email.policy import default as default_policy
from typing import Dict, Any, List, Set
from app.services.sheets_document_store import SheetDatabase

from app.config import settings

logger = logging.getLogger(__name__)
UPLOAD_DIR = "/tmp/uploads/verbali_gmail"
os.makedirs(UPLOAD_DIR, exist_ok=True)

SUBJECT_KEYWORDS = [
    "sanzione amministrativa",
    "codice della strada",
    "notifica di atto amministrativo",
    "verbale di contestazione",
]


def _decode(s):
    if not s:
        return ""
    parts = []
    for p, enc in decode_header(s):
        if isinstance(p, bytes):
            try:
                parts.append(p.decode(enc or "utf-8", errors="replace"))
            except Exception:
                parts.append(p.decode("utf-8", errors="replace"))
        else:
            parts.append(p)
    return " ".join(parts)


def _normalize_filename(value: str) -> str:
    """Rimuove piegature MIME/a-capo senza alterare il nome del documento."""
    return re.sub(r"\s+", " ", _decode(value or "")).strip()


async def get_senders_whitelist(db: SheetDatabase) -> Set[str]:
    # Collezione canonica unica `mittenti_email` (con union legacy per
    # retro-compatibilità) tramite l'accessor condiviso (P2-2).
    try:
        from app.services.mittenti import senders_attendibili
        # Il valore selezionabile nella UI e' `verbale`; `verbale_cds` resta
        # accettato per le configurazioni storiche.
        senders = await senders_attendibili(db, tipo_documento="verbale", canale="gmail")
        senders |= await senders_attendibili(db, tipo_documento="verbale_cds", canale="gmail")
        if senders:
            return senders
    except Exception:
        logger.exception("Errore lettura mittenti attendibili verbali")
    # Lista vuota = zero download. Non si ricade su un trasportatore PEC
    # generico: la whitelist canonica e' la fonte di verita'.
    return set()


async def _gmail_credentials(db: SheetDatabase):
    """Usa prima le credenziali salvate dall'Admin, poi quelle d'ambiente."""
    user = password = None
    try:
        from app.utils.crypto import decrypt_credential
        cfg = await db["settings"].find_one({"chiave": "gmail"}, {"_id": 0})
        if cfg and cfg.get("imap_user") and cfg.get("gmail_app_password"):
            user = cfg["imap_user"]
            password = decrypt_credential(cfg["gmail_app_password"])
    except Exception:
        logger.exception("Credenziali Gmail Admin non leggibili")
    return (
        user or settings.GMAIL_EMAIL or settings.IMAP_USER
        or settings.GMAIL_ACCOUNT_AMMINISTRATIVO,
        password or settings.GMAIL_APP_PASSWORD or settings.IMAP_PASSWORD
        or settings.GMAIL_APP_PASSWORD_AMMINISTRATIVO,
    )


async def scan_gmail_verbali(db: SheetDatabase, days_back: int = 7, mark_as_read: bool = False) -> Dict[str, Any]:
    stats = {
        "email_scansionate": 0, "email_match": 0,
        "verbali_nuovi": 0, "verbali_aggiornati": 0, "errori": [],
        "documenti_nuovi": 0, "documenti_duplicati": 0,
        "drive_archiviati": 0, "drive_duplicati": 0,
    }
    email_user, email_password = await _gmail_credentials(db)
    if not email_user or not email_password:
        stats["errori"].append("Gmail non configurato")
        return stats

    senders = await get_senders_whitelist(db)
    if not senders:
        stats["errori"].append("Nessun mittente attendibile per i verbali")
        return stats
    try:
        conn = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        conn.login(email_user, email_password)
        conn.select("INBOX")
        from_clause = " OR ".join(f"from:{s}" for s in senders)
        after = (datetime.now() - timedelta(days=days_back)).strftime("%Y/%m/%d")
        # Il mittente attendibile e' obbligatorio. Prima il ramo OR sui subject
        # permetteva a qualunque mittente di entrare se scriveva "verbale".
        raw_query = f"({from_clause}) has:attachment after:{after}"
        status, data = conn.search(None, "X-GM-RAW", f'"{raw_query}"')
        if status != "OK" or not data or not data[0]:
            try:
                conn.logout()
            except Exception:
                pass
            return stats
        for num in data[0].split():
            stats["email_scansionate"] += 1
            try:
                _, mdata = conn.fetch(num, "(RFC822)")
                msg = email_lib.message_from_bytes(mdata[0][1])
                parsed = _parse_email_verbale(msg, senders)
                if not parsed:
                    continue
                stats["email_match"] += 1
                parsed["allegati"] = _save_attachments(msg, parsed.get("upec_id") or parsed.get("numero_verbale"))
                # Se c'è un "avviso" PDF parsane i dettagli
                for a in parsed["allegati"]:
                    if "avviso" in a["filename"].lower():
                        pdf_data = _parse_avviso_digitale_pdf(a["path"])
                        for k, v in pdf_data.items():
                            if v and not parsed.get(k):
                                parsed[k] = v
                        break
                op = await _upsert_verbale(db, parsed)
                if op == "new":
                    stats["verbali_nuovi"] += 1
                    # Dopo insert cerca se c'è già la fattura associata
                    try:
                        from app.services.verbali_fattura_linker import cerca_fattura_per_verbale
                        if parsed.get("numero_verbale"):
                            mf = await cerca_fattura_per_verbale(db, parsed["numero_verbale"])
                            if mf:
                                await _collega_fattura(db, parsed["numero_verbale"], mf)
                    except Exception:
                        logger.exception("Errore ricerca fattura per verbale nuovo")
                elif op == "updated":
                    stats["verbali_aggiornati"] += 1
                for allegato in parsed["allegati"]:
                    ingest = await _ingest_pdf_attachment(db, parsed, allegato)
                    if ingest["documento"] == "nuovo":
                        stats["documenti_nuovi"] += 1
                    else:
                        stats["documenti_duplicati"] += 1
                    if ingest["drive"] == "archived":
                        stats["drive_archiviati"] += 1
                    elif ingest["drive"] == "duplicate":
                        stats["drive_duplicati"] += 1
                if mark_as_read:
                    conn.store(num, "+FLAGS", "\\Seen")
            except Exception as e:
                logger.exception("Errore processing email %s", num)
                stats["errori"].append(str(e))
        conn.logout()
    except Exception as e:
        logger.exception("Errore scan Gmail verbali")
        stats["errori"].append(str(e))
    return stats


def _parse_email_verbale(msg, senders_whitelist: Set[str]):
    sender = (msg.get("From") or "").lower()
    subject = _decode(msg.get("Subject") or "")
    addresses = {
        value.lower()
        for value in re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", sender, re.IGNORECASE)
    }
    if not addresses.intersection({s.lower() for s in senders_whitelist}):
        return None
    try:
        data_ric = email_lib.utils.parsedate_to_datetime(msg.get("Date", ""))
    except Exception:
        data_ric = datetime.now(timezone.utc)
    body = _extract_text_body(msg)
    m_atto = re.search(r'Atto\s+(\d+)\s+del\s+(\d{2}/\d{2}/\d{4})', subject)
    m_upec = re.search(r'\[upec(\d+)\]', subject)
    m_verb_body = re.search(
        r'Numero verbale[:\s]+([A-Z]\d{10,12})\s*del\s*(\d{2}/\d{2}/\d{4})',
        body, re.IGNORECASE
    )
    m_reg = re.search(r'Numero registro Atto[:\s]+(\d+)', body, re.IGNORECASE)
    m_piva = re.search(r'P\.?I\.?\s+(\d{11})', body, re.IGNORECASE)
    m_orig = re.search(r'inviato da\s*"([^"]+@[^"]+)"', body, re.IGNORECASE)
    return {
        "numero_verbale": m_verb_body.group(1) if m_verb_body else None,
        "data_violazione": (m_verb_body.group(2) if m_verb_body
                            else (m_atto.group(2) if m_atto else None)),
        "numero_atto": m_reg.group(1) if m_reg else (m_atto.group(1) if m_atto else None),
        "upec_id": m_upec.group(1) if m_upec else None,
        "piva_destinatario": m_piva.group(1) if m_piva else None,
        "data_ricezione_notifica": data_ric.isoformat(),
        "email_subject": subject,
        "email_sender_visibile": sender,
        "email_sender_originale": m_orig.group(1) if m_orig else None,
        "source": "gmail_scanner",
    }


def _extract_text_body(msg) -> str:
    from app.services._email_utils import extract_best_body
    return extract_best_body(msg)


def _save_attachments(msg, key) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    prefix = key or uuid.uuid4().hex[:8]

    def _walk(m):
        for part in m.walk():
            ctype = part.get_content_type()
            filename = _normalize_filename(part.get_filename() or "")
            if ctype == "application/pdf" and filename:
                safe = re.sub(r'[^A-Za-z0-9._-]', '_', filename)
                path = os.path.join(UPLOAD_DIR, f"{prefix}_{safe}")
                try:
                    content = part.get_payload(decode=True)
                    with open(path, "wb") as f:
                        f.write(content)
                    out.append({"filename": filename, "path": path,
                                "size": os.path.getsize(path),
                                "file_hash": hashlib.md5(content).hexdigest()})
                except Exception as e:
                    logger.warning("save %s: %s", filename, e)
            elif ctype == "message/rfc822" or (filename and filename.lower().endswith(".eml")):
                try:
                    raw = part.get_payload(decode=True)
                    if raw:
                        inner = BytesParser(policy=default_policy).parsebytes(raw)
                        _walk(inner)
                except Exception:
                    pass

    _walk(msg)
    return out


async def _ingest_pdf_attachment(db, parsed: Dict[str, Any], allegato: Dict[str, Any]) -> Dict[str, str]:
    """Conserva il PDF nell'app, lo classifica e ne archivia una copia Drive."""
    with open(allegato["path"], "rb") as handle:
        content = handle.read()
    digest = allegato.get("file_hash") or hashlib.md5(content).hexdigest()
    existing = await db["documents_inbox"].find_one(
        {"file_hash": digest},
        {"_id": 0, "id": 1, "drive_archive_status": 1},
    )
    now = datetime.now(timezone.utc).isoformat()
    if existing:
        document_id = existing["id"]
        document_status = "duplicato"
    else:
        document_id = str(uuid.uuid4())
        document = {
            "id": document_id,
            "filename": allegato["filename"],
            "file_hash": digest,
            "pdf_data": base64.b64encode(content).decode("ascii"),
            "tipo_documento": "verbale",
            "categoria": "verbale",
            "category": "verbale",
            "email_from": parsed.get("email_sender_visibile"),
            "email_sender_originale": parsed.get("email_sender_originale"),
            "email_subject": parsed.get("email_subject"),
            "email_date": parsed.get("data_ricezione_notifica"),
            "fonte": "gmail_verbali",
            "source": "gmail_verbali",
            "stato": "importato",
            "status": "importato",
            "processed": False,
            "created_at": now,
        }
        await db["documents_inbox"].insert_one(dict(document))
        document_status = "nuovo"

    from app.services.verbali_document_import import process_verbale_document
    await process_verbale_document(
        db,
        document_id=document_id,
        content=content,
        filename=allegato["filename"],
        source="email_verbale",
    )

    # Un documento gia' archiviato non deve essere ritrasmesso a ogni nuova
    # scansione Gmail. Questo protegge anche le copie caricate con OAuth/UI
    # quando l'account di servizio non dispone di quota Drive propria.
    previous_drive_status = str((existing or {}).get("drive_archive_status") or "")
    if previous_drive_status in {"archived", "duplicate", "archived_manual_oauth"}:
        await db["documents_inbox"].update_one(
            {"id": document_id},
            {"$set": {"updated_at": now}},
        )
        return {"documento": document_status, "drive": previous_drive_status}

    from app.services.email_drive_archive import archive_document_copy
    archive_doc = {
        "id": document_id,
        "filename": allegato["filename"],
        "file_hash": digest,
        "pdf_data": base64.b64encode(content).decode("ascii"),
    }
    try:
        drive = await asyncio.to_thread(archive_document_copy, archive_doc, "verbale")
    except Exception as exc:
        logger.exception("Archivio Drive verbale fallito: %s", allegato["filename"])
        drive = {"status": "error", "reason": str(exc)}
    await db["documents_inbox"].update_one(
        {"id": document_id},
        {"$set": {
            "drive_archive_status": drive.get("status"),
            "drive_archive_area": drive.get("area"),
            "drive_archived_at": drive.get("archived_at"),
            "drive_archive_reason": drive.get("reason"),
            "updated_at": now,
        }},
    )
    return {"documento": document_status, "drive": str(drive.get("status") or "error")}


def _parse_avviso_digitale_pdf(pdf_path: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception as e:
        logger.warning("PDF %s: %s", pdf_path, e)
        return out
    m = re.search(r'\b([03]\d{17})\b', text)
    if m:
        out["iuv"] = m.group(1)
    m = re.search(r'\b([A-Z]{2}\d{3}[A-Z]{2})\b', text, re.IGNORECASE)
    if m:
        out["targa"] = m.group(1).upper()
    for pat in [r'(?:Importo|Totale|Da pagare)[:\s]*€?\s*([\d.]+,\d{2})',
                r'€\s*([\d.]+,\d{2})']:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                out["importo"] = float(m.group(1).replace(".", "").replace(",", "."))
                break
            except ValueError:
                continue
    m = re.search(r'(?:art|articolo)\.?\s*(\d+)\s*(?:comma\s*(\d+))?', text, re.IGNORECASE)
    if m:
        out["articolo_cds"] = f"Art. {m.group(1)}" + (f" c.{m.group(2)}" if m.group(2) else "")
    m = re.search(r'(?:Ente creditore|Creditore)[:\s]*([^\n]{5,80})', text)
    if m:
        out["ente_creditore"] = m.group(1).strip()
    m = re.search(
        r'(?:Descrizione violazione|Tipo violazione)[:\s]*([^\n]{10,200})',
        text, re.IGNORECASE
    )
    if m:
        out["descrizione_violazione"] = m.group(1).strip()
    return out


async def _upsert_verbale(db, parsed) -> str:
    try:
        data_ric = datetime.fromisoformat(parsed["data_ricezione_notifica"])
    except Exception:
        data_ric = datetime.now(timezone.utc)
    data_scad_30 = (data_ric + timedelta(days=5)).date().isoformat()
    data_scad_60 = (data_ric + timedelta(days=60)).date().isoformat()
    payload = {**parsed,
               "data_scadenza_riduzione_30": data_scad_30,
               "data_scadenza_ordinaria_60": data_scad_60,
               "stato": "notificato",
               "updated_at": datetime.now(timezone.utc).isoformat()}
    payload = {k: v for k, v in payload.items() if v not in (None, "", [])}

    q = None
    if parsed.get("numero_verbale"):
        q = {"numero_verbale": parsed["numero_verbale"]}
    elif parsed.get("upec_id"):
        q = {"upec_id": parsed["upec_id"]}
    if not q:
        # Il PDF classificato puo' ancora ricavare il numero con OCR/vision.
        # Non creiamo una riga anonima che diventerebbe un duplicato quando
        # il documento genera poi l'entita' corretta.
        return "ignored"

    existing = await db["verbali_noleggio"].find_one(q)
    if existing:
        fields = {k: v for k, v in payload.items()
                  if not existing.get(k) and v not in (None, "", 0, [], {})}
        if fields:
            fields["updated_at"] = payload["updated_at"]
            await db["verbali_noleggio"].update_one(
                {"_id": existing["_id"]}, {"$set": fields}
            )
            return "updated"
        return "unchanged"
    payload["id"] = str(uuid.uuid4())
    payload["creato_il"] = datetime.now(timezone.utc).isoformat()
    await db["verbali_noleggio"].insert_one(payload)
    return "new"


async def _collega_fattura(db, numero_verbale: str, fm: Dict[str, Any]) -> None:
    await db["verbali_noleggio"].update_one(
        {"numero_verbale": numero_verbale},
        {"$set": {
            "fattura_associata_id": fm["fattura_id"],
            "fattura_associata_numero": fm["numero_fattura"],
            "fattura_associata_data": fm["data_fattura"],
            "fattura_associata_fornitore": fm["fornitore"],
            "fattura_associata_importo": fm["importo_fattura"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )
