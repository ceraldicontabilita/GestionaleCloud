"""Invio email — punto unico di risoluzione delle credenziali.

Un solo sistema per tutte le email dell'app (presenze al commercialista,
notifiche richieste dal portale...): niente logica di invio duplicata in più router.

Il relay Apps Script (GMAIL_RELAY_URL/SECRET) NON supporta allegati (risponde
sempre "ok" anche ignorandoli, verificato) — va bene solo per email senza
allegato. Quando c'è un allegato serve SMTP:
  1. SMTP_HOST/SMTP_PORT + SMTP_EMAIL|SMTP_USER + SMTP_PASSWORD
  2. PEC_HOST/PEC_PORT + PEC_USER + PEC_PASSWORD
  3. GMAIL_APP_PASSWORD (+ ADMIN_EMAIL o GMAIL_ACCOUNT_AMMINISTRATIVO) → smtp.gmail.com:465
Credenziali SOLO nelle env di Render, mai nel codice/chat.
"""
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional, Sequence, Tuple

import httpx


def _credenziali_relay() -> Optional[dict]:
    url = os.getenv("GMAIL_RELAY_URL")
    secret = os.getenv("GMAIL_RELAY_SECRET")
    if not (url and secret):
        return None
    return {"url": url, "secret": secret}


def credenziali_smtp() -> Optional[dict]:
    host = os.getenv("SMTP_HOST") or os.getenv("PEC_HOST")
    port_str = os.getenv("SMTP_PORT") or os.getenv("PEC_PORT")
    user = os.getenv("SMTP_EMAIL") or os.getenv("SMTP_USER") or os.getenv("PEC_USER")
    pwd = os.getenv("SMTP_PASSWORD") or os.getenv("PEC_PASSWORD")
    if not (host and user and pwd):
        gmail_pwd = os.getenv("GMAIL_APP_PASSWORD")
        gmail_user = os.getenv("GMAIL_ACCOUNT_AMMINISTRATIVO") or os.getenv("ADMIN_EMAIL")
        if gmail_pwd and gmail_user:
            host = host or "smtp.gmail.com"
            user = user or gmail_user
            # l'app password di Gmail si copia spesso con gli spazi (xxxx xxxx xxxx xxxx)
            pwd = pwd or gmail_pwd.replace(" ", "")
    if not (host and user and pwd):
        return None
    return {"host": host, "port": int(port_str or 465), "user": user, "password": pwd}


def _invia_via_relay(cred: dict, destinatario: str, oggetto: str, corpo: str) -> None:
    payload = {
        "secret": cred["secret"],
        "to": destinatario,
        "subject": oggetto,
        "body": corpo,
    }
    resp = httpx.post(cred["url"], json=payload, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    corpo_risposta = resp.text or ""
    if '"ok":true' not in corpo_risposta.replace(" ", ""):
        raise RuntimeError(f"Relay email ha risposto senza conferma: {corpo_risposta[:300]}")


def _invia_via_smtp(cred: dict, destinatario: str, oggetto: str, corpo: str,
                    allegati: Optional[Sequence[Tuple[bytes, str, str, str]]] = None) -> None:
    msg = EmailMessage()
    msg["From"] = cred["user"]
    msg["To"] = destinatario
    msg["Subject"] = oggetto
    msg.set_content(corpo)
    for dati, maintype, subtype, filename in (allegati or []):
        msg.add_attachment(dati, maintype=maintype, subtype=subtype, filename=filename)
    # timeout esplicito: senza, una connessione SMTP che non risponde resta
    # bloccata a tempo indeterminato — un endpoint che invia l'email prima di
    # rispondere (es. POST /richieste) puo' far scadere il timeout del client
    # (frontend) mentre l'inserimento e' gia' avvenuto, inducendo un secondo
    # tentativo che duplica la richiesta. 25s per restare sotto il timeout
    # scritture del portale mobile (40s), coerente col relay email (30s sopra).
    if cred["port"] == 465:
        with smtplib.SMTP_SSL(cred["host"], cred["port"], timeout=25,
                              context=ssl.create_default_context()) as s:
            s.login(cred["user"], cred["password"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(cred["host"], cred["port"], timeout=25) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(cred["user"], cred["password"])
            s.send_message(msg)


def invia_email(destinatario: str, oggetto: str, corpo: str,
                allegati: Optional[Sequence[Tuple[bytes, str, str, str]]] = None) -> None:
    """Invio SINCRONO (bloccante): chiamare da un thread (asyncio.to_thread) se
    usato da codice async. allegati: lista di (bytes, maintype, subtype, filename).
    Con allegati serve per forza SMTP (il relay li ignora silenziosamente)."""
    if allegati:
        cred = credenziali_smtp()
        if not cred:
            raise RuntimeError("Email con allegato non configurata su Render: il relay "
                               "(GMAIL_RELAY_URL/SECRET) non supporta gli allegati, serve "
                               "SMTP_HOST/PEC_HOST oppure GMAIL_APP_PASSWORD + ADMIN_EMAIL")
        _invia_via_smtp(cred, destinatario, oggetto, corpo, allegati)
        return
    relay = _credenziali_relay()
    if relay:
        _invia_via_relay(relay, destinatario, oggetto, corpo)
        return
    cred = credenziali_smtp()
    if not cred:
        raise RuntimeError("Email non configurata su Render (mancano GMAIL_RELAY_URL/SECRET, "
                           "SMTP_HOST/PEC_HOST oppure GMAIL_APP_PASSWORD + ADMIN_EMAIL)")
    _invia_via_smtp(cred, destinatario, oggetto, corpo)
