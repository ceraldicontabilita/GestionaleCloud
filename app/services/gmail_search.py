"""
Ricerca email su Gmail via IMAP (X-GM-RAW) per le riconciliazioni.

Usata dalla pagina PayPal per trovare fatture "esterne" che non passano dal
Sistema di Interscambio (ricevute SaaS, fornitori esteri: Spotify, MongoDB,
OpenAI, ...): si cerca nella casella Gmail per importo/controparte intorno
alla data della transazione.

Credenziali: prima dagli account configurati in Admin → Email
(collection `email_accounts`, campo app_password), poi dalle variabili
d'ambiente EMAIL_USER / EMAIL_APP_PASSWORD.
"""
import imaplib
import logging
import os
from email.header import decode_header
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

logger = logging.getLogger(__name__)


async def get_gmail_credentials(db) -> Tuple[Optional[str], Optional[str], str]:
    """Ritorna (email, app_password, imap_server)."""
    try:
        acc = await db["email_accounts"].find_one(
            {"app_password": {"$exists": True, "$nin": [None, ""]}},
            {"_id": 0, "email": 1, "app_password": 1, "imap_server": 1},
        )
        if acc and acc.get("email") and acc.get("app_password"):
            return acc["email"], acc["app_password"], acc.get("imap_server") or "imap.gmail.com"
    except Exception:
        logger.exception("Errore lettura account email da config")
    user = os.environ.get("EMAIL_USER") or os.environ.get("EMAIL_ADDRESS")
    pwd = os.environ.get("EMAIL_APP_PASSWORD") or os.environ.get("EMAIL_PASSWORD")
    return user, pwd, "imap.gmail.com"


def _decode(s: Optional[str]) -> str:
    if not s:
        return ""
    out = ""
    try:
        for txt, enc in decode_header(s):
            out += txt.decode(enc or "utf-8", "replace") if isinstance(txt, bytes) else txt
    except Exception:
        return str(s)
    return out.strip()


def search_gmail_sync(user: str, password: str, server: str,
                      raw_query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Cerca su Gmail con la sintassi di ricerca nativa (X-GM-RAW).

    Ritorna una lista di {subject, from, date, message_id, gmail_link,
    has_attachment} ordinata dal messaggio più recente.
    """
    conn = imaplib.IMAP4_SSL(server, timeout=20)
    try:
        conn.login(user, password)
        # Il nome della cartella "Tutti i messaggi" dipende dalla lingua account
        for folder in ('"[Gmail]/Tutti i messaggi"', '"[Gmail]/All Mail"', "INBOX"):
            try:
                st, _ = conn.select(folder, readonly=True)
                if st == "OK":
                    break
            except Exception:
                continue

        typ, data = conn.uid("SEARCH", "X-GM-RAW", f'"{raw_query}"')
        if typ != "OK" or not data or not data[0]:
            return []
        uids = data[0].split()
        uids = uids[-limit:]  # i più recenti
        results: List[Dict[str, Any]] = []
        for uid in reversed(uids):
            try:
                typ, msg_data = conn.uid(
                    "FETCH", uid,
                    "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE MESSAGE-ID)] BODYSTRUCTURE)",
                )
                if typ != "OK" or not msg_data:
                    continue
                header_bytes = b""
                structure_bytes = b""
                for part in msg_data:
                    if isinstance(part, tuple):
                        header_bytes += part[1]
                        structure_bytes += part[0]
                    elif isinstance(part, bytes):
                        structure_bytes += part
                import email as _email
                msg = _email.message_from_bytes(header_bytes)
                message_id = (msg.get("Message-ID") or "").strip().strip("<>")
                gmail_link = (
                    f"https://mail.google.com/mail/u/0/#search/rfc822msgid:{quote(message_id)}"
                    if message_id else None
                )
                su = structure_bytes.upper()
                has_attachment = b"ATTACHMENT" in su or b'"PDF"' in su
                results.append({
                    "subject": _decode(msg.get("Subject")),
                    "from": _decode(msg.get("From")),
                    "date": _decode(msg.get("Date")),
                    "message_id": message_id,
                    "gmail_link": gmail_link,
                    "has_attachment": has_attachment,
                })
            except Exception:
                continue
        return results
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def build_transaction_query(importo: float, nome_controparte: str = "",
                            data_iso: str = "", giorni_prima: int = 25,
                            giorni_dopo: int = 10) -> str:
    """Costruisce la query Gmail per una transazione: importo (con punto e
    virgola), eventuale controparte, finestra di date intorno alla transazione."""
    from datetime import datetime, timedelta

    imp = abs(float(importo or 0))
    terms = []
    if imp > 0:
        v_dot = f"{imp:.2f}"
        v_comma = v_dot.replace(".", ",")
        terms.extend([f'"{v_dot}"', f'"{v_comma}"'])
    nome = (nome_controparte or "").strip()
    if nome and nome != "-":
        # prima parola significativa (es. "MongoDB Limited" → MongoDB)
        for w in nome.replace(",", " ").split():
            if len(w) >= 4:
                terms.append(f'"{w}"')
                break
    q = "(" + " OR ".join(terms) + ")" if terms else ""
    if data_iso:
        try:
            d = datetime.strptime(data_iso[:10], "%Y-%m-%d")
            after = (d - timedelta(days=giorni_prima)).strftime("%Y/%m/%d")
            before = (d + timedelta(days=giorni_dopo)).strftime("%Y/%m/%d")
            q = f"{q} after:{after} before:{before}".strip()
        except (ValueError, TypeError):
            pass
    return q.strip()
