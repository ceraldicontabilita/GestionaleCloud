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
        "croissant-senza-glutine-80g",
        "Croissant senza glutine",
        "Croissant vuoto senza glutine.",
    ),
    "AQV DORAMAO CROISSANT ALMONDS 95G 494KG": (
        "croissant-dorami-mandorle-95g",
        "Croissant Dorami alle mandorle",
        "Croissant dritto alle mandorle.",
    ),
    "FAGOTTO DUBAI STYLE": (
        "fagotto-dubai-style",
        "Fagotto Dubai Style",
        "Fagotto dolce in stile Dubai.",
    ),
    "POLPETTINE DI CARNE G 10 12": (
        "polpettine-carne-10-12g",
        "Polpettine di carne",
        "Polpettine di carne in formato mignon.",
    ),
    "AQV CMBLL MAXI SUGARED 100G 3KG": (
        "ciambella-maxi-zuccherata-100g",
        "Ciambella maxi zuccherata",
        "Ciambella soffice ricoperta di zucchero.",
    ),
    "CIAMBELLA MAXI ZUCCHERATA G 100": (
        "ciambella-maxi-zuccherata-100g",
        "Ciambella maxi zuccherata",
        "Ciambella soffice ricoperta di zucchero.",
    ),
    "AQV CMBLL MINI SUGARED 22G 2 64KG": (
        "ciambella-mini-zuccherata-22g",
        "Mini ciambella zuccherata",
        "Mini ciambella soffice ricoperta di zucchero.",
    ),
    "CIAMBELLA MINI ZUCCHERATA G 22 25": (
        "ciambella-mini-zuccherata-22g",
        "Mini ciambella zuccherata",
        "Mini ciambella soffice ricoperta di zucchero.",
    ),
    "AQV CORNETTO VEG CURCUMA VUOTO 75G 4 6KG": (
        "cornetto-vegano-curcuma-75g",
        "Cornetto vegano alla curcuma",
        "Cornetto vegano curvo alla curcuma.",
    ),
    "AQV SOFIA 82G 4 592KG": (
        "sofia-82g",
        "Sofia",
        "Cornetto dritto con burro e lievito naturale.",
    ),
    "AQV TAPPI GRANDI 57G 6KG": (
        "tappi-grandi-57g",
        "Tappi grandi",
        "Basi di sfoglia da farcire.",
    ),
    "TAPPI GRANDI G 55 60": (
        "tappi-grandi-57g",
        "Tappi grandi",
        "Basi di sfoglia da farcire.",
    ),
    "AQV TAPPI MIGNON FOR SFOGL 20G 4KG": (
        "tappi-mignon-20g",
        "Tappi mignon",
        "Basi di sfoglia mignon da farcire.",
    ),
    "TAPPI MIGNON PER SFOGLIATE GR 20": (
        "tappi-mignon-20g",
        "Tappi mignon",
        "Basi di sfoglia mignon da farcire.",
    ),
    "CORNETTO SENZA GLUTINE VUOTO G 100": (
        "cornetto-senza-glutine-vuoto-100g",
        "Cornetto senza glutine vuoto",
        "Cornetto vuoto senza glutine.",
    ),
    "CORNETTO SENZA GLUTINE ALBICOCCA G 100": (
        "cornetto-senza-glutine-albicocca-100g",
        "Cornetto senza glutine all'albicocca",
        "Cornetto senza glutine farcito all'albicocca.",
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
    presentazione = _PRESENTAZIONE_FATTURA_ESATTA.get(testo_normalizzato(descrizione))
    if presentazione:
        return f"fattura_alias:{presentazione[0]}", None
    return f"fattura:{testo_normalizzato(descrizione)}", None


def digest_identita(identita: str) -> str:
    return hashlib.sha256(str(identita).encode("utf-8")).hexdigest()[:24]


def presentazione_fattura(descrizione: str) -> tuple[str, str]:
    """Testo breve per alias noti, senza attribuire una scheda catalogo."""

    testo = testo_normalizzato(descrizione)
    presentazione = _PRESENTAZIONE_FATTURA_ESATTA.get(testo)
    if presentazione:
        return presentazione[1], presentazione[2]
    return str(descrizione or "").strip(), ""


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
