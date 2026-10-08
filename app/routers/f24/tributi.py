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

from fastapi import APIRouter, Depends, HTTPException, Query

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


@router.get("/tributi/scadenzario",
            summary="Scadenzario: ogni tributo pagato nei termini, in ritardo, ravveduto o no")
async def scadenzario(
    anno: Optional[int] = Query(None, ge=2000, le=2100),
    stato: Optional[str] = Query(None, max_length=40),
    cerca: Optional[str] = Query(None, max_length=80),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Legge lo scadenzario persistente; se e' ancora vuoto lo calcola sul momento."""
    from app.services import scadenzario_tributi as sc

    db = Database.get_db()
    voci = await db[sc.COLL].find({}, {"_id": 0}).to_list(20000)
    persistente = bool(voci)
    if not voci:
        voci = await sc.carica(db)
    return {**sc.riepilogo(voci, anno=anno, stato=stato or None, cerca=(cerca or "").strip() or None),
            "persistente": persistente}


@istantanea(ttl=300)
async def _termini() -> Dict[str, Any]:
    # La vista costa circa 5 secondi: si serve pronta e si ricalcola in sottofondo.
    db = Database.get_db()
    if not hasattr(db, "termini_recupero"):
        # Archivio senza la vista dei termini (non e' Supabase): non si inventa una lista.
        raise HTTPException(status_code=503, detail="Fonte dei termini di recupero non disponibile in questo archivio")
    return {"righe": await db.termini_recupero()}


@router.get("/tributi/termini",
            summary="Termini di recupero: entro quando l'ente puo' ancora chiedere un tributo non trovato")
async def termini_recupero(
    stato: Optional[str] = Query(None, max_length=40,
                                 description="Assente = versamento mancante; TUTTI = senza filtro"),
    situazione: Optional[str] = Query(None, pattern="^(ANCORA_RECUPERABILE|TERMINE_SCADUTO|DA_VERIFICARE)$"),
    codice: Optional[str] = Query(None, max_length=20),
    cerca: Optional[str] = Query(None, max_length=80),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Sola lettura sulla vista dei termini (``services/termini_recupero.py``).
    Termini indicativi: vanno confermati con il commercialista."""
    from app.services import termini_recupero as termini

    dati = await _termini()
    return {**termini.riepilogo(dati["righe"], stato=stato or None, situazione=situazione or None,
                                codice=codice or None, cerca=(cerca or "").strip() or None),
            "istantanea": dati.get("istantanea")}


@router.post("/tributi/scadenzario/aggiorna", summary="Ricalcola lo scadenzario (idempotente)")
async def aggiorna_scadenzario(_admin: Dict[str, Any] = Depends(get_current_admin_user)) -> Dict[str, Any]:
    from app.services import scadenzario_tributi as sc

    return await sc.aggiorna(Database.get_db())
