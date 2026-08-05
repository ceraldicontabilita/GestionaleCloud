"""Normalizzazione condivisa per identita' di persone e aziende.

Il modulo non dipende da router o database: puo' quindi essere riusato dai
flussi bonifici, stipendi e fatture senza creare cicli di importazione.
"""

from __future__ import annotations

import re
import unicodedata


_FORME_GIURIDICHE = (
    (r"\bs\s*\.?\s*r\s*\.?\s*l\s*\.?\b", "srl"),
    (r"\bs\s*\.?\s*p\s*\.?\s*a\s*\.?\b", "spa"),
    (r"\bs\s*\.?\s*a\s*\.?\s*s\s*\.?\b", "sas"),
    (r"\bs\s*\.?\s*n\s*\.?\s*c\s*\.?\b", "snc"),
    (r"\bs\s*\.?\s*s\s*\.?\b", "ss"),
)

_STOP_WORDS = {
    "beneficiario",
    "ordinante",
    "bonifico",
    "stipendio",
    "emolumenti",
    "mensilita",
    "pagamento",
    "favore",
    "copia",
}


def nome_tokens(nome: str) -> frozenset[str]:
    """Token stabili, senza accenti e con forme societarie normalizzate."""
    text = str(nome or "").casefold()
    for pattern, replacement in _FORME_GIURIDICHE:
        text = re.sub(pattern, f" {replacement} ", text, flags=re.IGNORECASE)
    text = "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )
    tokens = re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", text)
    return frozenset(
        token for token in tokens if len(token) > 1 and token not in _STOP_WORDS
    )


def identita_coincide(nome_a: str, nome_b: str) -> bool:
    """Richiede la stessa identita' completa, mai un solo token generico."""
    tokens_a, tokens_b = nome_tokens(nome_a), nome_tokens(nome_b)
    return len(tokens_a) >= 2 and tokens_a == tokens_b


def nome_presente_nel_testo(nome: str, testo: str) -> bool:
    """Vero quando tutti i token significativi del nome sono nel testo."""
    identita = nome_tokens(nome)
    testo_tokens = nome_tokens(testo)
    return len(identita) >= 2 and identita.issubset(testo_tokens)
