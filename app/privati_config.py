"""
Configurazione Privati — Ceraldi ERP
=====================================
SORGENTE UNICA DI VERITÀ per tutti i soggetti privati (familiari del titolare).

REGOLA: nessun altro file deve contenere dati anagrafici dei privati.
Tutti i parser, router e componenti importano DA QUI.

I dati anagrafici sensibili (indirizzi, IBAN, ecc.) sono gestiti
esclusivamente nel database MongoDB — collection "privati_anagrafica" —
e accessibili solo tramite la pagina /privati (autenticata).

Questo file contiene SOLO i CF e i metadati minimi necessari
per il routing automatico dei documenti.
"""

CF_AZIENDA = "04523831214"

# Mappa CF → metadati minimi per routing documenti
# I dati completi sono in MongoDB: db["privati_anagrafica"]
PRIVATI_CF = {
    "CRLMHL50R01F352F": {
        "nome": "Ceraldi Michele",
        "relazione": "familiare",
        "collezioni": ["tributi_privati", "f24_privati"],
        "pagina": "privati",
    },
    "CRLNNT75M55F352C": {
        "nome": "Ceraldi Antonietta",
        "relazione": "familiare",
        "collezioni": ["tributi_privati"],
        "pagina": "privati",
    },
}


def is_privato(cf: str) -> bool:
    """Ritorna True se il CF appartiene a un privato (non all'azienda)."""
    return cf != CF_AZIENDA and cf in PRIVATI_CF


def get_info_privato(cf: str) -> dict | None:
    """Ritorna i metadati minimi di un privato, o None se non trovato."""
    return PRIVATI_CF.get(cf)


def collezione_da_cf(cf: str) -> str:
    """Determina la collection MongoDB principale da usare per questo CF."""
    if cf == CF_AZIENDA:
        return "tributi_azienda"
    info = PRIVATI_CF.get(cf)
    if info:
        return info["collezioni"][0]
    return "tributi_privati"  # default per CF sconosciuti


def nome_da_cf(cf: str) -> str:
    """Ritorna il nome del soggetto dal CF."""
    if cf == CF_AZIENDA:
        return "Ceraldi Group SRL"
    info = PRIVATI_CF.get(cf)
    return info["nome"] if info else f"CF {cf}"
