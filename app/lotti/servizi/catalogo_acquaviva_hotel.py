"""Identita' verificabile delle referenze Acquaviva acquistate.

Le fatture restano la prova dell'acquisto. Il catalogo ufficiale serve soltanto
per presentare nome, foto e descrizione leggibili; il collegamento e' ammesso
solo con codice, alias fattura o testo esatto documentato.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any, Iterable, Mapping, Optional


CAMPI_CODICE = (
    "codice",
    "codice_articolo",
    "codice_prodotto",
    "codice_aqv_2026",
    "codice_aqv_2025",
    "acquaviva_id",
)


_PRESENTAZIONE_FATTURA_ESATTA = {
    "AQV CRNT GLUTEN FREE 80G 1 6KG": (
        "Croissant senza glutine",
        "Croissant vuoto senza glutine.",
    ),
    "AQV DORAMAO CROISSANT ALMONDS 95G 494KG": (
        "Croissant Dorami alle mandorle",
        "Croissant dritto alle mandorle.",
    ),
    "FAGOTTO DUBAI STYLE": (
        "Fagotto Dubai Style",
        "Fagotto dolce in stile Dubai.",
    ),
    "POLPETTINE DI CARNE G 10 12": (
        "Polpettine di carne",
        "Polpettine di carne in formato mignon.",
    ),
}


def testo_normalizzato(valore: Any) -> str:
    testo = unicodedata.normalize("NFKD", str(valore or ""))
    testo = "".join(c for c in testo if not unicodedata.combining(c))
    return " ".join(re.findall(r"[A-Z0-9]+", testo.upper()))


def _codici_prodotto(prodotto: Mapping[str, Any]) -> set[str]:
    valori = [
        *(prodotto.get(campo) for campo in CAMPI_CODICE),
        *((prodotto.get("codici_alias") or [])),
    ]
    return {
        testo_normalizzato(valore).replace(" ", "")
        for valore in valori
        if str(valore or "").strip()
    }


def prodotto_certo_da_riga(
    descrizione: str,
    riga: Mapping[str, Any],
    prodotti: Iterable[Mapping[str, Any]],
) -> Optional[Mapping[str, Any]]:
    """Restituisce un solo prodotto quando l'identita' e' documentata."""

    codici_riga = {
        testo_normalizzato(riga.get(campo)).replace(" ", "")
        for campo in ("codice", "codice_articolo", "codice_prodotto", "sku")
        if riga.get(campo)
    }
    testo_riga = testo_normalizzato(descrizione)
    candidati: list[Mapping[str, Any]] = []
    for prodotto in prodotti:
        codici = _codici_prodotto(prodotto)
        alias = {
            testo_normalizzato(valore)
            for valore in (prodotto.get("alias_fattura") or [])
            if str(valore or "").strip()
        }
        testi_esatti = {
            testo_normalizzato(prodotto.get(campo))
            for campo in (
                "nome",
                "nome_display",
                "nome_verificato",
                "descrizione",
                "descrizione_lunga",
            )
            if prodotto.get(campo)
        }
        codice_nel_testo = any(
            len(codice) >= 4
            and re.search(rf"(?:^|\s){re.escape(codice)}(?:\s|$)", testo_riga)
            for codice in codici
        )
        if (
            (codici_riga and codici_riga & codici)
            or codice_nel_testo
            or testo_riga in alias
            or (testo_riga and testo_riga in testi_esatti)
        ):
            candidati.append(prodotto)
    ids = {str(p.get("id") or "") for p in candidati}
    return candidati[0] if len(candidati) == 1 and len(ids) == 1 else None


def identita_riga(
    descrizione: str,
    riga: Mapping[str, Any],
    prodotti: Iterable[Mapping[str, Any]],
) -> tuple[str, Optional[Mapping[str, Any]]]:
    collegato = prodotto_certo_da_riga(descrizione, riga, prodotti)
    prodotto_id = str((collegato or {}).get("id") or "").strip()
    if prodotto_id:
        return f"catalogo:{prodotto_id}", collegato
    return f"fattura:{testo_normalizzato(descrizione)}", None


def digest_identita(identita: str) -> str:
    return hashlib.sha256(str(identita).encode("utf-8")).hexdigest()[:24]


def presentazione_fattura(descrizione: str) -> tuple[str, str]:
    """Testo breve per alias noti, senza attribuire una scheda catalogo."""

    testo = testo_normalizzato(descrizione)
    return _PRESENTAZIONE_FATTURA_ESATTA.get(testo, (str(descrizione or "").strip(), ""))


def descrizione_breve(prodotto: Mapping[str, Any]) -> str:
    """Una sola frase per il menu, senza codici, cartoni o istruzioni tecniche."""

    nome = str(
        prodotto.get("nome_verificato")
        or prodotto.get("nome_display")
        or prodotto.get("nome")
        or ""
    ).strip()
    normalizzato = testo_normalizzato(nome)
    descrizioni_note = (
        ("BABY CALISE", "Cornetto baby vuoto, soffice e friabile, con impasto brioche e sfoglia."),
        ("CIAMBELLA MAXI", "Ciambella soffice ricoperta di zucchero."),
        ("CIAMBELLA MINI", "Mini ciambella soffice ricoperta di zucchero."),
        ("CODA D ARAGOSTA MIGNON", "Sfoglia croccante in formato mignon, da farcire."),
        ("CODA D ARAGOSTA", "Sfoglia croccante della tradizione napoletana, da farcire."),
        ("SFOGLIATELLA FROLLA MIGNON", "Pasta frolla mignon con ricotta, semola e canditi."),
        ("SFOGLIATELLA NAPOLETANA MIGNON", "Sfogliatella riccia mignon con ricotta, semola e arancia."),
        ("SOFIA", "Cornetto dritto e compatto, con burro e lievito naturale."),
        ("PANCAKE", "Pancake soffice, pronto da guarnire."),
        ("POLPETTINE", "Polpettine di carne in formato mignon."),
        ("TAPPI MIGNON", "Base di sfoglia mignon per preparazioni dolci."),
        ("TAPPI", "Base di sfoglia per preparazioni dolci."),
    )
    for chiave, testo in descrizioni_note:
        if chiave in normalizzato:
            return testo

    descrizione = str(
        prodotto.get("descrizione_breve")
        or prodotto.get("descrizione_lunga")
        or prodotto.get("descrizione")
        or ""
    ).strip()
    descrizione = re.sub(r"\s+", " ", descrizione)
    descrizione = re.sub(
        r"\b(?:codice|grammi|pz\.?\s*conf\.?|gradi\s*forno|minuti)\b.*$",
        "",
        descrizione,
        flags=re.IGNORECASE,
    ).strip(" -–—:;,. ")
    if not descrizione:
        return ""
    frase = re.split(r"(?<=[.!?])\s+", descrizione, maxsplit=1)[0]
    if len(frase) <= 170:
        return frase
    taglio = frase[:167].rsplit(" ", 1)[0]
    return f"{taglio}…"
