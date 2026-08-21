"""
Router Trattenute Verbali — ciclo di vita trattenute in busta paga
===================================================================
Gestisce la trattenuta al dipendente per verbali (multe) pagati dalla
società: conferma (sempre manuale), comunicazione al consulente del
lavoro, rinvio ad altro mese, esclusione e report Excel per consulente.

Prefisso: /api/trattenute-verbali (vedi router_registry.py)
Collection: trattenute_dipendenti (condivisa, mai cancellare record)
"""
import io
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import StreamingResponse
from app.services.sheets_document_store import ReturnRecord

from app.database import Database
from app.utils.error_handler import handle_errors
from app.services.trattenute_verbali_service import (
    COLL_TRATTENUTE,
    STATI_ATTESA_VERIFICA,
    STATI_CONFERMABILI,
    STATI_TERMINALI,
    STATO_COMUNICATA,
    STATO_CONFERMATA,
    STATO_ESCLUSA,
    STATO_PROPOSTA,
    valida_mese_cedolino,
)

logger = logging.getLogger(__name__)
router = APIRouter()


async def _audit_cambio_stato(
    db,
    trattenuta: Dict[str, Any],
    azione: str,
    stato_prec: Optional[str],
    dettaglio: str,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Audit unificato per ogni cambio stato della trattenuta."""
    from app.services.audit_logger import log_evento

    await log_evento(
        modulo="trattenute_verbali",
        azione=azione,
        entita_id=trattenuta.get("id", ""),
        entita_collection=COLL_TRATTENUTE,
        db=db,
        vecchio_stato={"stato": stato_prec},
        nuovo_stato={"stato": trattenuta.get("stato")},
        fonte="api_trattenute_verbali",
        utente="utente",
        dettaglio=dettaglio,
        extra=extra,
    )


@router.get("/")
@handle_errors
async def lista_trattenute(
    stato: Optional[str] = Query(None),
    anno: Optional[int] = Query(None),
) -> Dict[str, Any]:
    """Lista trattenute verbali con filtri opzionali per stato e anno."""
    db = Database.get_db()

    query: Dict[str, Any] = {"tipo": {"$in": ["verbale_multa", "trattenuta_verbale"]}}
    if stato:
        query["stato"] = stato
    if anno:
        # Anno del mese cedolino suggerito (YYYY-MM) o campo anno legacy
        query["$or"] = [
            {"mese_cedolino_suggerito": {"$regex": f"^{int(anno)}-"}},
            {"anno": int(anno)},
        ]

    trattenute = await db[COLL_TRATTENUTE].find(query, {"_id": 0}).sort(
        "created_at", -1
    ).to_list(500)

    return {
        "trattenute": trattenute,
        "totale": len(trattenute),
        "importo_totale": round(
            sum(
                float(t.get("importo_da_recuperare") or t.get("importo") or 0)
                for t in trattenute
            ),
            2,
        ),
    }


@router.post("/{trattenuta_id}/conferma")
@handle_errors
async def conferma_trattenuta(
    trattenuta_id: str, data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Conferma la trattenuta (SEMPRE azione dell'utente): richiede il mese
    cedolino esplicito 'YYYY-MM'. Claim atomico solo da proposta/da_verificare.
    """
    db = Database.get_db()

    mese_cedolino = (data.get("mese_cedolino") or "").strip()
    if not valida_mese_cedolino(mese_cedolino):
        raise HTTPException(
            status_code=400,
            detail="mese_cedolino obbligatorio in formato YYYY-MM (es. 2026-08)",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    # find_one_and_update: claim atomico, evita doppie conferme concorrenti
    trattenuta = await db[COLL_TRATTENUTE].find_one_and_update(
        {"id": trattenuta_id, "stato": {"$in": list(STATI_CONFERMABILI)}},
        {"$set": {
            "stato": STATO_CONFERMATA,
            "mese_cedolino_suggerito": mese_cedolino,
            "confermata_at": now_iso,
            "updated_at": now_iso,
        }},
        projection={"_id": 0},
        return_document=ReturnRecord.AFTER,
    )
    if not trattenuta:
        esistente = await db[COLL_TRATTENUTE].find_one(
            {"id": trattenuta_id}, {"_id": 0, "stato": 1}
        )
        if not esistente:
            raise HTTPException(status_code=404, detail="Trattenuta non trovata")
        raise HTTPException(
            status_code=409,
            detail=(
                f"Trattenuta in stato '{esistente.get('stato')}': la conferma è "
                f"possibile solo da {', '.join(STATI_CONFERMABILI)}"
            ),
        )

    await _audit_cambio_stato(
        db, trattenuta, "confermata", STATO_PROPOSTA,
        f"Trattenuta verbale {trattenuta.get('numero_verbale', '')} confermata "
        f"dall'utente per il cedolino {mese_cedolino}",
    )
    return {"success": True, "trattenuta": trattenuta}


@router.post("/{trattenuta_id}/comunica")
@handle_errors
async def comunica_trattenuta(trattenuta_id: str) -> Dict[str, Any]:
    """Segna la trattenuta come comunicata al consulente (solo da confermata)."""
    db = Database.get_db()

    now_iso = datetime.now(timezone.utc).isoformat()
    trattenuta = await db[COLL_TRATTENUTE].find_one_and_update(
        {"id": trattenuta_id, "stato": STATO_CONFERMATA},
        {"$set": {
            "stato": STATO_COMUNICATA,
            "comunicata_consulente_at": now_iso,
            "updated_at": now_iso,
        }},
        projection={"_id": 0},
        return_document=ReturnRecord.AFTER,
    )
    if not trattenuta:
        esistente = await db[COLL_TRATTENUTE].find_one(
            {"id": trattenuta_id}, {"_id": 0, "stato": 1}
        )
        if not esistente:
            raise HTTPException(status_code=404, detail="Trattenuta non trovata")
        raise HTTPException(
            status_code=409,
            detail=(
                f"Trattenuta in stato '{esistente.get('stato')}': comunicabile "
                f"solo da '{STATO_CONFERMATA}'"
            ),
        )

    await _audit_cambio_stato(
        db, trattenuta, "comunicata_consulente", STATO_CONFERMATA,
        f"Trattenuta verbale {trattenuta.get('numero_verbale', '')} comunicata "
        f"al consulente del lavoro (mese {trattenuta.get('mese_cedolino_suggerito')})",
    )
    return {"success": True, "trattenuta": trattenuta}


@router.post("/{trattenuta_id}/rimanda")
@handle_errors
async def rimanda_trattenuta(
    trattenuta_id: str, data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """Rimanda la trattenuta a un altro mese cedolino (da proposta/confermata)."""
    db = Database.get_db()

    nuovo_mese = (data.get("nuovo_mese") or "").strip()
    if not valida_mese_cedolino(nuovo_mese):
        raise HTTPException(
            status_code=400,
            detail="nuovo_mese obbligatorio in formato YYYY-MM (es. 2026-09)",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    stati_ammessi = [STATO_PROPOSTA, STATO_CONFERMATA]
    prima = await db[COLL_TRATTENUTE].find_one(
        {"id": trattenuta_id}, {"_id": 0, "stato": 1, "mese_cedolino_suggerito": 1}
    )
    trattenuta = await db[COLL_TRATTENUTE].find_one_and_update(
        {"id": trattenuta_id, "stato": {"$in": stati_ammessi}},
        {"$set": {
            "mese_cedolino_suggerito": nuovo_mese,
            "rimandata_at": now_iso,
            "updated_at": now_iso,
        }},
        projection={"_id": 0},
        return_document=ReturnRecord.AFTER,
    )
    if not trattenuta:
        if not prima:
            raise HTTPException(status_code=404, detail="Trattenuta non trovata")
        raise HTTPException(
            status_code=409,
            detail=(
                f"Trattenuta in stato '{prima.get('stato')}': rinvio possibile "
                f"solo da {', '.join(stati_ammessi)}"
            ),
        )

    await _audit_cambio_stato(
        db, trattenuta, "rimandata", trattenuta.get("stato"),
        f"Trattenuta verbale {trattenuta.get('numero_verbale', '')} rimandata "
        f"da {prima.get('mese_cedolino_suggerito')} a {nuovo_mese}",
        extra={"mese_precedente": prima.get("mese_cedolino_suggerito")},
    )
    return {"success": True, "trattenuta": trattenuta}


@router.post("/{trattenuta_id}/escludi")
@handle_errors
async def escludi_trattenuta(
    trattenuta_id: str, data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """Esclude la trattenuta dal recupero (con motivo, da stati non terminali)."""
    db = Database.get_db()

    motivo = (data.get("motivo") or "").strip()
    if not motivo:
        raise HTTPException(status_code=400, detail="motivo obbligatorio")

    now_iso = datetime.now(timezone.utc).isoformat()
    prima = await db[COLL_TRATTENUTE].find_one(
        {"id": trattenuta_id}, {"_id": 0, "stato": 1}
    )
    trattenuta = await db[COLL_TRATTENUTE].find_one_and_update(
        {"id": trattenuta_id, "stato": {"$nin": list(STATI_TERMINALI)}},
        {"$set": {
            "stato": STATO_ESCLUSA,
            "motivo_esclusione": motivo,
            "esclusa_at": now_iso,
            "updated_at": now_iso,
        }},
        projection={"_id": 0},
        return_document=ReturnRecord.AFTER,
    )
    if not trattenuta:
        if not prima:
            raise HTTPException(status_code=404, detail="Trattenuta non trovata")
        raise HTTPException(
            status_code=409,
            detail=f"Trattenuta in stato terminale '{prima.get('stato')}': non escludibile",
        )

    await _audit_cambio_stato(
        db, trattenuta, "esclusa", prima.get("stato") if prima else None,
        f"Trattenuta verbale {trattenuta.get('numero_verbale', '')} esclusa: {motivo}",
        extra={"motivo": motivo},
    )
    return {"success": True, "trattenuta": trattenuta}


@router.post("/retro-verifica")
@handle_errors
async def retro_verifica_trattenute() -> Dict[str, Any]:
    """
    Lancio manuale della verifica retroattiva: ripesca i cedolini già
    archiviati (posta/Drive) e verifica le trattenute confermate/comunicate/
    in attesa con le stesse regole del percorso on-import. Stesso giro del
    job giornaliero delle 8:30 (id 'verifica_trattenute_retro').
    """
    from app.services.trattenute_verbali_service import verifica_trattenute_retroattiva

    db = Database.get_db()
    esito = await verifica_trattenute_retroattiva(db)
    return {"success": True, **esito}


@router.get("/report-consulente")
@handle_errors
async def report_consulente(
    formato: str = Query("excel"),
    stato: Optional[str] = Query(None),
    anno: Optional[int] = Query(None),
):
    """
    Report trattenute per il consulente del lavoro.
    formato=excel → file .xlsx (openpyxl via pandas, come export prima nota);
    altrimenti JSON con le stesse colonne.
    """
    db = Database.get_db()

    query: Dict[str, Any] = {"tipo": {"$in": ["verbale_multa", "trattenuta_verbale"]}}
    if stato:
        query["stato"] = stato
    else:
        # Default: escludi le escluse, il consulente vede solo trattenute vive
        query["stato"] = {"$ne": STATO_ESCLUSA}
    if anno:
        query["$or"] = [
            {"mese_cedolino_suggerito": {"$regex": f"^{int(anno)}-"}},
            {"anno": int(anno)},
        ]

    trattenute = await db[COLL_TRATTENUTE].find(query, {"_id": 0}).sort(
        [("mese_cedolino_suggerito", 1), ("dipendente", 1)]
    ).to_list(2000)

    righe = [
        {
            "Dipendente": t.get("dipendente") or t.get("dipendente_nome", ""),
            "Matricola": t.get("matricola") or "",
            "Codice fiscale": t.get("codice_fiscale", ""),
            "Targa": t.get("targa", ""),
            "Numero verbale": t.get("numero_verbale", ""),
            "Data infrazione": t.get("data_infrazione")
            or t.get("data_verbale", ""),
            "Importo pagato società": float(
                t.get("importo_pagato_societa") or t.get("importo") or 0
            ),
            "Importo da trattenere": float(
                t.get("importo_da_recuperare") or t.get("importo") or 0
            ),
            "Mese cedolino suggerito": t.get("mese_cedolino_suggerito", ""),
            "Stato": t.get("stato", ""),
            "Nota": t.get("nota_consulente", ""),
        }
        for t in trattenute
    ]

    if formato != "excel":
        return {"righe": righe, "totale": len(righe)}

    try:
        import pandas as pd
    except ImportError:
        raise HTTPException(status_code=500, detail="pandas non installato")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        colonne = [
            "Dipendente", "Matricola", "Codice fiscale", "Targa",
            "Numero verbale", "Data infrazione", "Importo pagato società",
            "Importo da trattenere", "Mese cedolino suggerito", "Stato", "Nota",
        ]
        df = pd.DataFrame(righe, columns=colonne)
        df.to_excel(writer, sheet_name="Trattenute Verbali", index=False)

    output.seek(0)
    filename = f"trattenute_verbali_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
