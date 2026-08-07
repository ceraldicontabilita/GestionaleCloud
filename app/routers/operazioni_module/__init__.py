"""
Operazioni Module - Gestione operazioni da confermare.
- smart: Riconciliazione smart, banca veloce, analisi

Il sottomodulo "carta" (transazioni carta di credito + supervisione) è stato
rimosso: zero chiamanti frontend, mai wired in UI (audit
memoria/endpoints/RICONCILIAZIONE_AUDIT.md, sistema #6).
"""
from fastapi import APIRouter, Query, Body
from typing import Optional, Dict, Any

router = APIRouter()

# Import functions from modules
from .smart import (
    banca_veloce, analizza_movimenti_smart, analizza_singolo_movimento,
    avvia_riconciliazione_automatica, stato_riconciliazione_automatica,
    riconcilia_manuale, conferma_f24_batch,
    cerca_fatture_per_associazione, cerca_stipendi_per_associazione, cerca_f24_per_associazione
)
from .common import RiconciliaManuale

# === ROTTE STATICHE ===

# Smart riconciliazione
router.add_api_route("/smart/banca-veloce", banca_veloce, methods=["GET"])
router.add_api_route("/smart/analizza", analizza_movimenti_smart, methods=["GET"])
router.add_api_route("/smart/riconcilia-auto", avvia_riconciliazione_automatica, methods=["POST"])
router.add_api_route("/smart/riconcilia-auto/status", stato_riconciliazione_automatica, methods=["GET"])
router.add_api_route("/smart/riconcilia-manuale", riconcilia_manuale, methods=["POST"])
router.add_api_route("/smart/conferma-f24", conferma_f24_batch, methods=["POST"])
router.add_api_route("/smart/cerca-fatture", cerca_fatture_per_associazione, methods=["GET"])
router.add_api_route("/smart/cerca-stipendi", cerca_stipendi_per_associazione, methods=["GET"])
router.add_api_route("/smart/cerca-f24", cerca_f24_per_associazione, methods=["GET"])


# Stipendi ↔ bonifici estratto conto (richiesta 18/07/2026: il nome del
# dipendente letto in estratto conto associa il pagamento al dipendente)
async def _riconcilia_stipendio(data: dict = Body(...)):
    from fastapi import HTTPException
    from app.database import Database
    from app.services.stipendi_bonifici import associa_bonifici_stipendi
    stipendio_id = data.get("stipendio_id")
    if not stipendio_id:
        raise HTTPException(status_code=400, detail="stipendio_id richiesto")
    db = Database.get_db()
    r = await associa_bonifici_stipendi(db, stipendio_id=stipendio_id)
    if not r["bonifici_associati"]:
        return {"success": False,
                "message": "Nessun bonifico col nome del dipendente trovato in "
                           "estratto conto: la riga resta in attesa (regola: mai "
                           "pagato senza riscontro bancario)."}
    return {"success": True, **r}


async def _associa_stipendi_auto():
    from app.database import Database
    from app.services.stipendi_bonifici import associa_bonifici_stipendi
    return await associa_bonifici_stipendi(Database.get_db())

router.add_api_route("/smart/riconcilia-stipendio", _riconcilia_stipendio, methods=["POST"])
router.add_api_route("/smart/associa-stipendi-auto", _associa_stipendi_auto, methods=["POST"])

# === ROTTE DINAMICHE ===

router.add_api_route("/smart/movimento/{movimento_id}", analizza_singolo_movimento, methods=["GET"])


# Ignora movimento (marca come da non processare)
async def _ignora_movimento(data: dict = Body(...)):
    from app.database import Database
    from datetime import datetime, timezone
    db = Database.get_db()
    mov_id = data.get("movimento_id")
    if not mov_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="movimento_id richiesto")
    # Aggiorna in ENTRAMBE le collection (movimenti possono essere in una o l'altra)
    ts = datetime.now(timezone.utc).isoformat()
    update = {"$set": {"ignorato": True, "updated_at": ts}}
    r1 = await db["estratto_conto_movimenti"].update_one({"id": mov_id}, update)
    r2 = await db["bank_movements"].update_one({"id": mov_id}, update)
    # anche le righe stipendio pendenti (tab Stipendi) si possono ignorare
    r3 = await db["prima_nota_salari"].update_one({"id": mov_id}, update)
    if r1.matched_count == 0 and r2.matched_count == 0 and r3.matched_count == 0:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Movimento non trovato")
    return {"message": "Movimento ignorato", "movimento_id": mov_id}

router.add_api_route("/smart/ignora", _ignora_movimento, methods=["POST"])
