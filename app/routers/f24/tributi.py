"""Tributi per codice: pagati, ravveduti, compensati, e cosa resta (solo admin).

Montato dentro il router F24 (``/api/f24``), prima della rotta dinamica:

* ``GET /api/f24/tributi?anno=2026&stato=APERTO&sezione=sezione_erario&cerca=1040``
* ``GET /api/f24/tributi/versamenti?anno=2020&origine=drive`` — registro versamenti
  (``services/registro_versamenti_f24.py``)

Sola lettura sul registro unico F24 e sulle ritenute attese
(``services/tributi_per_codice.py``).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query

from app.database import Database
from app.middleware.performance import istantanea
from app.services import tributi_per_codice as tributi
from app.utils.dependencies import get_current_admin_user

router = APIRouter()


@istantanea(ttl=120)
async def _voci() -> Dict[str, Any]:
    return await tributi.carica_voci(Database.get_db())


@router.get("/tributi", summary="Tributi per codice: pagati, ravveduti, a credito, da pagare")
async def elenco_tributi(
    anno: Optional[int] = Query(None, ge=2000, le=2100),
    stato: Optional[str] = Query(None, max_length=40),
    sezione: Optional[str] = Query(None, max_length=40),
    cerca: Optional[str] = Query(None, max_length=80),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    dati = await _voci()
    risultato = tributi.riepilogo(
        dati["voci"], anno=anno, stato=stato or None, sezione=sezione or None,
        cerca=(cerca or "").strip() or None,
    )
    return {**risultato, "conteggi": dati["conteggi"], "istantanea": dati.get("istantanea")}


@istantanea(ttl=120)
async def _pagamenti() -> Dict[str, Any]:
    from app.services import f24_controllo_incrociato as reg

    registro = await reg.carica_registro(Database.get_db())
    quietanze = [q for q in registro["quietanze"] if q.get("righe")]
    return {"pagamenti": reg.pagamenti_da_quietanze(quietanze)}


@router.get("/tributi/versamenti",
            summary="Registro versamenti F24 per anno: codici dare/avere, deleghe, crediti, mesi mancanti")
async def registro_versamenti(
    anno: Optional[int] = Query(None, ge=2000, le=2100),
    origine: Optional[str] = Query(None, pattern="^(posta|drive|caricato|altro)$"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    from app.services import registro_versamenti_f24 as versamenti

    dati = await _pagamenti()
    return {**versamenti.costruisci(dati["pagamenti"], anno=anno, origine=origine),
            "istantanea": dati.get("istantanea")}
