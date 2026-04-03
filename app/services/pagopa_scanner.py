"""
Scanner PagoPA Quietanze Verbali

Scansiona la casella Gmail ceraldigroupsrl@gmail.com per le email di:
- partenopay@ext.comune.napoli.it      (Comune di Napoli / parcometri)
- noreply-checkout@ricevute.pagopa.it  (Ricevute pagamento PagoPA)
- notifica.pl.napoli@pec.it            (Polizia Locale Napoli)

Per ogni email:
1. Cerca numero verbale (pattern B\\d{10,11}) nel corpo e nell'oggetto
2. Se PDF allegato → lo salva come quietanza
3. Se nessun PDF → converte il corpo email in PDF con reportlab
4. Collega al verbale in DB → stato "quietanza_ricevuta"
"""

import imaplib
import email
import re
import base64
import uuid
import logging
import os
import io
from email.header import decode_header
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Mittenti PagoPA da monitorare
PAGOPA_SENDERS = [
    "partenopay@ext.comune.napoli.it",
    "noreply-checkout@ricevute.pagopa.it",
    "notifica.pl.napoli@pec.it",
]

# Pattern numero verbale (B + 10-12 cifre, oppure A + 8-12 cifre)
VERBALE_PATTERNS = [
    r'[Bb]\d{10,12}',          # B23123049750
    r'[Aa]\d{8,12}',           # A25111540620
    r'verbale[:\s#\-]+([A-Z0-9]{8,14})',  # "Verbale: XXXXX"
    r'n\.?\s*verbale[:\s]+([A-Z0-9]{8,14})',  # "N. Verbale: XXXXX"
    r'codice[:\s]+([A-Z]\d{8,12})',  # "Codice: BXXX"
]

IMAP_HOST = os.environ.get("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.environ.get("IMAP_PORT", "993"))
IMAP_USER = os.environ.get("IMAP_USER", os.environ.get("EMAIL_ADDRESS", "ceraldigroupsrl@gmail.com"))
IMAP_PASSWORD = os.environ.get("IMAP_PASSWORD", os.environ.get("EMAIL_PASSWORD", ""))


def decode_header_str(value: str) -> str:
    """Decodifica header email in stringa leggibile."""
    if not value:
        return ""
    try:
        parts = decode_header(value)
        result = ""
        for part, enc in parts:
            if isinstance(part, bytes):
                result += part.decode(enc or "utf-8", errors="ignore")
            else:
                result += str(part)
        return result.strip()
    except Exception:
        return str(value)


def extract_text_from_message(msg) -> str:
    """Estrae tutto il testo (plain + html stripped) da un messaggio email."""
    text_parts = []
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                continue
            if ct == "text/plain":
                try:
                    charset = part.get_content_charset() or "utf-8"
                    text_parts.append(part.get_payload(decode=True).decode(charset, errors="ignore"))
                except Exception:
                    pass
            elif ct == "text/html":
                try:
                    charset = part.get_content_charset() or "utf-8"
                    html = part.get_payload(decode=True).decode(charset, errors="ignore")
                    # Strip HTML tags basic
                    clean = re.sub(r'<[^>]+>', ' ', html)
                    clean = re.sub(r'\s+', ' ', clean)
                    text_parts.append(clean)
                except Exception:
                    pass
    else:
        try:
            charset = msg.get_content_charset() or "utf-8"
            text_parts.append(msg.get_payload(decode=True).decode(charset, errors="ignore"))
        except Exception:
            pass
    return " ".join(text_parts)


def extract_pdf_attachments(msg) -> List[Dict[str, Any]]:
    """Estrae tutti gli allegati PDF da un messaggio email."""
    pdfs = []
    if not msg.is_multipart():
        return pdfs
    for part in msg.walk():
        cd = str(part.get("Content-Disposition", ""))
        ct = part.get_content_type()
        filename = part.get_filename()
        if filename:
            filename = decode_header_str(filename)
        if filename and (".pdf" in filename.lower() or ct == "application/pdf"):
            try:
                data = part.get_payload(decode=True)
                if data:
                    pdfs.append({
                        "filename": filename,
                        "content_base64": base64.b64encode(data).decode("utf-8"),
                        "size": len(data),
                    })
            except Exception as e:
                logger.warning(f"Errore lettura allegato PDF {filename}: {e}")
    return pdfs


def corpo_email_to_pdf_base64(subject: str, mittente: str, body_text: str, data_email: str) -> str:
    """
    Converte il corpo email in PDF usando reportlab.
    Ritorna il PDF come stringa base64.
    """
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    # Header
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2 * cm, h - 2 * cm, "Ricevuta PagoPA / Quietanza Verbale")
    c.setFont("Helvetica", 9)
    c.drawString(2 * cm, h - 2.8 * cm, f"Da: {mittente}")
    c.drawString(2 * cm, h - 3.3 * cm, f"Oggetto: {subject[:80]}")
    c.drawString(2 * cm, h - 3.8 * cm, f"Data: {data_email}")
    c.line(2 * cm, h - 4.2 * cm, w - 2 * cm, h - 4.2 * cm)

    # Body text
    c.setFont("Helvetica", 8)
    y = h - 5 * cm
    max_chars = 110
    for line in body_text.split("\n"):
        # Spezza righe lunghe
        while len(line) > max_chars:
            c.drawString(2 * cm, y, line[:max_chars])
            line = line[max_chars:]
            y -= 0.45 * cm
            if y < 2 * cm:
                c.showPage()
                y = h - 2 * cm
                c.setFont("Helvetica", 8)
        if line.strip():
            c.drawString(2 * cm, y, line)
            y -= 0.45 * cm
        if y < 2 * cm:
            c.showPage()
            y = h - 2 * cm
            c.setFont("Helvetica", 8)

    c.save()
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def find_verbale_numbers(text: str) -> List[str]:
    """Trova tutti i numeri verbale nel testo."""
    found = set()
    for pattern in VERBALE_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            # Normalizza a uppercase e rimuovi spazi
            clean = m.strip().upper().replace(" ", "")
            if len(clean) >= 8:
                found.add(clean)
    return list(found)


async def scan_pagopa_email(db, days_back: int = 365) -> Dict[str, Any]:
    """
    Scansiona Gmail per email PagoPA.
    Cerca ricevute/quietanze dai 3 mittenti autorizzati.
    """
    risultato = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "email_analizzate": 0,
        "verbali_trovati": 0,
        "quietanze_salvate": 0,
        "verbali_aggiornati": 0,
        "pdf_generati_da_corpo": 0,
        "dettagli": [],
        "errori": [],
    }

    # Connessione IMAP
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(IMAP_USER, IMAP_PASSWORD)
    except Exception as e:
        risultato["errori"].append(f"Connessione IMAP fallita: {e}")
        risultato["success"] = False
        return risultato

    try:
        # Data da cui cercare
        since_date = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")

        for mittente in PAGOPA_SENDERS:
            try:
                mail.select("INBOX")
                # Cerca email da questo mittente
                status, data = mail.search(
                    None,
                    f'(FROM "{mittente}" SINCE "{since_date}")'
                )
                if status != "OK":
                    continue

                msg_ids = data[0].split()
                logger.info(f"[PagoPA] Mittente {mittente}: {len(msg_ids)} email trovate")

                for msg_id in msg_ids:
                    try:
                        status, msg_data = mail.fetch(msg_id, "(RFC822)")
                        if status != "OK":
                            continue

                        msg = email.message_from_bytes(msg_data[0][1])
                        subject = decode_header_str(msg.get("Subject", ""))
                        data_email = msg.get("Date", "")
                        risultato["email_analizzate"] += 1

                        # Estrai corpo testo
                        body_text = extract_text_from_message(msg)
                        full_text = f"{subject} {body_text}"

                        # Cerca numeri verbale
                        numeri_verbale = find_verbale_numbers(full_text)
                        if not numeri_verbale:
                            continue

                        risultato["verbali_trovati"] += len(numeri_verbale)

                        # Cerca PDF allegati
                        pdfs = extract_pdf_attachments(msg)
                        pdf_da_usare = None

                        if pdfs:
                            pdf_da_usare = pdfs[0]  # Usa il primo PDF
                        else:
                            # Converti corpo in PDF
                            try:
                                pdf_b64 = corpo_email_to_pdf_base64(
                                    subject, mittente, body_text, data_email
                                )
                                pdf_da_usare = {
                                    "filename": f"quietanza_pagopa_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                                    "content_base64": pdf_b64,
                                    "source": "corpo_email_convertito",
                                }
                                risultato["pdf_generati_da_corpo"] += 1
                            except Exception as e:
                                logger.error(f"Errore conversione corpo in PDF: {e}")

                        # Aggiorna ogni verbale trovato
                        for numero_verbale in numeri_verbale:
                            try:
                                await _aggiorna_verbale_con_quietanza(
                                    db, numero_verbale, mittente, subject,
                                    data_email, pdf_da_usare, body_text
                                )
                                risultato["verbali_aggiornati"] += 1
                                if pdf_da_usare:
                                    risultato["quietanze_salvate"] += 1
                                risultato["dettagli"].append({
                                    "verbale": numero_verbale,
                                    "mittente": mittente,
                                    "oggetto": subject[:60],
                                    "ha_pdf": bool(pdf_da_usare),
                                })
                            except Exception as e:
                                risultato["errori"].append(
                                    f"Errore verbale {numero_verbale}: {e}"
                                )

                    except Exception as e:
                        risultato["errori"].append(f"Errore msg {msg_id}: {e}")

            except Exception as e:
                risultato["errori"].append(f"Errore mittente {mittente}: {e}")

    finally:
        try:
            mail.logout()
        except Exception:
            pass

    # Cerca anche nelle cartelle "Posta inviata", "Spam" (alcune PEC arrivano in spam)
    risultato["success"] = True
    return risultato


async def _aggiorna_verbale_con_quietanza(
    db,
    numero_verbale: str,
    mittente: str,
    subject: str,
    data_email: str,
    pdf_info: Optional[Dict],
    body_text: str,
) -> None:
    """Aggiorna o crea un verbale nel DB con la quietanza PagoPA trovata."""

    # Cerca verbale esistente
    verbale = await db["verbali_noleggio"].find_one({"numero_verbale": numero_verbale})

    quietanza_doc = {
        "id": str(uuid.uuid4()),
        "verbale_numero": numero_verbale,
        "mittente_email": mittente,
        "oggetto_email": subject,
        "data_email": data_email,
        "corpo_testo": body_text[:2000],  # Max 2000 caratteri
        "source": "pagopa_scanner",
        "salvata_at": datetime.now(timezone.utc).isoformat(),
    }
    if pdf_info:
        quietanza_doc["pdf_filename"] = pdf_info.get("filename")
        quietanza_doc["pdf_base64"] = pdf_info.get("content_base64")
        quietanza_doc["pdf_source"] = pdf_info.get("source", "allegato_email")

    # Salva quietanza nella collection separata
    await db["quietanze_verbali"].update_one(
        {"verbale_numero": numero_verbale, "mittente_email": mittente},
        {"$set": quietanza_doc},
        upsert=True,
    )

    if verbale:
        # Aggiorna verbale esistente
        nuovo_stato = "riconciliato" if verbale.get("fattura_id") else "quietanza_ricevuta"
        update = {
            "quietanza_ricevuta": True,
            "quietanza_mittente": mittente,
            "quietanza_data": data_email,
            "stato": nuovo_stato,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if pdf_info:
            update["quietanza_pdf_filename"] = pdf_info.get("filename")
            # Salva solo base64 se non troppo grande
            if len(pdf_info.get("content_base64", "")) < 500_000:
                update["quietanza_pdf"] = pdf_info.get("content_base64")

        await db["verbali_noleggio"].update_one(
            {"numero_verbale": numero_verbale},
            {"$set": update},
        )
        logger.info(f"[PagoPA] Verbale {numero_verbale} aggiornato: {nuovo_stato}")
    else:
        # Crea nuovo verbale con lo stato quietanza
        new_verbale = {
            "id": str(uuid.uuid4()),
            "numero_verbale": numero_verbale,
            "stato": "quietanza_ricevuta",
            "quietanza_ricevuta": True,
            "quietanza_mittente": mittente,
            "quietanza_data": data_email,
            "source": "pagopa_scanner",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if pdf_info and len(pdf_info.get("content_base64", "")) < 500_000:
            new_verbale["quietanza_pdf"] = pdf_info.get("content_base64")
            new_verbale["quietanza_pdf_filename"] = pdf_info.get("filename")
        await db["verbali_noleggio"].insert_one(new_verbale)
        logger.info(f"[PagoPA] Nuovo verbale creato: {numero_verbale}")
