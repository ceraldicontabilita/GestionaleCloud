"""Posizione dare/avere del dipendente e conciliazioni (solo amministratore).

La logica sta in ``app/services/posizione_dipendente.py``: qui solo lettura
della richiesta, autorizzazione (``require_admin`` sul router in ``main.py``) e
risposta. Gli errori portano ``code``, ``message`` e ``details``.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import Response

from app.hr.database import Database
from app.services import posizione_dipendente as pos

router = APIRouter(tags=["Posizione dipendente"])


def _db():
    return Database.get_db()


def _errore(exc: pos.ErrorePosizione, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail=exc.come_dict())


def _non_trovata() -> HTTPException:
    return HTTPException(404, {"code": "CONCILIAZIONE_NON_TROVATA", "message": "Conciliazione non trovata",
                               "details": {}})


async def _dipendente(db, dipendente_id: str) -> Dict[str, Any]:
    dip = await db.dipendenti.find_one({"id": dipendente_id}, {"_id": 0, "id": 1, "nome_completo": 1})
    if not dip:
        raise HTTPException(404, {"code": "DIPENDENTE_NON_TROVATO", "message": "Dipendente non trovato",
                                  "details": {"dipendente_id": dipendente_id}})
    return dip


@router.get("/vocabolari")
async def vocabolari():
    return pos.vocabolari()


@router.get("/dipendente/{dipendente_id}")
async def posizione(dipendente_id: str, anno: Optional[int] = None):
    """Dare/avere con saldo progressivo e riporto; bonus delle conciliazioni a parte."""
    db = _db()
    dip = await _dipendente(db, dipendente_id)
    out = await pos.posizione_dipendente(db, dipendente_id, anno)
    out["dipendente"] = dip.get("nome_completo")
    return out


@router.get("/conciliazioni")
async def elenco_conciliazioni(dipendente_id: Optional[str] = None, annullate: bool = False):
    filtro: Dict[str, Any] = {"dipendente_id": dipendente_id} if dipendente_id else {}
    righe = await _db()[pos.COLL_CONCILIAZIONI].find(filtro, {"_id": 0, "file_data": 0}).to_list(500)
    righe = [pos.vista_conciliazione(r) for r in righe if annullate or not r.get("annullata")]
    righe.sort(key=lambda r: r.get("data") or "", reverse=True)
    return {"righe": righe, "totale": len(righe)}


@router.post("/conciliazioni")
async def crea_conciliazione(dati: Dict[str, Any] = Body(...)):
    db = _db()
    try:
        doc = pos.normalizza_conciliazione(dati)
    except pos.ErrorePosizione as exc:
        raise _errore(exc) from exc
    await _dipendente(db, doc["dipendente_id"])
    ora = datetime.now(timezone.utc).isoformat()
    doc.update({"id": str(uuid.uuid4()), "pagamenti": [], "stato": "da_pagare",
                "annullata": False, "created_at": ora, "updated_at": ora})
    await db[pos.COLL_CONCILIAZIONI].insert_one(dict(doc))
    return pos.vista_conciliazione(doc)


@router.put("/conciliazioni/{conciliazione_id}")
async def modifica_conciliazione(conciliazione_id: str, dati: Dict[str, Any] = Body(...)):
    """Riscrive i campi della conciliazione; pagamenti e documento restano."""
    db = _db()
    conc = await db[pos.COLL_CONCILIAZIONI].find_one({"id": conciliazione_id}, {"_id": 0, "file_data": 0})
    if not conc:
        raise _non_trovata()
    try:
        nuovi = pos.normalizza_conciliazione({**dati, "dipendente_id": conc["dipendente_id"]})
    except pos.ErrorePosizione as exc:
        raise _errore(exc) from exc
    conc.update(nuovi)
    nuovi.update({"stato": pos.stato_conciliazione(conc), "updated_at": datetime.now(timezone.utc).isoformat()})
    await db[pos.COLL_CONCILIAZIONI].update_one({"id": conciliazione_id}, {"$set": nuovi})
    conc.update(nuovi)
    return pos.vista_conciliazione(conc)


@router.post("/conciliazioni/{conciliazione_id}/annulla")
async def annulla_conciliazione(conciliazione_id: str, dati: Dict[str, Any] = Body(...)):
    """Una conciliazione non si cancella: si annulla con il motivo e resta in archivio."""
    motivo = str(dati.get("motivo") or "").strip()
    if not motivo:
        raise HTTPException(400, {"code": "MOTIVO_MANCANTE", "message": "Scegli il motivo dell'annullamento",
                                  "details": {}})
    db = _db()
    res = await db[pos.COLL_CONCILIAZIONI].update_one(
        {"id": conciliazione_id},
        {"$set": {"annullata": True, "motivo_annullamento": motivo,
                  "annullata_il": datetime.now(timezone.utc).isoformat()}})
    if res.matched_count == 0:
        raise _non_trovata()
    return {"ok": True}


@router.post("/conciliazioni/{conciliazione_id}/pagamenti")
async def aggiungi_pagamento(conciliazione_id: str, dati: Dict[str, Any] = Body(...)):
    try:
        return await pos.aggiungi_pagamento(_db(), conciliazione_id, {**dati, "origine": "manuale"})
    except pos.ErrorePosizione as exc:
        raise _errore(exc, 404 if exc.code == "CONCILIAZIONE_NON_TROVATA" else 400) from exc


@router.delete("/conciliazioni/{conciliazione_id}/pagamenti/{pagamento_id}")
async def togli_pagamento(conciliazione_id: str, pagamento_id: str):
    """Solo un pagamento scritto a mano; uno arrivato dalla coda bonifici resta."""
    db = _db()
    conc = await db[pos.COLL_CONCILIAZIONI].find_one({"id": conciliazione_id}, {"_id": 0, "file_data": 0})
    if not conc:
        raise _non_trovata()
    pagamenti = conc.get("pagamenti") or []
    trovato = next((p for p in pagamenti if p.get("id") == pagamento_id), None)
    if not trovato:
        raise HTTPException(404, {"code": "PAGAMENTO_NON_TROVATO", "message": "Pagamento non trovato", "details": {}})
    if trovato.get("origine") != "manuale":
        raise HTTPException(409, {"code": "PAGAMENTO_DA_BANCA",
                                  "message": "Un pagamento arrivato dalla coda bonifici non si toglie da qui",
                                  "details": {"origine": trovato.get("origine")}})
    conc["pagamenti"] = [p for p in pagamenti if p.get("id") != pagamento_id]
    agg = {"pagamenti": conc["pagamenti"], "stato": pos.stato_conciliazione(conc),
           "updated_at": datetime.now(timezone.utc).isoformat()}
    await db[pos.COLL_CONCILIAZIONI].update_one({"id": conciliazione_id}, {"$set": agg})
    conc.update(agg)
    return pos.vista_conciliazione(conc)


@router.post("/conciliazioni/{conciliazione_id}/documento")
async def carica_documento(conciliazione_id: str, file: UploadFile = File(...)):
    contenuto = await file.read()
    try:
        return await pos.salva_documento(_db(), conciliazione_id, file.filename or "verbale.pdf", contenuto)
    except pos.ErrorePosizione as exc:
        raise _errore(exc, 404 if exc.code == "CONCILIAZIONE_NON_TROVATA" else 400) from exc


@router.get("/conciliazioni/{conciliazione_id}/documento")
async def scarica_documento(conciliazione_id: str):
    trovato = await pos.leggi_documento(_db(), conciliazione_id)
    if not trovato:
        raise HTTPException(404, {"code": "DOCUMENTO_NON_TROVATO", "message": "Documento non disponibile",
                                  "details": {}})
    contenuto, nome, mime = trovato
    nome_sicuro = nome.replace('"', "").replace("\n", " ")
    return Response(content=contenuto, media_type=mime,
                    headers={"Content-Disposition": f'inline; filename="{nome_sicuro}"'})
