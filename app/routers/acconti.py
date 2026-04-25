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
    natura: Optional[str] = Query(default=None, description="su_futuro | su_pregresso"),
    stato: Optional[str] = Query(default=None, description="registrato | riconciliato_banca | scalato_su_cedolino | annullato"),
    dipendente_id: Optional[str] = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=5000),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Restituisce tutti gli acconti con filtri opzionali.

    Per la griglia pagina Acconti. I filtri anno/mese sono matching su prefisso
    del campo `data` (formato YYYY-MM-DD).

    Filtri estesi:
    - natura: filtra per natura_acconto (su_futuro / su_pregresso)
    - stato: filtra per stato lifecycle (registrato, riconciliato_banca,
             scalato_su_cedolino, annullato)
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
    if natura:
        if natura not in {"su_futuro", "su_pregresso"}:
            raise HTTPException(
                status_code=400,
                detail="Natura non valida. Validi: su_futuro, su_pregresso",
            )
        query["natura_acconto"] = natura
    if stato:
        valid_stati = {"registrato", "riconciliato_banca", "scalato_su_cedolino", "annullato"}
        if stato not in valid_stati:
            raise HTTPException(
                status_code=400,
                detail=f"Stato non valido. Validi: {', '.join(sorted(valid_stati))}",
            )
        query["stato"] = stato

    # Filtro per anno/mese:
    # Schema reale dei docs (ispezione MongoDB):
    #   - Hanno campi NUMERICI `anno` (int) e `mese` (int) — fonte di verità
    #   - Il campo `data` è una STRINGA in formato DD/MM/YYYY (parser italiano),
    #     non ISO — il vecchio regex "^YYYY" non matchava mai nulla.
    # Soluzione: filtro primario su anno/mese numerici. Manteniamo un OR con
    # il regex su `data` in formato ISO per retrocompatibilità con eventuali
    # record legacy che hanno solo `data` in formato ISO.
    if anno and mese:
        prefix_iso = f"{anno}-{str(mese).zfill(2)}"
        query["$or"] = [
            {"anno": int(anno), "mese": int(mese)},
            {"data": {"$regex": f"^{prefix_iso}"}},
        ]
    elif anno:
        query["$or"] = [
            {"anno": int(anno)},
            {"data": {"$regex": f"^{int(anno)}"}},
        ]

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
    """Aggrega acconti per tipo e per dipendente nel periodo selezionato.

    Schema reale dei docs (da ispezione DB):
      - Campi numerici `anno` e `mese` (fonte di verità)
      - Campo `data` stringa in formato DD/MM/YYYY (NON ISO)
      - Molti docs hanno `source` ("estratto_conto", "manuale") ma non `tipo`
      - Altri docs hanno `tipo` ("tfr", "stipendio", ...) ma non `source`

    Per il raggruppamento "per tipo" usiamo un fallback: se `tipo` è assente
    o vuoto, usiamo `source`. Il filtro anno usa `anno` numerico (con
    fallback regex su `data` per retrocompat).
    """
    db = Database.get_db()
    match: Dict[str, Any] = {}
    if anno:
        match["$or"] = [
            {"anno": int(anno)},
            {"data": {"$regex": f"^{int(anno)}"}},
        ]

    # Pipeline comune: aggiunge un campo "categoria" = $ifNull($tipo, $source)
    # per raggruppare in modo sensato anche i documenti che hanno solo `source`.
    common_enrich = {
        "$addFields": {
            "categoria": {
                "$ifNull": [
                    {"$cond": [{"$eq": ["$tipo", ""]}, None, "$tipo"]},
                    {"$ifNull": ["$source", "non_specificato"]},
                ]
            },
            "_importo_num": {
                "$convert": {
                    "input": "$importo",
                    "to": "double",
                    "onError": 0,
                    "onNull": 0,
                }
            },
        }
    }

    # Totali per categoria (tipo o source)
    pipeline_tipo: List[Dict[str, Any]] = []
    if match:
        pipeline_tipo.append({"$match": match})
    pipeline_tipo.extend(
        [
            common_enrich,
            {
                "$group": {
                    "_id": "$categoria",
                    "totale": {"$sum": "$_importo_num"},
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"totale": -1}},
        ]
    )
    per_tipo_raw = await db["acconti_dipendenti"].aggregate(pipeline_tipo).to_list(50)
    per_tipo = [
        {
            "tipo": r["_id"] or "non_specificato",
            "totale": round(r["totale"] or 0, 2),
            "count": r["count"],
        }
        for r in per_tipo_raw
    ]

    # Totali per dipendente
    pipeline_dip: List[Dict[str, Any]] = []
    if match:
        pipeline_dip.append({"$match": match})
    pipeline_dip.extend(
        [
            common_enrich,
            {
                "$group": {
                    "_id": {
                        "$ifNull": [
                            "$dipendente_id",
                            {"$ifNull": ["$dipendente_nome", "sconosciuto"]},
                        ]
                    },
                    "dipendente_nome": {"$last": "$dipendente_nome"},
                    "totale": {"$sum": "$_importo_num"},
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"totale": -1}},
        ]
    )
    per_dipendente_raw = (
        await db["acconti_dipendenti"].aggregate(pipeline_dip).to_list(500)
    )
    per_dipendente = [
        {
            "dipendente_id": r["_id"],
            "dipendente_nome": r.get("dipendente_nome") or "",
            "totale": round(r["totale"] or 0, 2),
            "count": r["count"],
        }
        for r in per_dipendente_raw
    ]

    # Aggregazione per natura_acconto (su_futuro vs su_pregresso)
    # Per i record legacy senza il campo, default "su_futuro" (caso più comune)
    pipeline_natura: List[Dict[str, Any]] = []
    if match:
        pipeline_natura.append({"$match": match})
    pipeline_natura.extend(
        [
            common_enrich,
            {
                "$group": {
                    "_id": {"$ifNull": ["$natura_acconto", "su_futuro"]},
                    "totale": {"$sum": "$_importo_num"},
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"totale": -1}},
        ]
    )
    per_natura_raw = await db["acconti_dipendenti"].aggregate(pipeline_natura).to_list(10)
    per_natura = [
        {
            "natura": r["_id"] or "su_futuro",
            "totale": round(r["totale"] or 0, 2),
            "count": r["count"],
        }
        for r in per_natura_raw
    ]

    # Aggregazione per stato lifecycle
    pipeline_stato: List[Dict[str, Any]] = []
    if match:
        pipeline_stato.append({"$match": match})
    pipeline_stato.extend(
        [
            common_enrich,
            {
                "$group": {
                    "_id": {"$ifNull": ["$stato", "registrato"]},
                    "totale": {"$sum": "$_importo_num"},
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"totale": -1}},
        ]
    )
    per_stato_raw = await db["acconti_dipendenti"].aggregate(pipeline_stato).to_list(10)
    per_stato = [
        {
            "stato": r["_id"] or "registrato",
            "totale": round(r["totale"] or 0, 2),
            "count": r["count"],
        }
        for r in per_stato_raw
    ]

    totale_generale = sum(r["totale"] for r in per_tipo)

    return {
        "anno": anno,
        "totale_generale": round(totale_generale, 2),
        "per_tipo": per_tipo,
        "per_dipendente": per_dipendente,
        "per_natura": per_natura,
        "per_stato": per_stato,
    }
