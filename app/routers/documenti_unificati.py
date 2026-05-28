"""
API REST per la vista unificata sui documenti.

Espone una sola interfaccia (paginated, filtrabile) sopra le tre
collezioni fisiche (documents_inbox, documenti_classificati,
documenti_non_associati). NON tocca le scritture esistenti.

Endpoint:
    GET /api/documenti-unificati/lista
    GET /api/documenti-unificati/conteggi
    GET /api/documenti-unificati/{documento_id}
"""
from typing import Optional
from fastapi import APIRouter, HTTPException

from app.database import Database
from app.services import documenti_unified

router = APIRouter()


@router.get("/lista")
async def lista_documenti_unificata(
    stato: Optional[str] = None,
    tipo: Optional[str] = None,
    mittente: Optional[str] = None,
    pagina: int = 1,
    dimensione: int = 50,
):
    """Lista unificata di tutti i documenti (3 collezioni fuse).

    Filtri:
        - stato: 'inbox' | 'classificato' | 'non_associato'
        - tipo: filtro libero su campo 'tipo'/'categoria'
        - mittente: filtro libero su 'mittente'/'from'
    """
    db = Database.get_db()
    filtro: dict = {}
    if tipo:
        filtro["$or"] = [{"tipo": tipo}, {"categoria": tipo}]
    if mittente:
        filtro["$or"] = (filtro.get("$or") or []) + [
            {"mittente": {"$regex": mittente, "$options": "i"}},
            {"from": {"$regex": mittente, "$options": "i"}},
        ]

    pagina = max(1, int(pagina))
    dimensione = max(1, min(int(dimensione), 200))
    skip = (pagina - 1) * dimensione

    items = await documenti_unified.lista_unificata(
        db, filtro=filtro, skip=skip, limit=dimensione
    )
    # Se l'utente filtra per stato, lo applichiamo dopo perche' lo "stato"
    # logico viene calcolato dalla pipeline, non e' un campo MongoDB indicizzato.
    if stato:
        items = [d for d in items if d.get("stato") == stato]

    return {
        "pagina": pagina,
        "dimensione": dimensione,
        "documenti": items,
    }


@router.get("/conteggi")
async def conteggi_documenti_per_stato():
    """Conta i documenti per stato logico (inbox/classificato/non_associato)."""
    db = Database.get_db()
    return await documenti_unified.conta_totali(db)


@router.get("/{documento_id}")
async def dettaglio_documento(documento_id: str):
    """Dettaglio di un documento per ID, in qualsiasi collezione viva."""
    db = Database.get_db()
    doc = await documenti_unified.trova_per_id(db, documento_id)
    if not doc:
        raise HTTPException(
            status_code=404,
            detail={"errore": "documento_non_trovato", "id": documento_id},
        )
    return doc
