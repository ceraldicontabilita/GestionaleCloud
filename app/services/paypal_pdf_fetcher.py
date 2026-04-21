"""
Scarica PDF giustificativi transazioni PayPal:
- PagoPA via Gmail (ricevuta da noreply-checkout@ricevute.pagopa.it o noreply_paytech@mooney.it)
- Commerciali: genera PDF sintetico da dati API
"""
import imaplib
import email as email_lib
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.config import settings

logger = logging.getLogger(__name__)
UPLOAD_DIR = "/app/uploads/paypal_ricevute"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _connect():
    user = settings.GMAIL_EMAIL or settings.IMAP_USER
    pwd = settings.GMAIL_APP_PASSWORD or settings.IMAP_PASSWORD
    conn = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    conn.login(user, pwd)
    return conn


async def fetch_ricevuta_pagopa(
    db: AsyncIOMotorDatabase, transaction_id: str, importo: float, data_iso: str
) -> Optional[Dict[str, Any]]:
    """Cerca su Gmail la ricevuta PagoPA corrispondente alla transazione PayPal."""
    try:
        data_dt = datetime.fromisoformat(data_iso.replace("Z", "+00:00"))
    except Exception:
        return None
    after = (data_dt - timedelta(days=2)).strftime("%Y/%m/%d")
    before = (data_dt + timedelta(days=3)).strftime("%Y/%m/%d")

    importo_str = f"{importo:.2f}".replace(".", ",")

    conn = _connect()
    try:
        conn.select("INBOX")
        query = (
            f'(X-GM-RAW "from:(noreply-checkout@ricevute.pagopa.it OR '
            f'noreply_paytech@mooney.it OR partenopay@ext.comune.napoli.it) '
            f'after:{after} before:{before}")'
        )
        status, data = conn.search(None, query)
        if status != "OK" or not data or not data[0]:
            return None

        for num in data[0].split():
            _, msg_data = conn.fetch(num, "(RFC822)")
            msg = email_lib.message_from_bytes(msg_data[0][1])
            from app.services._email_utils import extract_best_body
            body_txt = extract_best_body(msg)
            pdf_attach = None
            for part in msg.walk():
                if part.get_content_type() == "application/pdf":
                    pdf_attach = part
                    break

            if importo_str not in body_txt:
                continue

            parsed = _parse_pagopa_body(body_txt)
            pdf_path = os.path.join(UPLOAD_DIR, f"pagopa_{transaction_id}.pdf")
            if pdf_attach:
                with open(pdf_path, "wb") as f:
                    f.write(pdf_attach.get_payload(decode=True))
            else:
                _genera_pdf_da_testo(body_txt, pdf_path, "Ricevuta PagoPA")

            await db["paypal_transactions"].update_one(
                {"transaction_id": transaction_id},
                {"$set": {
                    "pdf_ricevuta_path": pdf_path,
                    "ricevuta_dati": parsed,
                    "ricevuta_scaricata_at": datetime.utcnow().isoformat(),
                }}
            )
            return {"pdf_path": pdf_path, "transaction_id": transaction_id, **parsed}
    finally:
        try:
            conn.logout()
        except Exception:
            pass
    return None


def _parse_pagopa_body(body: str) -> Dict[str, Any]:
    """Parser multi-formato email PagoPA: pagopa.it, mooney.it, PartenoPay."""
    # Delega al parser condiviso in verbali_pagamento_finder
    from app.services.verbali_pagamento_finder import _parse_pagopa_body as _unified
    return _unified(body)


def _genera_pdf_da_testo(testo: str, path: str, titolo: str):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import cm
    c = canvas.Canvas(path, pagesize=A4)
    _, h = A4
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2*cm, h-2*cm, titolo)
    c.setFont("Helvetica", 9)
    y = h - 3*cm
    for line in testo.split("\n"):
        if y < 2*cm:
            c.showPage()
            y = h - 2*cm
        c.drawString(2*cm, y, line[:100])
        y -= 0.4*cm
    c.save()


async def genera_pdf_transazione_paypal(
    db: AsyncIOMotorDatabase, transaction_id: str
) -> Optional[str]:
    tx = await db["paypal_transactions"].find_one({"transaction_id": transaction_id})
    if not tx:
        return None
    pdf_path = os.path.join(UPLOAD_DIR, f"paypal_{transaction_id}.pdf")

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import cm
    c = canvas.Canvas(pdf_path, pagesize=A4)
    _, h = A4
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2*cm, h-2*cm, "Ricevuta Transazione PayPal")
    c.setFont("Helvetica", 10)
    y = h - 3.5*cm
    campi = [
        ("Transaction ID", tx.get("transaction_id")),
        ("Data", (tx.get("initiation_date", "") or "")[:19]),
        ("Importo", f"€ {tx.get('importo', 0):.2f}"),
        ("Beneficiario (PayPal Account)", tx.get("paypal_account_id", "")),
        ("Invoice ID fornitore", tx.get("invoice_id_fornitore", "")),
        ("Codice custom", tx.get("custom_field", "")),
        ("Oggetto", tx.get("transaction_subject", "")),
        ("Note", tx.get("transaction_note", "")),
        ("Strumento", f"{tx.get('instrument_type','')} / {tx.get('instrument_sub_type','')}"),
    ]
    for label, val in campi:
        if not val:
            continue
        c.setFont("Helvetica-Bold", 10)
        c.drawString(2*cm, y, f"{label}:")
        c.setFont("Helvetica", 10)
        val_str = str(val)
        if len(val_str) > 70:
            c.drawString(7*cm, y, val_str[:70])
            y -= 0.5*cm
            c.drawString(7*cm, y, val_str[70:140])
        else:
            c.drawString(7*cm, y, val_str)
        y -= 0.7*cm
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(2*cm, 1.5*cm, f"Generato da gestionale2 il {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    c.save()
    await db["paypal_transactions"].update_one(
        {"transaction_id": transaction_id},
        {"$set": {"pdf_generato_path": pdf_path}}
    )
    return pdf_path
