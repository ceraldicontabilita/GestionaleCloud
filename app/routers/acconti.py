"""Acconti router — pagina panoramica acconti su tutti i dipendenti.

La collection di riferimento è `acconti_dipendenti` e le operazioni CRUD sul
singolo acconto sono già implementate in `app/routers/tfr.py` sotto il prefix
`/api/tfr/acconti`. Questo router aggiunge SOLO:

  - GET  /api/acconti          lista globale con filtri (anno, mese, tipo,
                                dipendente) — utile per la pagina panoramica
  - GET  /api/acconti/riepilogo  totali per tipo e per dipendente

Per create/update/delete il frontend usa i già esistenti endpoint TFR.
Questo per non duplicare logica (la creazione di un acconto TFR deve aggiornare
anche `dipendenti.tfr_accantonato` e registrare in `movimenti_contabili`).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List, Optional
import logging

from app.database import Database
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


TIPI_VALIDI = {"tfr", "ferie", "tredicesima", "quattordicesima", "prestito", "stipendio"}


@router.get("", summary="Elenco globale acconti")
async def list_acconti(
    anno: Optional[int] = Query(default=None),
    mese: Optional[int] = Query(default=None, ge=1, le=12),
    tipo: Optional[str] = Query(default=None),
    dipendente_id: Optional[str] = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Restituisce tutti gli acconti con filtri opzionali.

    Per la griglia pagina Acconti. I filtri anno/mese sono matching su prefisso
    del campo `data` (formato YYYY-MM-DD).
    """
    db = Database.get_db()
    query: Dict[str, Any] = {}

    if dipendente_id:
        query["dipendente_id"] = dipendente_id
    if tipo:
        if tipo not in TIPI_VALIDI:
            raise HTTPException(
                status_code=400,
                detail=f"Tipo non valido. Validi: {', '.join(sorted(TIPI_VALIDI))}",
            )
        query["tipo"] = tipo

    # Filtro per anno/mese sul campo `data`
    if anno and mese:
        prefix = f"{anno}-{str(mese).zfill(2)}"
        query["data"] = {"$regex": f"^{prefix}"}
    elif anno:
        query["data"] = {"$regex": f"^{anno}"}

    items = (
        await db["acconti_dipendenti"]
        .find(query, {"_id": 0})
        .sort("data", -1)
        .to_list(limit)
    )

    # Arricchimento minimo: se manca dipendente_nome, lookup dal documento
    # (gestisce record legacy senza il campo)
    missing_names = [a for a in items if not a.get("dipendente_nome")]
    if missing_names:
        ids = list({a["dipendente_id"] for a in missing_names if a.get("dipendente_id")})
        if ids:
            dip_docs = await db["dipendenti"].find(
                {"id": {"$in": ids}},
                {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "nome_completo": 1},
            ).to_list(len(ids))
            name_by_id = {
                d["id"]: d.get("nome_completo")
                or f"{d.get('cognome', '')} {d.get('nome', '')}".strip()
                for d in dip_docs
            }
            for a in missing_names:
                a["dipendente_nome"] = name_by_id.get(a.get("dipendente_id"), "")

    totale = sum(float(a.get("importo", 0) or 0) for a in items)

    return {
        "count": len(items),
        "totale": round(totale, 2),
        "acconti": items,
    }


@router.get("/riepilogo", summary="Riepilogo acconti per tipo e dipendente")
async def riepilogo_acconti(
    anno: Optional[int] = Query(default=None),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Aggrega acconti per tipo e per dipendente nel periodo selezionato."""
    db = Database.get_db()
    match: Dict[str, Any] = {}
    if anno:
        match["data"] = {"$regex": f"^{anno}"}

    # Totali per tipo
    pipeline_tipo: List[Dict[str, Any]] = []
    if match:
        pipeline_tipo.append({"$match": match})
    pipeline_tipo.extend(
        [
            {
                "$group": {
                    "_id": "$tipo",
                    "totale": {"$sum": "$importo"},
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"totale": -1}},
        ]
    )
    per_tipo = await db["acconti_dipendenti"].aggregate(pipeline_tipo).to_list(50)
    per_tipo = [
        {"tipo": r["_id"] or "non_specificato", "totale": round(r["totale"], 2), "count": r["count"]}
        for r in per_tipo
    ]

    # Totali per dipendente
    pipeline_dip: List[Dict[str, Any]] = []
    if match:
        pipeline_dip.append({"$match": match})
    pipeline_dip.extend(
        [
            {
                "$group": {
                    "_id": "$dipendente_id",
                    "dipendente_nome": {"$last": "$dipendente_nome"},
                    "totale": {"$sum": "$importo"},
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"totale": -1}},
        ]
    )
    per_dipendente = (
        await db["acconti_dipendenti"].aggregate(pipeline_dip).to_list(500)
    )
    per_dipendente = [
        {
            "dipendente_id": r["_id"],
            "dipendente_nome": r.get("dipendente_nome") or "",
            "totale": round(r["totale"], 2),
            "count": r["count"],
        }
        for r in per_dipendente
    ]

    totale_generale = sum(r["totale"] for r in per_tipo)

    return {
        "anno": anno,
        "totale_generale": round(totale_generale, 2),
        "per_tipo": per_tipo,
        "per_dipendente": per_dipendente,
    }
