"""Rettifica reversibile dei lotti creati per errore, con storia HACCP."""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from app.lotti.db import database as db
from app.lotti.servizi.movimenti_lotto_service import registra_movimento


async def _lotto(lotto_id: str) -> dict:
    lotto = await db.lotti.find_one({"$or": [{"id": lotto_id}, {"lotto_id": lotto_id}]})
    if not lotto:
        raise HTTPException(404, "Lotto non trovato")
    return lotto


async def _verifica_non_utilizzato(lotto: dict) -> None:
    identita = [x for x in (lotto.get("id"), lotto.get("lotto_id")) if x]
    riferimenti = [*identita, *([lotto["numero_lotto"]] if lotto.get("numero_lotto") else [])]
    if await db.vendite_banco.count_documents({"lotto_id": {"$in": identita}}):
        raise HTTPException(409, "Lotto già inviato al banco: correggere tramite rettifica")
    if await db.movimenti_lotto.count_documents({
        "lotto_id": {"$in": identita},
        "tipo_evento": {"$in": ["banco", "uso", "recupero", "rientro_invenduto"]},
    }):
        raise HTTPException(409, "Lotto già utilizzato: correggere tramite rettifica")
    if await db.lotti.count_documents({
        "lotti_componenti": {"$elemMatch": {"$or": [
            {"lotto_id": {"$in": riferimenti}},
            {"numero_lotto": {"$in": riferimenti}},
        ]}},
    }):
        raise HTTPException(409, "Lotto usato in altra produzione: correggere tramite rettifica")


async def annulla_lotto(lotto_id: str, motivo: str, actor: dict) -> dict:
    lotto = await _lotto(lotto_id)
    if lotto.get("stato") != "annullato":
        if lotto.get("stato") == "bloccato_richiamo":
            raise HTTPException(423, "Lotto bloccato da richiamo: serve la gestione del richiamo")
        if lotto.get("consumato") or lotto.get("esaurito") or (lotto.get("quantita") or 0) <= 0:
            raise HTTPException(409, "Lotto già esaurito: correggere tramite rettifica")
        await _verifica_non_utilizzato(lotto)
        operazione = str(uuid.uuid4())
        modifica = {
            "stato": "annullato", "esaurito": True, "quantita": 0,
            "quantita_pre_annullamento": lotto["quantita"],
            "stato_pre_annullamento": lotto.get("stato") or "attivo",
            "esaurito_pre_annullamento": bool(lotto.get("esaurito")),
            "motivo_annullamento": motivo,
            "annullato_il": datetime.now(timezone.utc).isoformat(),
            "annullato_da_id": actor["id"], "annullato_da_nome": actor["nome"],
            "annullamento_operazione_id": operazione,
        }
        esito = await db.lotti.update_one(
            {"_id": lotto["_id"], "stato": {"$ne": "annullato"},
             "quantita": lotto["quantita"]}, {"$set": modifica})
        if esito.matched_count != 1:
            raise HTTPException(409, "Lotto cambiato: aggiornare la scheda")
        lotto.update(modifica)
    elif lotto.get("motivo_annullamento") != motivo:
        raise HTTPException(409, "Lotto già annullato con un'altra motivazione")

    await registra_movimento(
        lotto.get("id") or lotto_id, "annullamento",
        numero_lotto=lotto.get("numero_lotto") or lotto.get("lotto_id") or "",
        quantita=lotto.get("quantita_pre_annullamento"),
        operatore_id=lotto["annullato_da_id"], operatore_nome=lotto["annullato_da_nome"],
        motivo=lotto["motivo_annullamento"],
        operation_id=lotto["annullamento_operazione_id"],
    )
    return {"ok": True, "lotto_id": lotto.get("id") or lotto_id, "stato": "annullato"}


async def ripristina_lotto(lotto_id: str, motivo: str, actor: dict) -> dict:
    lotto = await _lotto(lotto_id)
    if lotto.get("stato") == "annullato":
        await _verifica_non_utilizzato(lotto)
        operazione = str(uuid.uuid4())
        modifica = {
            "stato": lotto.get("stato_pre_annullamento") or "attivo",
            "esaurito": bool(lotto.get("esaurito_pre_annullamento")),
            "quantita": lotto.get("quantita_pre_annullamento") or 0,
            "motivo_ripristino": motivo,
            "ripristinato_il": datetime.now(timezone.utc).isoformat(),
            "ripristinato_da_id": actor["id"], "ripristinato_da_nome": actor["nome"],
            "ripristino_operazione_id": operazione,
        }
        esito = await db.lotti.update_one(
            {"_id": lotto["_id"], "stato": "annullato"}, {"$set": modifica})
        if esito.matched_count != 1:
            raise HTTPException(409, "Lotto cambiato: aggiornare la scheda")
        lotto.update(modifica)
    elif not lotto.get("ripristino_operazione_id") or lotto.get("motivo_ripristino") != motivo:
        raise HTTPException(409, "Lotto non annullato")

    await registra_movimento(
        lotto.get("id") or lotto_id, "ripristino",
        numero_lotto=lotto.get("numero_lotto") or lotto.get("lotto_id") or "",
        quantita=lotto.get("quantita_pre_annullamento"),
        operatore_id=lotto["ripristinato_da_id"], operatore_nome=lotto["ripristinato_da_nome"],
        motivo=lotto["motivo_ripristino"],
        operation_id=lotto["ripristino_operazione_id"],
    )
    return {"ok": True, "lotto_id": lotto.get("id") or lotto_id, "stato": lotto["stato"]}
