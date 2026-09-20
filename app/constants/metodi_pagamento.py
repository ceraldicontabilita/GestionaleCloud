"""Quando il metodo di pagamento di un fornitore NON e' configurato.

Il gestionale non ha un solo modo di dire «non lo so»: l'import scrive
`"sospesa"` (`fatture_upload.py`, «se il fornitore non ha un metodo →
"sospesa" → resta nei provvisori»), altri percorsi hanno lasciato
`"da_configurare"`, `"none"` o la stringa vuota, e l'import massivo del
14/09/2026 non ha scritto il campo affatto.

Sono tutti lo stesso fatto contabile — **il metodo non c'e'** — e finche'
ogni pezzo di codice si teneva la propria lista il vocabolario divergeva in
silenzio. Misurato in produzione il 19/09/2026 sulle 873 fatture attive:
583 `"sospesa"`, 249 senza il campo, 41 con un metodo vero. L'handler
`on_fattura_created_alert_fornitore` confrontava contro
`("", "da_configurare", "none")`: `"sospesa"` non c'era, quindi
`FORN_MP_MANCANTE` e `FAT_MP_NON_DEFINITO` non sono **mai** stati emessi da
quel percorso (0 righe in `alerts` contro le 832 fatture che li meritavano;
i 590 `FAT_MP_NON_DEFINITO` in archivio vengono da un altro punto di
emissione, `fatture_upload.py`).

Una sola definizione, qui. Un valore nuovo si aggiunge in questo file.
"""
from typing import Any

__all__ = [
    "METODI_NON_CONFIGURATI",
    "FILTRO_METODO_NON_CONFIGURATO",
    "metodo_non_configurato",
]

#: I valori che significano «metodo di pagamento non configurato».
#: Il confronto e' sempre in minuscolo e senza spazi ai bordi.
METODI_NON_CONFIGURATI = frozenset({
    "",
    "sospesa",
    "da_configurare",
    "none",
    "null",
})


def metodo_non_configurato(valore: Any) -> bool:
    """`True` se questo metodo di pagamento vale «non configurato».

    Tollera `None`, spazi e maiuscole: in produzione convivono `"bonifico"` e
    `"Bonifico"`, quindi un confronto esatto si perderebbe dei casi.
    """
    if valore is None:
        return True
    return str(valore).strip().lower() in METODI_NON_CONFIGURATI


#: Lo stesso fatto, come filtro di archivio. Serve a chi deve *selezionare* le
#: righe senza metodo invece di giudicarne una: scrivere la lista a mano nella
#: query e' come tenersi un secondo vocabolario, e si perde il caso piu'
#: frequente. `None` intercetta anche il campo assente.
FILTRO_METODO_NON_CONFIGURATO = {
    "metodo_pagamento": {"$in": [None] + sorted(METODI_NON_CONFIGURATI)}
}
