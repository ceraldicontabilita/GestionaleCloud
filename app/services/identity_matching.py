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
# BRANCH" sono lo stesso soggetto; "Alfa Forniture Srl" e "ALFA PAYMENTS
# EUROPE S.A." no (salvo i collettori di gruppo dichiarati sotto).
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

# Collettori di pagamento di un gruppo: la causale dichiara la societa' che
# incassa per conto del fornitore. "AMAZON PAYMENTS EUROPE S.C.A." riscuote
# gli SDD di ogni societa' Amazon ("Amazon Business EU S.a.r.l", "Amazon EU
# S.a r.l."): e' lo stesso gruppo, non un soggetto diverso (titolare,
# 02/10/2026: Amazon paga sempre con metodo tracciato, l'SDD e' la prova).
# Chiave: token identificativi del collettore; valore: il marchio che il
# fornitore deve portare nel nome.
_COLLETTORI_DI_GRUPPO: dict[frozenset[str], str] = {
    frozenset({"amazon", "payments"}): "amazon",
}

_SDD_SOGGETTO_RE = re.compile(
    r"\bSDD\s*(?:CORE|B2B)?\s*:\s*(\S+)\s+(.+)$", re.IGNORECASE,
)
_BONIFICO_SOGGETTO_RE = re.compile(
    r"\b(?:A\s+FAVORE\s+DI|FAVORE|BENEF(?:ICIARIO)?)\s*[:\s]\s*(.+)$",
    re.IGNORECASE,
)
_FINE_SOGGETTO_RE = re.compile(r"\s+-\s+|\s+NOTPROVIDE\b|\s+ADD\.\s*(?:TOT|SPE)\b", re.IGNORECASE)
# Bonifico in entrata: l'ordinante dopo ``BON.DA`` ("BONIF. VS. FAVORE -
# BON.DA AMAZON BUSINESS EU SARL, IT BRANCH 408 -3630067-4208347 ..."). Il
# numero d'ordine o il riferimento che segue il nome non e' parte del
# soggetto.
_BONIFICO_ORDINANTE_RE = re.compile(r"\bBON\.?\s*DA\s+(.+)$", re.IGNORECASE)
_FINE_ORDINANTE_RE = re.compile(
    r"\s+\d[\d\s]*-\d|\s+NR\.\s*BONIFICO\b|\s+AMZN\b|\s+RIF\.?\s", re.IGNORECASE,
)


def soggetto_causale_bancaria(descrizione: str) -> str | None:
    """Controparte dichiarata dalla banca nella causale, se leggibile.

    - addebiti diretti: il nome che segue il codice mandato
      (``SDD CORE: <mandato> AMAZON PAYMENTS EUROPE S.C.A.``);
    - bonifici disposti: il beneficiario dopo ``FAVORE`` / ``A FAVORE DI`` /
      ``BENEFICIARIO``;
    - bonifici ricevuti: l'ordinante dopo ``BON.DA`` (rimborsi, note di
      credito), letto prima del ``FAVORE`` della stessa causale.

    Restituisce ``None`` quando la causale non dichiara nessuna controparte
    (nessun giudizio possibile), mai una stringa vuota.
    """
    testo = " ".join(str(descrizione or "").split())
    if not testo:
        return None
    match = _SDD_SOGGETTO_RE.search(testo)
    soggetto = match.group(2) if match else None
    if soggetto is None:
        match = _BONIFICO_ORDINANTE_RE.search(testo)
        if match:
            soggetto = _FINE_ORDINANTE_RE.split(match.group(1), maxsplit=1)[0]
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
    - ``True`` anche quando la controparte e' il collettore di pagamento del
      gruppo del fornitore (``_COLLETTORI_DI_GRUPPO``: "AMAZON PAYMENTS
      EUROPE S.C.A." per ogni societa' Amazon);
    - ``False``: la controparte porta un'identita' diversa. Un solo marchio
      in comune ("ALFA" tra "Alfa Forniture Srl" e "ALFA PAYMENTS EUROPE")
      non basta: sono due soggetti, salvo i collettori di gruppo dichiarati.
    """
    soggetto = soggetto_causale_bancaria(descrizione)
    if not soggetto:
        return None
    tokens_soggetto = tokens_identita_soggetto(soggetto)
    if not tokens_soggetto:
        return None
    for tokens_collettore, marchio in _COLLETTORI_DI_GRUPPO.items():
        if tokens_collettore <= tokens_soggetto and marchio in tokens_identita_soggetto(str(fornitore or "")):
            return True
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
