"""Ricerca di tracciabilita': per ingrediente, fornitore, fattura o lotto.

«Con quella farina quanti prodotti diversi ho fatto» e «da dove veniva la
farina di questo dolce» sono la stessa domanda letta nei due versi, ed e' la
domanda che fa un'ispezione. Qui si risponde a tutte e due.

Il motore che legge le origini sta in `servizi/tracciabilita.py`: qui ci sono
solo le rotte e il modo di contare.
"""

from fastapi import APIRouter, HTTPException, Query

from app.lotti.db import database as db
from app.lotti.servizi.tracciabilita import corrisponde, normalizza, origini_del_lotto

router = APIRouter(prefix="/tracciabilita", tags=["Tracciabilità"])

# I lotti di produzione sono poche migliaia: si leggono tutti e si filtra in
# memoria, perche' le origini vivono dentro due strutture diverse (lo scarico
# e le righe di testo) e nessuna query sola le copre entrambe.
_TETTO_LOTTI = 5000

_PROIEZIONE = {
    "_id": 0, "id": 1, "numero_lotto": 1, "prodotto": 1, "data_produzione": 1,
    "data_scadenza": 1, "quantita": 1, "unita_misura": 1, "operatore_nome": 1,
    "ingredienti_dettaglio": 1, "lotti_fornitori": 1, "consumato": 1,
}


async def _lotti_di_produzione() -> list:
    return await db.lotti.find({}, _PROIEZIONE).to_list(_TETTO_LOTTI)


def _scheda_lotto(lotto: dict, origini: list) -> dict:
    return {
        "id": lotto.get("id", ""),
        "numero_lotto": lotto.get("numero_lotto", ""),
        "prodotto": lotto.get("prodotto", ""),
        "data_produzione": lotto.get("data_produzione", ""),
        "data_scadenza": lotto.get("data_scadenza", ""),
        "quantita": lotto.get("quantita"),
        "unita_misura": lotto.get("unita_misura", ""),
        "consumato": bool(lotto.get("consumato")),
        "origini": origini,
    }


async def _cerca(*, ingrediente="", fornitore="", fattura="") -> dict:
    """Il corpo comune delle tre ricerche: cambia solo cosa si chiede."""
    trovati, prodotti, fornitori, fatture, ingredienti = [], set(), set(), set(), set()
    prove_esatte = 0

    for lotto in await _lotti_di_produzione():
        origini = [
            o for o in origini_del_lotto(lotto)
            if corrisponde(o, ingrediente=ingrediente, fornitore=fornitore, fattura=fattura)
        ]
        if not origini:
            continue
        trovati.append(_scheda_lotto(lotto, origini))
        if lotto.get("prodotto"):
            prodotti.add(normalizza(lotto["prodotto"]))
        for o in origini:
            if o.get("fornitore"):
                fornitori.add(o["fornitore"])
            if o.get("fattura"):
                fatture.add(o["fattura"])
            if o.get("ingrediente"):
                ingredienti.add(o["ingrediente"])
            if o.get("origine") == "scarico":
                prove_esatte += 1

    trovati.sort(key=lambda l: l.get("data_produzione", ""), reverse=True)
    return {
        "lotti_di_produzione": len(trovati),
        # La domanda del titolare: «quanti prodotti DIVERSI ho fatto».
        "prodotti_diversi": len(prodotti),
        "fornitori": sorted(fornitori),
        "fatture": sorted(fatture),
        "ingredienti": sorted(ingredienti),
        # Quante origini sono il collegamento esatto dello scarico e quante
        # una ricostruzione dall'etichetta: davanti a un'ispezione la
        # differenza conta, e non va nascosta dentro un totale unico.
        "origini_certe": prove_esatte,
        "risultati": trovati,
    }


@router.get("/ingrediente")
async def per_ingrediente(nome: str = Query(..., min_length=2)):
    """In quali prodotti finiti e' finito questo ingrediente.

    Cerca per pezzo di nome: «farina» trova «FARINA 00 MANITOBA KG 25», e
    «uova» trova i tuorli solo se il nome li chiama cosi' — il nome e' quello
    che ha scritto il fornitore in fattura.
    """
    return {"cerca": {"ingrediente": nome}, **await _cerca(ingrediente=nome)}


@router.get("/fornitore")
async def per_fornitore(nome: str = Query(..., min_length=2)):
    """Tutto quello che e' stato prodotto con la merce di questo fornitore."""
    return {"cerca": {"fornitore": nome}, **await _cerca(fornitore=nome)}


@router.get("/fattura")
async def per_fattura(numero: str = Query(..., min_length=1)):
    """Tutto quello che e' stato prodotto con la merce di questa fattura.

    Il numero si confronta intero: «1/196084» non deve uscire cercando «6084».
    """
    return {"cerca": {"fattura": numero}, **await _cerca(fattura=numero)}


@router.get("/lotto/{numero_lotto}")
async def origini_di_un_lotto(numero_lotto: str):
    """Il verso opposto: da un lotto prodotto, da dove viene ogni ingrediente."""
    lotto = await db.lotti.find_one(
        {"$or": [{"numero_lotto": numero_lotto}, {"id": numero_lotto}]}, _PROIEZIONE
    )
    if not lotto:
        raise HTTPException(status_code=404, detail=f"Lotto «{numero_lotto}» non trovato")

    origini = origini_del_lotto(lotto)
    senza = [o["ingrediente"] for o in origini if o.get("senza_origine")]
    return {
        **_scheda_lotto(lotto, origini),
        "ingredienti_totali": len(origini),
        "origini_certe": sum(1 for o in origini if o.get("origine") == "scarico"),
        "origini_ricostruite": sum(1 for o in origini if o.get("origine") == "testo"
                                   and not o.get("senza_origine")),
        # Il buco da conoscere prima di essere interrogati.
        "senza_origine": senza,
    }


@router.get("/senza-origine")
async def ingredienti_senza_origine(limite: int = Query(200, ge=1, le=2000)):
    """Gli ingredienti che non si sa da dove vengono.

    Non e' una curiosita': e' il punto in cui la catena si spezza. Un lotto
    con un ingrediente senza fornitore non e' rintracciabile all'indietro, e
    davanti a un richiamo non si puo' rispondere.
    """
    # FastAPI risolve i default `Query(...)` solo passando dalla rotta: chiamata
    # da codice (test, script, un altro servizio) `limite` resta l'oggetto
    # Query e il taglio finale esplode. Vale per ogni endpoint richiamato
    # direttamente, e qui fallisce **dopo** aver gia' fatto tutto il lavoro.
    if not isinstance(limite, int):
        limite = 200

    buchi, per_ingrediente = [], {}
    for lotto in await _lotti_di_produzione():
        mancanti = [o for o in origini_del_lotto(lotto) if o.get("senza_origine")]
        if not mancanti:
            continue
        buchi.append({
            "numero_lotto": lotto.get("numero_lotto", ""),
            "prodotto": lotto.get("prodotto", ""),
            "data_produzione": lotto.get("data_produzione", ""),
            "ingredienti": [o["ingrediente"] for o in mancanti],
        })
        for o in mancanti:
            chiave = o["ingrediente"]
            per_ingrediente[chiave] = per_ingrediente.get(chiave, 0) + 1

    buchi.sort(key=lambda b: b.get("data_produzione", ""), reverse=True)
    classifica = sorted(per_ingrediente.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "lotti_coinvolti": len(buchi),
        "ingredienti_distinti": len(per_ingrediente),
        "piu_frequenti": [{"ingrediente": k, "lotti": n} for k, n in classifica[:25]],
        "lotti": buchi[:limite],
    }
