"""Gli stati di un verbale, in un posto solo.

Il vocabolario era scritto a mano in ogni punto che ne aveva bisogno, e ogni
copia diceva una cosa diversa. Misurato in produzione il 20/09/2026 sui 105
verbali in archivio, tutti in stato ``fattura_ricevuta``:

* ``post_download_pipeline._cerca_quietanze_verbali`` cercava in
  ``["salvato", "da_pagare", "identificato"]`` — **nessuno** dei 105;
* ``verbali_email_scanner`` cercava in ``["da_pagare", "DA_PAGARE",
  "identificato", "fattura_ricevuta"]`` — senza ``IDENTIFICATO`` e senza
  ``salvato``;
* ``verbali_email_logic`` aveva la quinta voce ma non ``salvato``;
* la lista dei «gia' pagati» esisteva in quattro copie
  (``_STATI_GIA_PAGATI``, ``sanitize_verbale_evidence``, la pipeline di
  ``/verbali-riconciliazione/stats`` e il filtro del finder).

Gli stati convivono in minuscolo e in maiuscolo perche' scrittori diversi li
hanno salvati cosi': i filtri d'archivio li devono elencare entrambi, e per
questo si generano qui invece di scriverli a mano.

``pagato_attesa_fattura`` e' **legacy**: e' il nome sbagliato di «attesa
quietanza» e ``/verbali-riconciliazione/migra-attesa-fattura`` lo sostituisce.
Resta elencato finche' esistono righe che lo portano, non si scrive piu'.
"""
from typing import Any, Dict, Iterable, List

__all__ = [
    "STATI_APERTI",
    "STATI_PAGATI",
    "STATI_VERBALE_CHIUSI",
    "STATO_ATTESA_QUIETANZA_LEGACY",
    "STATO_QUARANTENA",
    "FILTRO_STATO_APERTO",
    "FILTRO_STATO_PAGATO",
    "e_aperto",
    "e_chiuso",
    "e_pagato",
    "varianti",
]

#: Il verbale non ha ancora una prova di pagamento: lo si cerca ancora.
STATI_APERTI = frozenset({
    "salvato",
    "importato",
    "da_scaricare",
    "da_gestire",
    "notificato",
    "identificato",
    "fattura_ricevuta",
    "da_pagare",
    "in_attesa_conferma",
})

#: Il nome sbagliato di «attesa quietanza», in via di migrazione.
STATO_ATTESA_QUIETANZA_LEGACY = "pagato_attesa_fattura"

#: Una prova di pagamento c'e' gia' (documentale, bancaria o entrambe).
STATI_PAGATI = frozenset({
    "pagato",
    "pagato_attesa_quietanza",
    STATO_ATTESA_QUIETANZA_LEGACY,
    "riconciliato",
})


#: Non e' un verbale: e' un numero di fattura letto come verbale, o un
#: verbale nato da una fattura che non esiste piu'. Resta in archivio con
#: ``motivo_quarantena`` (mai cancellato) e non e' ne' aperto ne' pagato.
STATO_QUARANTENA = "quarantena"

#: Il verbale non chiede piu' niente: pagato, chiuso a mano, in quarantena.
STATI_VERBALE_CHIUSI = frozenset(STATI_PAGATI | {"chiuso", STATO_QUARANTENA})


def varianti(stati: Iterable[str]) -> List[str]:
    """Gli stessi stati come li trova in archivio: minuscolo e maiuscolo.

    In `verbali_noleggio` convivono `da_pagare` e `DA_PAGARE` perche' li hanno
    scritti percorsi diversi. Un filtro che ne elenca uno solo perde le righe
    dell'altro senza dare errore.
    """
    fuori: List[str] = []
    for stato in stati:
        for variante in (stato.lower(), stato.upper()):
            if variante not in fuori:
                fuori.append(variante)
    return sorted(fuori)


#: Lo stesso fatto come filtro d'archivio.
FILTRO_STATO_APERTO: Dict[str, Any] = {"stato": {"$in": varianti(STATI_APERTI)}}
FILTRO_STATO_PAGATO: Dict[str, Any] = {"stato": {"$in": varianti(STATI_PAGATI)}}


def e_aperto(valore: Any) -> bool:
    """`True` se questo stato dice «prova di pagamento ancora da trovare»."""
    return str(valore or "").strip().lower() in STATI_APERTI


def e_pagato(valore: Any) -> bool:
    """`True` se questo stato dice «una prova di pagamento c'e' gia'»."""
    return str(valore or "").strip().lower() in STATI_PAGATI


def e_chiuso(valore: Any) -> bool:
    """`True` se il verbale non chiede piu' niente (pagato, chiuso, quarantena)."""
    return str(valore or "").strip().lower() in STATI_VERBALE_CHIUSI
