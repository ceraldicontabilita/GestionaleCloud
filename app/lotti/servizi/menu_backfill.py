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
non e' mai stato deciso (vedi ``menu_bridge.prezzo_per_menu``). Il conteggio
``senza_prezzo`` (e ``nascoste_per_prezzo``) e' piu' grave: sono le ricette
che non hanno **nessuno** dei due prezzi e che quindi il ponte pubblica
nascoste, perche' una riga senza prezzo nel Menu sarebbe ordinabile a 0 euro.

``troncato`` dice se il giro si e' fermato al tetto di ``LIMITE_RICETTE``:
senza questo campo un backfill parziale si sarebbe dichiarato «completato».
"""
from __future__ import annotations

import asyncio
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

    # Prefetch unico: una sola lettura della collezione, poi si lavora in
    # memoria. Si legge una riga oltre il tetto solo per accorgersi del
    # troncamento: senza, un archivio piu' grande di LIMITE_RICETTE avrebbe
    # riportato "completato" su un giro parziale.
    ricette: List[Dict[str, Any]] = await db.ricette.find(
        {}, PROIEZIONE).to_list(LIMITE_RICETTE + 1)
    troncato = len(ricette) > LIMITE_RICETTE
    if troncato:
        ricette = ricette[:LIMITE_RICETTE]
    totale = len(ricette)

    ricette_ignorate = 0
    if troncato:
        try:
            ricette_ignorate = max(await db.ricette.count_documents({}) - totale, 0)
        except Exception:  # noqa: BLE001 - il conteggio e' informativo
            logger.warning("Ripubblicazione Menu: conteggio ricette non disponibile")

    senza_prezzo_tavolo = [
        {"id": r.get("id"), "nome": r.get("nome")}
        for r in ricette if menu_bridge.prezzo_menu(r.get("prezzo_tavolo")) is None
    ]
    # Nessuno dei due prezzi: il ponte le pubblica NASCOSTE (una riga senza
    # prezzo sarebbe ordinabile a 0 euro). Il titolare deve vedere quali sono.
    senza_prezzo = [
        {"id": r.get("id"), "nome": r.get("nome"),
         "menu_pubblico": bool(r.get("menu_pubblico"))}
        for r in ricette if menu_bridge.prezzo_per_menu(r)[0] is None
    ]
    visibili = sum(1 for r in ricette if r.get("menu_pubblico"))

    base: Dict[str, Any] = {
        "ok": True,
        "dry_run": dry_run,
        "menu_configurato": menu_bridge.menu_configurato(),
        "ricette_totali": totale,
        "troncato": troncato,
        "limite_ricette": LIMITE_RICETTE,
        "ricette_ignorate": ricette_ignorate,
        "visibili": visibili,
        "nascoste": totale - visibili,
        "senza_prezzo_tavolo": len(senza_prezzo_tavolo),
        "campioni_senza_prezzo_tavolo": senza_prezzo_tavolo[:MAX_CAMPIONI],
        "senza_prezzo": len(senza_prezzo),
        "campioni_senza_prezzo": senza_prezzo[:MAX_CAMPIONI],
    }

    if dry_run:
        return base

    if not menu_bridge.menu_configurato():
        # Nessuna chiamata parte: il ponte direbbe "non_configurato" 500 volte.
        return {**base, "pubblicate": 0, "aggiornate": 0, "errori": 0,
                "nascoste_per_prezzo": 0, "campioni_nascoste_per_prezzo": [],
                "esito": "non_configurato"}

    pubblicate = aggiornate = errori = nascoste_per_prezzo = 0
    campioni_errori: List[Dict[str, Any]] = []
    campioni_nascoste_per_prezzo: List[Dict[str, Any]] = []

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
        # Il titolare aveva spuntato «inserisci in menu» ma manca il prezzo:
        # la riga resta nascosta e questo e' il posto dove lo legge.
        if esito.get("motivo_nascosto") == "prezzo_assente":
            nascoste_per_prezzo += 1
            if len(campioni_nascoste_per_prezzo) < MAX_CAMPIONI:
                campioni_nascoste_per_prezzo.append({
                    "id": ricetta.get("id"), "nome": ricetta.get("nome"),
                })
        if on_progress and (indice % 25 == 0 or indice == totale):
            await on_progress(indice, totale)

    return {**base, "pubblicate": pubblicate, "aggiornate": aggiornate,
            "errori": errori, "campioni_errori": campioni_errori,
            "nascoste_per_prezzo": nascoste_per_prezzo,
            "campioni_nascoste_per_prezzo": campioni_nascoste_per_prezzo}


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
# Riferimento al task in volo: senza, il garbage collector puo' raccogliere il
# task a meta' giro (asyncio tiene solo una reference debole), il `finally` che
# azzera `_in_corso` non gira mai e ogni avvio successivo risponde
# "Ripubblicazione gia' in corso" fino al riavvio del processo. Stesso schema
# di `app/services/registrazione_contabile.py::_pregresso_task`.
_task_in_corso: Optional["asyncio.Task"] = None


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
        # «completato» non deve mentire: oltre LIMITE_RICETTE il giro e' parziale.
        stato = "completato_parziale" if risultato.get("troncato") else "completato"
        await _salva_stato(db, stato=stato, terminato_at=_now(), risultato=risultato)
    except Exception as exc:  # noqa: BLE001 - lo stato deve restare leggibile
        logger.exception("Ripubblicazione ricette nel Menu interrotta")
        await _salva_stato(db, stato="errore", errore=str(exc), terminato_at=_now())
    finally:
        _in_corso = False


def avvia_ripubblicazione_in_background(db) -> bool:
    """Risponde subito; l'avanzamento si segue con ``stato_ripubblicazione_menu``.
    Un secondo avvio mentre e' in corso non parte (ritorna ``False``)."""
    global _in_corso, _task_in_corso

    if _in_corso:
        return False
    # Alzato qui e non dentro la coroutine: `create_task` la mette solo in
    # coda, quindi due POST ravvicinati partivano entrambi.
    _in_corso = True
    _task_in_corso = asyncio.create_task(_ripubblica_in_background(db))
    return True
