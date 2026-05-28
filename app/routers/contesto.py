"""
GET /api/contesto/{tipo}/{id}
Restituisce entita' + entita' collegate in un blocco unico per il
"pannello relazionale" del frontend (clicco su fattura -> vedo
fornitore, partite, alert, match, prima nota).

Tipi supportati: fattura, fornitore, dipendente, movimento_banca,
f24, cedolino, assegno, documento.
"""
from fastapi import APIRouter, HTTPException
from app.database import Database
from app.services.contesto_entita import (
    ricostruisci_contesto, TIPI_SUPPORTATI,
)

router = APIRouter()


@router.get("/tipi")
async def elenca_tipi_supportati():
    """Elenco dei tipi di entita' per cui esiste la vista contesto."""
    return {"tipi": sorted(TIPI_SUPPORTATI)}


@router.get("/{tipo}/{entita_id}")
async def get_contesto(tipo: str, entita_id: str):
    if tipo not in TIPI_SUPPORTATI:
        raise HTTPException(
            status_code=400,
            detail={"errore": "tipo_non_supportato",
                    "tipi_validi": sorted(TIPI_SUPPORTATI)},
        )
    db = Database.get_db()
    res = await ricostruisci_contesto(db, tipo, entita_id)
    if not res:
        raise HTTPException(
            status_code=404,
            detail={"errore": "entita_non_trovata",
                    "tipo": tipo, "id": entita_id},
        )
    return res
