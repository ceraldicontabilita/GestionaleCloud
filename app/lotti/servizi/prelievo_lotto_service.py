"""Prelievo canonico di un lotto utilizzabile per banco o recupero."""

from datetime import datetime, timezone

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from app.lotti.db import database as db
from app.lotti.servizi.lotto_arricchimento_service import calcola_stato_scadenza


async def preleva_lotto(lotto_id: str, quantita: float | None, tipo: str,
                       operation_id: str | None = None) -> dict:
    """Scala una quantità una sola volta; un retry riprende gli effetti successivi."""
    if tipo not in {"banco", "recupero"}:
        raise ValueError("Tipo prelievo non supportato")
    chiave = f"{tipo}_{operation_id}" if operation_id else None
    if chiave:
        precedente = await db.operazioni_idempotenti.find_one({"_id": chiave})
        if precedente:
            if precedente.get("lotto_id") not in (None, lotto_id):
                raise HTTPException(409, "ID operazione già usato per un altro lotto")
            if "quantita_richiesta" in precedente and precedente["quantita_richiesta"] != quantita:
                raise HTTPException(409, "ID operazione già usato con una quantità diversa")
            if precedente.get("risultato"):
                return {"risultato": precedente["risultato"]}
            if precedente.get("stato") == "scalato":
                return {"lotto": precedente["lotto"],
                        "quantita": precedente["quantita"],
                        "residua": precedente["residua"], "chiave": chiave}
            raise HTTPException(409, "Operazione in corso: riprovare tra poco")

    lotto = await db.lotti.find_one({"id": lotto_id}, {"_id": 0})
    if not lotto:
        raise HTTPException(404, "Lotto non trovato")
    if lotto.get("stato") == "bloccato_richiamo":
        raise HTTPException(423, "Lotto bloccato da richiamo")
    giorni = calcola_stato_scadenza(lotto.get("data_scadenza"))["giorni_alla_scadenza"]
    if giorni is None or giorni < 0:
        raise HTTPException(409, "Lotto scaduto o scadenza da verificare: non utilizzare")
    disponibile = lotto.get("quantita") or 0
    if lotto.get("consumato") or lotto.get("esaurito") or lotto.get("stato") in {"smaltito", "esaurito", "scaduto", "annullato"} or disponibile <= 0:
        raise HTTPException(409, "Lotto non disponibile")
    prelevata = disponibile if quantita is None else quantita
    if prelevata <= 0 or prelevata > disponibile or (tipo == "banco" and not float(prelevata).is_integer()):
        raise HTTPException(400, f"Quantità non valida: disponibili {disponibile}")
    residua = round(disponibile - prelevata, 3)
    if chiave:
        try:
            await db.operazioni_idempotenti.insert_one({
                "_id": chiave, "tipo": tipo, "lotto_id": lotto_id,
                "quantita_richiesta": quantita, "stato": "riservato",
                "creato": datetime.now(timezone.utc).isoformat(),
            })
        except DuplicateKeyError:
            return await preleva_lotto(lotto_id, quantita, tipo, operation_id)

    modifica = {"quantita": residua}
    if residua == 0:
        modifica.update({"consumato": True, "data_consumo": datetime.now(timezone.utc).isoformat()})
    filtro = {"id": lotto_id, "quantita": disponibile,
              "consumato": {"$ne": True}, "esaurito": {"$ne": True},
              "stato": lotto.get("stato"), "data_scadenza": lotto.get("data_scadenza")}
    try:
        esito = await db.lotti.update_one(filtro, {"$set": modifica})
    except Exception:
        if chiave:
            await db.operazioni_idempotenti.delete_one({"_id": chiave, "stato": "riservato"})
        raise
    if esito.matched_count != 1:
        if chiave:
            await db.operazioni_idempotenti.delete_one({"_id": chiave, "stato": "riservato"})
        raise HTTPException(409, "Lotto cambiato durante il prelievo: aggiornare la scheda")

    if chiave:
        await db.operazioni_idempotenti.update_one(
            {"_id": chiave}, {"$set": {"stato": "scalato", "lotto": lotto,
                                       "quantita": prelevata, "residua": residua}})
    return {"lotto": lotto, "quantita": prelevata, "residua": residua, "chiave": chiave}


async def conclude_prelievo(chiave: str | None, risultato: dict) -> None:
    if chiave:
        await db.operazioni_idempotenti.update_one(
            {"_id": chiave}, {"$set": {"stato": "completo", "risultato": risultato}})
