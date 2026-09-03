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


# ── Soggetto pagante dichiarato nella causale bancaria (audit 03/09/2026, PR 4)

# Forme societarie e parole che non identificano un soggetto: "Amazon
# Business EU S.a.r.l, Sede Secondaria" e "AMAZON BUSINESS EU SARL, IT
# BRANCH" sono lo stesso soggetto; "AMAZON PAYMENTS EUROPE S.C.A." no.
_FORME_SOCIETARIE_TOKEN = {
    "srl", "srls", "spa", "sas", "snc", "ss", "sarl", "sca", "scarl", "scpa",
    "gmbh", "ltd", "llc", "bv", "nv", "ag", "sa", "se", "plc", "inc", "co",
    "coop", "societa", "society", "company", "limited", "corporation", "corp",
}
_TOKEN_GENERICI_SOGGETTO = {
    "sede", "secondaria", "branch", "filiale", "italia", "italy", "italian",
    "it", "eu", "europe", "europa", "european", "international", "group",
    "gruppo", "holding", "rappresentante", "fiscale",
}

_SDD_SOGGETTO_RE = re.compile(
    r"\bSDD\s*(?:CORE|B2B)?\s*:\s*(\S+)\s+(.+)$", re.IGNORECASE,
)
_BONIFICO_SOGGETTO_RE = re.compile(
    r"\b(?:A\s+FAVORE\s+DI|FAVORE|BENEF(?:ICIARIO)?)\s*[:\s]\s*(.+)$",
    re.IGNORECASE,
)
_FINE_SOGGETTO_RE = re.compile(r"\s+-\s+|\s+NOTPROVIDE\b|\s+ADD\.\s*(?:TOT|SPE)\b", re.IGNORECASE)


def soggetto_causale_bancaria(descrizione: str) -> str | None:
    """Controparte dichiarata dalla banca nella causale, se leggibile.

    - addebiti diretti: il nome che segue il codice mandato
      (``SDD CORE: <mandato> AMAZON PAYMENTS EUROPE S.C.A.``);
    - bonifici: il beneficiario dopo ``FAVORE`` / ``A FAVORE DI`` /
      ``BENEFICIARIO``.

    Restituisce ``None`` quando la causale non dichiara nessuna controparte
    (nessun giudizio possibile), mai una stringa vuota.
    """
    testo = " ".join(str(descrizione or "").split())
    if not testo:
        return None
    match = _SDD_SOGGETTO_RE.search(testo)
    soggetto = match.group(2) if match else None
    if soggetto is None:
        match = _BONIFICO_SOGGETTO_RE.search(testo)
        if not match:
            return None
        soggetto = match.group(1)
    soggetto = _FINE_SOGGETTO_RE.split(soggetto, maxsplit=1)[0].strip(" -:;,.")
    return soggetto or None


def tokens_identita_soggetto(nome: str) -> frozenset[str]:
    """Token che identificano davvero un soggetto: senza forme societarie,
    senza parole di sede/nazione e senza numeri."""
    return frozenset(
        token for token in nome_tokens(nome)
        if token not in _FORME_SOCIETARIE_TOKEN
        and token not in _TOKEN_GENERICI_SOGGETTO
        and not token.isdigit()
    )


def soggetto_pagante_coerente(
    fornitore: str, descrizione: str, alias: tuple[str, ...] | list[str] = (),
) -> bool | None:
    """Il soggetto scritto nella causale e' lo stesso fornitore della fattura?

    - ``None``: la causale non dichiara nessuna controparte leggibile (nessun
      giudizio: valgono le altre prove);
    - ``True``: la controparte e' un'abbreviazione del fornitore ("Eni Spa"
      per "Eni Plenitude S.p.A."), lo stesso nome con forma societaria o
      sede diversa, oppure uno degli ``alias`` dichiarati in anagrafica;
    - ``False``: la controparte porta un'identita' diversa. Un solo marchio
      in comune ("AMAZON" tra "Amazon Business EU S.a.r.l" e "AMAZON
      PAYMENTS EUROPE S.C.A.") non basta: sono due soggetti.
    """
    soggetto = soggetto_causale_bancaria(descrizione)
    if not soggetto:
        return None
    tokens_soggetto = tokens_identita_soggetto(soggetto)
    if not tokens_soggetto:
        return None
    for nome in (fornitore, *(alias or ())):
        tokens_fornitore = tokens_identita_soggetto(str(nome or ""))
        if not tokens_fornitore:
            continue
        if tokens_soggetto <= tokens_fornitore:
            return True
        # Il fornitore e' contenuto nella controparte: ammesso solo quando
        # il fornitore ha un'identita' di almeno due parole ("Alfa Forniture"
        # in "ALFA FORNITURE NAPOLI"). Un marchio da una parola contenuto in
        # un nome piu' lungo e' un soggetto diverso.
        if len(tokens_fornitore) >= 2 and tokens_fornitore <= tokens_soggetto:
            return True
    return False


def alias_fornitore(documento: dict | None) -> tuple[str, ...]:
    """Nomi alternativi dichiarati su fattura o anagrafica fornitore."""
    if not isinstance(documento, dict):
        return ()
    valori: list[str] = []
    for campo in ("alias", "nomi_alternativi", "ragioni_sociali_alternative",
                  "fornitore_alias", "supplier_aliases"):
        valore = documento.get(campo)
        if isinstance(valore, str):
            valori.extend(parte.strip() for parte in valore.split(";"))
        elif isinstance(valore, (list, tuple)):
            valori.extend(str(item).strip() for item in valore)
    return tuple(v for v in valori if v)
