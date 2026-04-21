"""
Utility condivise per parsing email PagoPA/PEC Gmail.
Gestisce fallback text/plain → text/html con strip tag, normalizzazione whitespace.
"""
import re
from html.parser import HTMLParser
from html import unescape
from typing import Optional


class _HTMLStripper(HTMLParser):
    """Estrae testo visibile da HTML, ignorando script/style."""

    _SKIP_TAGS = {"script", "style", "head"}

    def __init__(self):
        super().__init__()
        self._parts = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        # inserisce newline per tag di blocco per preservare struttura
        if tag in ("br", "p", "div", "tr", "li"):
            self._parts.append("\n")
        elif tag == "td":
            self._parts.append(" ")

    def handle_endtag(self, tag):
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        raw = "".join(self._parts)
        raw = unescape(raw)
        # normalizza spazi ma preserva newline
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in raw.splitlines()]
        lines = [ln for ln in lines if ln]
        return "\n".join(lines)


def html_to_text(html_content: str) -> str:
    """Converte HTML in testo pulito. Fallback regex se HTMLParser fallisce."""
    if not html_content:
        return ""
    try:
        s = _HTMLStripper()
        s.feed(html_content)
        return s.get_text()
    except Exception:
        txt = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html_content,
                     flags=re.DOTALL | re.IGNORECASE)
        txt = re.sub(r"<[^>]+>", " ", txt)
        txt = unescape(txt)
        return re.sub(r"\s+", " ", txt).strip()


def extract_best_body(msg) -> str:
    """
    Estrai il miglior body testuale da un'email.
    Preferisce text/plain ma fa fallback su text/html (convertito) quando:
    - text/plain è assente
    - text/plain ha meno di 50 caratteri utili (es. solo firma/header)
    Gestisce anche message/rfc822 annidati.
    """
    from email.parser import BytesParser
    from email.policy import default as default_policy

    plain_parts = []
    html_parts = []

    for part in msg.walk():
        ctype = part.get_content_type()
        filename = (part.get_filename() or "")

        if ctype == "text/plain":
            try:
                body = (part.get_payload(decode=True) or b"").decode(
                    part.get_content_charset() or "utf-8", errors="replace"
                )
                plain_parts.append(body)
            except Exception:
                pass
        elif ctype == "text/html":
            try:
                body = (part.get_payload(decode=True) or b"").decode(
                    part.get_content_charset() or "utf-8", errors="replace"
                )
                html_parts.append(body)
            except Exception:
                pass
        elif ctype == "message/rfc822" or filename.lower().endswith(".eml"):
            try:
                if part.is_multipart():
                    for sub in part.get_payload():
                        inner = BytesParser(policy=default_policy).parsebytes(sub.as_bytes())
                        inner_text = extract_best_body(inner)
                        if inner_text:
                            plain_parts.append(inner_text)
                else:
                    raw = part.get_payload(decode=True)
                    if raw:
                        inner = BytesParser(policy=default_policy).parsebytes(raw)
                        inner_text = extract_best_body(inner)
                        if inner_text:
                            plain_parts.append(inner_text)
            except Exception:
                pass

    plain = "\n".join(plain_parts).strip()
    # Se text/plain è abbastanza corposo, usa quello
    if len(plain) >= 50:
        return plain

    # Altrimenti convertli HTML
    if html_parts:
        html_text = html_to_text("\n".join(html_parts))
        # Se HTML ha più contenuto reale, preferiscilo
        if len(html_text) > len(plain):
            return html_text

    return plain or ""
