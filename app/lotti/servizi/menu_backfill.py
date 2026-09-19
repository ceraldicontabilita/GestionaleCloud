"""Ripubblicazione in massa delle ricette di Lotti nel Menu digitale.

Il ponte (``app/lotti/servizi/menu_bridge.py``) scatta solo al salvataggio di
una ricetta: le ricette gia' in archivio prima che il ponte esistesse
(03/09/2026) non sono mai arrivate nel Menu. Questo e' il recupero del
pregresso, con lo stesso schema degli altri arretrati del gestionale
(``app/services/registrazione_contabile.py``,
``app/services/categorizzazione_movimenti.py``): **prefetch unico** della
collezione, esecuzione **in background** con stato in ``sistema_stato`` e un
endpoint di stato per il polling, perche' oltre i 5 minuti il proxy di Render
taglia la richiesta.

Due garanzie, entrambe coperte dai test:

* **idempotente** — il ponte scrive per ``lotti_ref = "ricetta:<id>"``, quindi
  il secondo giro aggiorna le stesse righe e non ne crea nemmeno una in piu';
* **non pubblica nulla di nascosto** — ``visible`` resta la scelta del
  titolare (``menu_pubblico``): una ricetta senza quel flag arriva nel Menu
  nascosta, il backfill non la mostra mai ai clienti.

Il conteggio ``senza_prezzo_tavolo`` e' il modo per vedere quante ricette
stanno ancora esponendo nel Menu il prezzo al banco perche' quello al tavolo
non e' mai stato deciso (vedi ``menu_bridge.prezzo_per_menu``).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("uvicorn.error")

_STATO_KEY = "ripubblicazione_menu_lotti"

# Solo i campi che il ponte legge davvero: la ricetta intera porta con se'
# ingredienti, componenti, procedimento e schede, inutili qui e pesanti su
# centinaia di righe.
PROIEZIONE = {
    "_id": 0, "id": 1, "nome": 1, "reparto": 1,
    "prezzo_vendita": 1, "prezzo_tavolo": 1, "descrizione": 1,
    "allergeni": 1, "allergeni_auto": 1, "foto_url": 1,
    "menu_pubblico": 1, "menu_category_id": 1, "menu_subcategory_id": 1,
}

LIMITE_RICETTE = 5000
MAX_CAMPIONI = 50


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def ripubblica_menu(
    db, *, dry_run: bool = False, on_progress=None,
) -> Dict[str, Any]:
    """Rimanda al Menu tutte le ricette di Lotti.

    Con ``dry_run=True`` non scrive nulla: e' una simulazione che conta cosa
    verrebbe pubblicato, quante righe resterebbero nascoste e quante ricette
    non hanno ancora un prezzo al tavolo.
    """
    from app.lotti.servizi import menu_bridge

    # Prefetch unico: una sola lettura della collezione, poi si lavora in memoria.
    ricette: List[Dict[str, Any]] = await db.ricette.find({}, PROIEZIONE).to_list(LIMITE_RICETTE)
    totale = len(ricette)

    senza_prezzo_tavolo = [
        {"id": r.get("id"), "nome": r.get("nome")}
        for r in ricette if not r.get("prezzo_tavolo")
    ]
    visibili = sum(1 for r in ricette if r.get("menu_pubblico"))

    base: Dict[str, Any] = {
        "ok": True,
        "dry_run": dry_run,
        "menu_configurato": menu_bridge.menu_configurato(),
        "ricette_totali": totale,
        "visibili": visibili,
        "nascoste": totale - visibili,
        "senza_prezzo_tavolo": len(senza_prezzo_tavolo),
        "campioni_senza_prezzo_tavolo": senza_prezzo_tavolo[:MAX_CAMPIONI],
    }

    if dry_run:
        return base

    if not menu_bridge.menu_configurato():
        # Nessuna chiamata parte: il ponte direbbe "non_configurato" 500 volte.
        return {**base, "pubblicate": 0, "aggiornate": 0, "errori": 0,
                "esito": "non_configurato"}

    pubblicate = aggiornate = errori = 0
    campioni_errori: List[Dict[str, Any]] = []

    for indice, ricetta in enumerate(ricette, start=1):
        esito = await menu_bridge.pubblica_prodotto_nel_menu(
            ricetta, visibile=bool(ricetta.get("menu_pubblico")), db=db,
        )
        stato = esito.get("esito")
        if stato == "pubblicato":
            pubblicate += 1
        elif stato == "aggiornato":
            aggiornate += 1
        else:
            errori += 1
            if len(campioni_errori) < MAX_CAMPIONI:
                campioni_errori.append({
                    "id": ricetta.get("id"), "nome": ricetta.get("nome"),
                    "esito": stato, "errore": esito.get("errore"),
                })
        if on_progress and (indice % 25 == 0 or indice == totale):
            await on_progress(indice, totale)

    return {**base, "pubblicate": pubblicate, "aggiornate": aggiornate,
            "errori": errori, "campioni_errori": campioni_errori}


# ================== Stato ed esecuzione in background ==================

async def stato_ripubblicazione_menu(db) -> Dict[str, Any]:
    stato = await db.sistema_stato.find_one({"chiave": _STATO_KEY}, {"_id": 0}) or {}
    stato.pop("chiave", None)
    return stato


async def _salva_stato(db, **campi: Any) -> None:
    campi["aggiornato_at"] = _now()
    await db.sistema_stato.update_one(
        {"chiave": _STATO_KEY}, {"$set": {"chiave": _STATO_KEY, **campi}}, upsert=True,
    )


_in_corso = False


def ripubblicazione_in_corso() -> bool:
    return _in_corso


async def _ripubblica_in_background(db) -> None:
    global _in_corso
    _in_corso = True
    await _salva_stato(db, stato="in_corso", avviato_at=_now(), risultato=None,
                       errore=None, avanzamento=None)

    async def progresso(fatte: int, totale: int) -> None:
        await _salva_stato(db, avanzamento={"fatte": fatte, "totale": totale})

    try:
        risultato = await ripubblica_menu(db, dry_run=False, on_progress=progresso)
        await _salva_stato(db, stato="completato", terminato_at=_now(), risultato=risultato)
    except Exception as exc:  # noqa: BLE001 - lo stato deve restare leggibile
        logger.exception("Ripubblicazione ricette nel Menu interrotta")
        await _salva_stato(db, stato="errore", errore=str(exc), terminato_at=_now())
    finally:
        _in_corso = False


def avvia_ripubblicazione_in_background(db) -> bool:
    """Risponde subito; l'avanzamento si segue con ``stato_ripubblicazione_menu``.
    Un secondo avvio mentre e' in corso non parte (ritorna ``False``)."""
    import asyncio

    if _in_corso:
        return False
    asyncio.create_task(_ripubblica_in_background(db))
    return True
