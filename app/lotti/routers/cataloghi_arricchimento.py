"""Arricchimento persistente e riprendibile dei cataloghi fornitori.

Il catalogo resta immediatamente consultabile: questo worker completa in
background descrizione, confezione, codice e foto sullo stesso documento.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.lotti.auth import require_admin
from app.lotti.db import database as db
from app.lotti.routers.acquaviva import (
    _scarica_dettaglio_acquaviva,
    rileva_allergeni,
)
from app.lotti.routers.mepa import scrape_dettaglio_mepa
from app.lotti.routers.saima import scrape_dettaglio_saima_prodotto


router = APIRouter(prefix="/cataloghi-arricchimento", tags=["cataloghi_arricchimento"])
logger = logging.getLogger("uvicorn.error")

FONTI = ("acquaviva", "saima", "mepa")
VERSIONE_ARRICCHIMENTO = 1
CONCORRENZA_PER_FORNITORE = 4
DIMENSIONE_LOTTO = 40


def _ora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _collezione(fonte: str):
    if fonte == "acquaviva":
        return db.acquaviva_prodotti
    return db.dizionario_ingredienti


def _testo(value, massimo: int = 1000) -> str:
    return " ".join(str(value or "").split())[:massimo]


def _errore_testo(exc: BaseException) -> str:
    return (str(exc).strip() or type(exc).__name__)[:1000]


async def _salva_aggiornamenti(collection, aggiornamenti: list[tuple]) -> None:
    """Persistenza batch con retry solo per errori di trasporto transitori."""
    batch_updater = getattr(type(collection), "update_documents_by_id", None)
    if not callable(batch_updater):
        await asyncio.gather(*(
            collection.update_one({"_id": doc_id}, {"$set": campi})
            for doc_id, campi in aggiornamenti
        ))
        return

    for tentativo in range(1, 4):
        try:
            await batch_updater(collection, aggiornamenti)
            return
        except httpx.TransportError as exc:
            if tentativo == 3:
                raise
            attesa = tentativo * 2
            logger.warning(
                "[ARRICCHIMENTO] salvataggio batch non riuscito (%s); ritento tra %ss",
                _errore_testo(exc),
                attesa,
            )
            await asyncio.sleep(attesa)


async def _assicura_descrizioni_base(collection, fonte: str, prodotti: list[dict]) -> int:
    """Rende subito descrittiva ogni card usando la categoria ufficiale gia' acquisita."""
    aggiornamenti = []
    for prodotto in prodotti:
        if _testo(prodotto.get("descrizione"), 500):
            continue
        categoria = _testo(prodotto.get("categoria"), 300)
        if not categoria:
            continue
        descrizione = f"Categoria: {categoria}"
        campi = {
            "descrizione": descrizione,
            "arricchimento_base_fonte": "catalogo_ufficiale_fornitore",
            "arricchimento_base_il": _ora(),
        }
        aggiornamenti.append((prodotto["_id"], campi))
        # La lista corrente e' stata caricata prima dell'aggiornamento batch:
        # la allineiamo affinche' il dettaglio possa sostituire questa base.
        prodotto.update(campi)

    for inizio in range(0, len(aggiornamenti), 200):
        await _salva_aggiornamenti(collection, aggiornamenti[inizio:inizio + 200])
    return len(aggiornamenti)


def _normalizza_dettaglio(fonte: str, prodotto: dict, extra: dict) -> dict:
    """Converte i campi fonte nel formato unico letto dalle card."""
    aggiornamento = {}
    descrizione_lunga = _testo(extra.get("descrizione_lunga"), 1000)
    descrizione_breve = _testo(extra.get("descrizione"), 500)
    descrizione_esistente = _testo(prodotto.get("descrizione"), 500)

    if descrizione_lunga:
        aggiornamento["descrizione_lunga"] = descrizione_lunga
        # La card usa ``descrizione``. Una mera indicazione di confezione puo'
        # essere sostituita dalla descrizione ufficiale piu' informativa.
        if not descrizione_esistente or descrizione_esistente.lower().startswith(("confezione:", "categoria:")):
            aggiornamento["descrizione"] = descrizione_lunga[:500]
    elif descrizione_breve:
        aggiornamento["descrizione"] = descrizione_breve

    for campo in (
        "codice_articolo",
        "codice_verificato",
        "nome_verificato",
        "unita_confezione",
        "pz_confezione",
        "peso_g",
        "peso_lordo",
        "specifiche",
        "categoria_dettaglio",
    ):
        valore = extra.get(campo)
        if valore not in (None, "", {}, []):
            aggiornamento[campo] = valore

    immagine = _testo(extra.get("immagine_prodotto"), 2000)
    if immagine:
        aggiornamento["immagine_prodotto"] = immagine
        aggiornamento["immagine_url"] = immagine
        if fonte == "acquaviva":
            aggiornamento["foto_url"] = immagine

    descrizione_finale = aggiornamento.get("descrizione") or descrizione_esistente
    if descrizione_finale:
        aggiornamento["allergeni"] = rileva_allergeni(
            prodotto.get("nome", ""),
            descrizione_finale,
            prodotto.get("categoria", ""),
        )

    utile = bool(
        descrizione_finale
        or aggiornamento.get("codice_articolo")
        or aggiornamento.get("unita_confezione")
        or aggiornamento.get("immagine_prodotto")
    )
    aggiornamento.update({
        "arricchimento_fonte": "pagina_ufficiale_fornitore",
        "arricchimento_esito": "completo" if utile else "verificato_senza_dettagli",
        "arricchito_il": _ora(),
    })
    # Una risposta vuota puo' essere un errore temporaneo del sito fornitore.
    # La versione viene quindi marcata solo quando e' stato realmente verificato
    # almeno un dato utile; al prossimo avvio le schede vuote saranno ritentate.
    if utile:
        aggiornamento["arricchimento_version"] = VERSIONE_ARRICCHIMENTO
    return aggiornamento


async def _scarica_dettaglio(
    fonte: str,
    prodotto: dict,
    client: httpx.AsyncClient,
) -> dict:
    if fonte == "acquaviva":
        link = prodotto.get("link_prodotto") or ""
        return await _scarica_dettaglio_acquaviva(client, link) if link else {}
    if fonte == "saima":
        codice = prodotto.get("codice_articolo") or ""
        return await scrape_dettaglio_saima_prodotto(codice, client=client) if codice else {}
    link = prodotto.get("link_prodotto") or ""
    return await scrape_dettaglio_mepa(link, client=client) if link else {}


async def _arricchisci_catalogo(
    fonte: str,
    *,
    force: bool = False,
    limit: int = 0,
) -> dict:
    if fonte not in FONTI:
        raise ValueError(f"Fonte non supportata: {fonte}")

    collection = _collezione(fonte)
    query = {"fonte": fonte}
    prodotti = await collection.find(query).sort("_id", 1).to_list(10_000)
    descrizioni_base = await _assicura_descrizioni_base(collection, fonte, prodotti)
    totale_catalogo = len(prodotti)
    da_elaborare = [
        p for p in prodotti
        if force or p.get("arricchimento_version") != VERSIONE_ARRICCHIMENTO
    ]
    if limit:
        da_elaborare = da_elaborare[:limit]

    stato_id = f"arricchimento_catalogo_{fonte}"
    contatori = {
        "elaborati": 0,
        "arricchiti": 0,
        "senza_dati": 0,
        "errori": 0,
    }
    await db.sync_status.update_one(
        {"_id": stato_id},
        {"$set": {
            "fonte": fonte,
            "stato": "in_corso",
            "iniziato_il": _ora(),
            "heartbeat_il": _ora(),
            "totale_catalogo": totale_catalogo,
            "totale_da_elaborare": len(da_elaborare),
            "versione": VERSIONE_ARRICCHIMENTO,
            "descrizioni_base_aggiunte": descrizioni_base,
            "errore": "",
            **contatori,
        }},
        upsert=True,
    )

    semaforo = asyncio.Semaphore(CONCORRENZA_PER_FORNITORE)
    timeout = httpx.Timeout(30.0, connect=15.0)
    limits = httpx.Limits(max_connections=CONCORRENZA_PER_FORNITORE + 1)

    async def elabora(prodotto: dict, client: httpx.AsyncClient) -> tuple[str, dict | None]:
        try:
            # Il semaforo limita solo le richieste ai siti dei fornitori. La
            # scrittura sul document store ha gia' un lock proprio e non deve
            # tenere inutilmente occupato uno slot HTTP.
            async with semaforo:
                extra = await _scarica_dettaglio(fonte, prodotto, client)
            aggiornamento = _normalizza_dettaglio(fonte, prodotto, extra)
            esito = "arricchiti" if aggiornamento["arricchimento_esito"] == "completo" else "senza_dati"
            return esito, {"_id": prodotto["_id"], "campi": aggiornamento}
        except Exception as exc:
            logger.warning(
                "[ARRICCHIMENTO %s] prodotto %s: %s",
                fonte,
                prodotto.get("nome") or prodotto.get("_id"),
                    _errore_testo(exc),
            )
            return "errore", None

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            limits=limits,
        ) as client:
            for inizio in range(0, len(da_elaborare), DIMENSIONE_LOTTO):
                lotto = da_elaborare[inizio:inizio + DIMENSIONE_LOTTO]
                risultati = await asyncio.gather(*(elabora(p, client) for p in lotto))
                aggiornamenti = [
                    (item["_id"], item["campi"])
                    for _, item in risultati
                    if item is not None
                ]
                await _salva_aggiornamenti(collection, aggiornamenti)
                for esito, _ in risultati:
                    contatori["elaborati"] += 1
                    contatori[esito] += 1
                await db.sync_status.update_one(
                    {"_id": stato_id},
                    {"$set": {
                        **contatori,
                        "rimanenti": len(da_elaborare) - contatori["elaborati"],
                        "heartbeat_il": _ora(),
                    }},
                )

        fine = _ora()
        rimanenti = await collection.count_documents({
            "fonte": fonte,
            "arricchimento_version": {"$ne": VERSIONE_ARRICCHIMENTO},
        })
        if contatori["errori"]:
            stato_finale = "completato_con_errori"
        elif rimanenti:
            stato_finale = "completato_con_schede_da_riprovare"
        else:
            stato_finale = "completato"
        await db.sync_status.update_one(
            {"_id": stato_id},
            {"$set": {
                **contatori,
                "stato": stato_finale,
                "completato_il": fine,
                "heartbeat_il": fine,
                "rimanenti": rimanenti,
            }},
        )
        await db.log_scraping.insert_one({
            "fonte": f"arricchimento_{fonte}",
            "data": fine,
            "versione": VERSIONE_ARRICCHIMENTO,
            "totale_catalogo": totale_catalogo,
            "totale_elaborato": len(da_elaborare),
            **contatori,
        })
        return {"fonte": fonte, "stato": stato_finale, **contatori}
    except Exception as exc:
        await db.sync_status.update_one(
            {"_id": stato_id},
            {"$set": {
                **contatori,
                "stato": "errore",
                "errore": _errore_testo(exc),
                "completato_il": _ora(),
            }},
        )
        logger.exception("[ARRICCHIMENTO %s] processo fallito", fonte)
        raise


def _esecuzione_recente(stato: Optional[dict]) -> bool:
    if not stato or stato.get("stato") != "in_corso":
        return False
    riferimento = stato.get("heartbeat_il") or stato.get("iniziato_il")
    if not riferimento:
        return False
    try:
        momento = datetime.fromisoformat(str(riferimento).replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - momento < timedelta(minutes=20)
    except ValueError:
        return False


@router.post("/avvia")
async def avvia_arricchimento(
    background_tasks: BackgroundTasks,
    fonte: str = Query(...),
    force: bool = Query(False),
    limit: int = Query(0, ge=0, le=10_000),
    _admin=Depends(require_admin),
):
    if fonte not in FONTI:
        raise HTTPException(400, f"Fonte non supportata: {fonte}")
    stato_id = f"arricchimento_catalogo_{fonte}"
    stato = await db.sync_status.find_one({"_id": stato_id}, {"_id": 0})
    if _esecuzione_recente(stato):
        return {"avviato": False, "messaggio": f"Arricchimento {fonte} gia' in corso"}
    # Prenota il worker prima di rispondere: due tocchi ravvicinati non devono
    # avviare due scansioni concorrenti dello stesso catalogo.
    await db.sync_status.update_one(
        {"_id": stato_id},
        {"$set": {
            "fonte": fonte,
            "stato": "in_corso",
            "iniziato_il": _ora(),
            "heartbeat_il": _ora(),
            "versione": VERSIONE_ARRICCHIMENTO,
            "errore": "",
        }},
        upsert=True,
    )
    background_tasks.add_task(_arricchisci_catalogo, fonte, force=force, limit=limit)
    return {
        "avviato": True,
        "fonte": fonte,
        "force": force,
        "limit": limit,
        "versione": VERSIONE_ARRICCHIMENTO,
    }


@router.get("/stato")
async def stato_arricchimento(fonte: str = Query(...)):
    if fonte not in FONTI:
        raise HTTPException(400, f"Fonte non supportata: {fonte}")
    stato = await db.sync_status.find_one(
        {"_id": f"arricchimento_catalogo_{fonte}"},
        {"_id": 0},
    )
    collection = _collezione(fonte)
    totale = await collection.count_documents({"fonte": fonte})
    completati = await collection.count_documents({
        "fonte": fonte,
        "arricchimento_version": VERSIONE_ARRICCHIMENTO,
    })
    return {
        "fonte": fonte,
        "totale_catalogo": totale,
        "schede_verificate": completati,
        "rimanenti": max(totale - completati, 0),
        "stato": stato or {"stato": "mai_eseguito"},
    }
