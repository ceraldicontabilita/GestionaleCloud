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
from datetime import datetime, timezone, timedelta
from email.header import decode_header
from email.parser import BytesParser
from email.policy import default as default_policy
from typing import Dict, Any, List, Set
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import settings

logger = logging.getLogger(__name__)
UPLOAD_DIR = "/tmp/uploads/verbali_gmail"
os.makedirs(UPLOAD_DIR, exist_ok=True)

SENDERS_VERBALI_DEFAULT: Set[str] = {
    "notifica.pl.napoli@pec.it",
    "posta-certificata@pec.aruba.it",
    "ufficiosanzioni@arval.it",
    "comando.pm@pec.comune.napoli.it",
    "prefettura.napoli@pec.interno.it",
}
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


async def get_senders_whitelist(db: AsyncIOMotorDatabase) -> Set[str]:
    try:
        cursor = db["mittenti_attendibili"].find({
            "tipo_documento": "verbale_cds",
            "attivo": True,
            "canale": "gmail",
        })
        senders = set()
        async for m in cursor:
            addr = (m.get("indirizzo_email") or "").lower()
            if addr:
                senders.add(addr)
        if senders:
            return senders
    except Exception:
        pass
    return SENDERS_VERBALI_DEFAULT


async def scan_gmail_verbali(db: AsyncIOMotorDatabase, days_back: int = 7, mark_as_read: bool = False) -> Dict[str, Any]:
    stats = {
        "email_scansionate": 0, "email_match": 0,
        "verbali_nuovi": 0, "verbali_aggiornati": 0, "errori": [],
    }
    if not settings.GMAIL_EMAIL and not settings.IMAP_USER:
        stats["errori"].append("Gmail non configurato")
        return stats

    senders = await get_senders_whitelist(db)
    try:
        conn = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        conn.login(settings.GMAIL_EMAIL or settings.IMAP_USER,
                   settings.GMAIL_APP_PASSWORD or settings.IMAP_PASSWORD)
        conn.select("INBOX")
        from_clause = " OR ".join(f"from:{s}" for s in senders)
        # Subject: Gmail X-GM-RAW usa parentesi per frasi, evitiamo doppi apici nested
        subj_clause = " OR ".join(f"subject:({k.replace(' ', '-')})" for k in SUBJECT_KEYWORDS[:3])
        after = (datetime.now() - timedelta(days=days_back)).strftime("%Y/%m/%d")
        q = f'(X-GM-RAW "({from_clause} OR ({subj_clause})) after:{after}")'
        status, data = conn.search(None, q)
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
    if not any(s in sender for s in senders_whitelist) \
       and not any(k in subject.lower() for k in SUBJECT_KEYWORDS):
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
            filename = _decode(part.get_filename() or "")
            if ctype == "application/pdf" and filename:
                safe = re.sub(r'[^A-Za-z0-9._-]', '_', filename)
                path = os.path.join(UPLOAD_DIR, f"{prefix}_{safe}")
                try:
                    with open(path, "wb") as f:
                        f.write(part.get_payload(decode=True))
                    out.append({"filename": filename, "path": path,
                                "size": os.path.getsize(path)})
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
               "updated_at": datetime.utcnow().isoformat()}
    payload = {k: v for k, v in payload.items() if v not in (None, "", [])}

    q = None
    if parsed.get("numero_verbale"):
        q = {"numero_verbale": parsed["numero_verbale"]}
    elif parsed.get("upec_id"):
        q = {"upec_id": parsed["upec_id"]}
    if q:
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
    payload["creato_il"] = datetime.utcnow().isoformat()
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
            "updated_at": datetime.utcnow().isoformat(),
        }}
    )
