"""L'unico posto che sa se una fattura è pagata.

Il 20/09/2026 lo stato di pagamento di una fattura viveva in **cinque campi**
scritti da moduli diversi, e nessuno copriva l'archivio intero (2.555 fatture):

    stato             786 righe   pagata 639 · da_pagare 142 · parziale 5
    stato_pagamento   832 righe   da_verificare 641 · da_pagare 142 · pagata 46 · pagato 3
    pagato             46 righe   sempre true
    paid               46 righe   sempre true
    payment_status     29 righe   sempre "paid"

Il danno, misurato: **639 fatture pagate per 311.838,20 €** hanno `stato =
"pagata"` e **non hanno affatto** il campo `pagato`. Il frontend chiedeva
`fattura.pagato`, che su quelle è `undefined`, quindi le mostrava **non
pagate**. E il backend cercava le fatture aperte con
`{"pagato": {"$ne": True}}`: su un campo che 2.509 fatture su 2.555 non hanno
quel filtro **passa sempre** (regola 11 di CLAUDE.md), quindi la
riconciliazione, il cash flow e i solleciti prendevano dentro anche le pagate.

Da qui in avanti la domanda «è pagata?» si fa in un posto solo, e ci si arriva
sia dal codice (`e_pagata`) sia da una query (`FILTRO_NON_PAGATE`).

**Due campi che sembrano lo stato di pagamento e non lo sono**, verificati sui
dati e deliberatamente esclusi:

- ``status`` (2.306 righe: archiviata 1.127, imported 624, archived 555) è lo
  stato del *documento*. Ha anche lui due parole per la stessa cosa, ma è un
  altro problema;
- ``stato_finanziario`` (596 righe: da_verificare, da_confermare_cassa,
  in_attesa_estratto_conto, riconciliato) è lo stato della *riconciliazione*:
  «riconciliato» non vuol dire pagato.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping

# ── il vocabolario, come sta davvero in archivio ─────────────────────────
PAGATA = "pagata"
PARZIALE = "parziale"
DA_PAGARE = "da_pagare"
DA_VERIFICARE = "da_verificare"
ANNULLATA = "annullata"

#: Ogni modo in cui l'archivio scrive «pagata», italiano e inglese.
PAROLE_PAGATA = frozenset({
    "pagata", "pagato", "paid", "saldata", "saldato",
    "quietanzata", "quietanzato", "chiusa", "chiuso", "closed",
})
#: Una fattura annullata o stornata non è né pagata né da pagare.
PAROLE_ANNULLATA = frozenset({
    "annullata", "annullato", "stornata", "stornato",
    "cancelled", "canceled", "deleted", "eliminata", "eliminato",
})
PAROLE_PARZIALE = frozenset({"parziale", "partial", "parzialmente_pagata"})
PAROLE_DA_PAGARE = frozenset({"da_pagare", "non_pagata", "non_pagato", "unpaid", "aperta"})

#: Solo per F24 e tributi: come si chiude una posizione quietanzata.
#: Non riguarda le fatture, quindi non è nel gemello JavaScript.
PAROLE_PAGATA_F24 = frozenset({
    "pagata_puntuale", "pagata_con_ravvedimento",
    "pagata_in_ritardo_senza_ravvedimento",
})

#: Una posizione non più aperta: pagata, quietanzata o annullata.
#: Era scritta **tre volte** — in `fiscale_shadow_service`,
#: `cash_flow_13w_service` e `crediti_shadow_service` — con tre contenuti
#: diversi: alla prima mancavano `chiusa`/`closed`/`stornata`, alla seconda
#: `quietanzato` e `deleted`, alla terza le varianti F24. Ogni lista aveva il
#: suo buco, e ogni buco era una posizione chiusa contata come aperta.
STATI_CHIUSI = PAROLE_PAGATA | PAROLE_PAGATA_F24 | PAROLE_ANNULLATA | frozenset({
    "chiusa", "chiuso", "closed",
})

#: I campi che portano davvero lo stato di *pagamento*, in ordine di autorità.
CAMPI_STATO = ("stato_pagamento", "stato", "payment_status")
#: I due booleani, storicamente scritti in coppia.
CAMPI_BOOLEANI = ("pagato", "paid")


def _parole(fattura: Mapping[str, Any]) -> set[str]:
    return {
        str(fattura.get(c)).strip().lower()
        for c in CAMPI_STATO
        if fattura.get(c) not in (None, "")
    }


def _un_booleano_dice_si(fattura: Mapping[str, Any]) -> bool:
    return any(fattura.get(c) is True or str(fattura.get(c)).lower() == "true"
               for c in CAMPI_BOOLEANI if fattura.get(c) is not None)


def e_pagata(fattura: Mapping[str, Any]) -> bool:
    """Vera se **un qualunque** campo dichiara il pagamento.

    Basta uno: l'archivio non è coerente, e una fattura marcata pagata da un
    solo modulo è comunque pagata. Il contrario — pretendere che tutti e
    cinque concordino — ne perderebbe 639.
    """
    if e_annullata(fattura):
        return False
    return _un_booleano_dice_si(fattura) or bool(_parole(fattura) & PAROLE_PAGATA)


def e_annullata(fattura: Mapping[str, Any]) -> bool:
    return bool(_parole(fattura) & PAROLE_ANNULLATA)


def e_parziale(fattura: Mapping[str, Any]) -> bool:
    return not e_pagata(fattura) and bool(_parole(fattura) & PAROLE_PARZIALE)


def stato_pagamento(fattura: Mapping[str, Any]) -> str:
    """Uno solo fra: pagata, parziale, da_pagare, annullata, da_verificare.

    `da_verificare` è la risposta onesta quando nessun campo dice niente: non
    si inventa `da_pagare`, perché un impegno che nessuno ha dichiarato non è
    un debito (le fatture fornitore non hanno scadenza: decide il titolare).
    """
    if e_annullata(fattura):
        return ANNULLATA
    if e_pagata(fattura):
        return PAGATA
    parole = _parole(fattura)
    if parole & PAROLE_PARZIALE:
        return PARZIALE
    if parole & PAROLE_DA_PAGARE:
        return DA_PAGARE
    return DA_VERIFICARE


# ── gli stessi criteri, come filtro di query ─────────────────────────────
def _rami_pagata() -> list[Dict[str, Any]]:
    rami: list[Dict[str, Any]] = [{c: True} for c in CAMPI_BOOLEANI]
    rami += [{c: {"$in": sorted(PAROLE_PAGATA)}} for c in CAMPI_STATO]
    return rami


def _rami_annullata() -> list[Dict[str, Any]]:
    return [{c: {"$in": sorted(PAROLE_ANNULLATA)}} for c in CAMPI_STATO]


#: Le fatture su cui c'è ancora da pagare: né pagate né annullate.
#: Sostituisce `{"pagato": {"$ne": True}}`, che su un campo assente passa sempre.
FILTRO_NON_PAGATE: Dict[str, Any] = {"$nor": _rami_pagata() + _rami_annullata()}

#: Le fatture pagate, comunque sia scritto.
FILTRO_PAGATE: Dict[str, Any] = {"$or": _rami_pagata()}

#: Le annullate o stornate: non entrano né di qua né di là.
FILTRO_ANNULLATE: Dict[str, Any] = {"$or": _rami_annullata()}


def con_non_pagate(filtro: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """Aggiunge «non pagata» a un filtro che ha già i suoi criteri.

    Si usa così invece di scrivere a mano un `$and`, perché due `$nor` nello
    stesso dizionario si sovrascriverebbero in silenzio.
    """
    base = dict(filtro or {})
    if not base:
        return dict(FILTRO_NON_PAGATE)
    return {"$and": [base, dict(FILTRO_NON_PAGATE)]}
