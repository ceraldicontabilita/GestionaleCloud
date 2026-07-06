"""
Operazioni Module - Gestione operazioni da confermare.
Modulo suddiviso per funzionalità:
- smart: Riconciliazione smart, banca veloce, analisi
- carta: Transazioni carta, supervisione
"""
from fastapi import APIRouter, Query, Body
from typing import Optional, Dict, Any

router = APIRouter()

# Import functions from modules
from .smart import (
    banca_veloce, analizza_movimenti_smart, analizza_singolo_movimento,
    riconcilia_automatico, riconcilia_manuale,
    cerca_fatture_per_associazione, cerca_stipendi_per_associazione, cerca_f24_per_associazione
)
from .carta import (
    lista_transazioni_carta, riconcilia_carta_automatico, riconcilia_carta_manuale,
    esegui_supervisione
)
from .common import RiconciliaManuale, RiconciliaCartaRequest

# === ROTTE STATICHE ===

# Smart riconciliazione
router.add_api_route("/smart/banca-veloce", banca_veloce, methods=["GET"])
router.add_api_route("/smart/analizza", analizza_movimenti_smart, methods=["GET"])
router.add_api_route("/smart/riconcilia-auto", riconcilia_automatico, methods=["POST"])
router.add_api_route("/smart/riconcilia-manuale", riconcilia_manuale, methods=["POST"])
router.add_api_route("/smart/cerca-fatture", cerca_fatture_per_associazione, methods=["GET"])
router.add_api_route("/smart/cerca-stipendi", cerca_stipendi_per_associazione, methods=["GET"])
router.add_api_route("/smart/cerca-f24", cerca_f24_per_associazione, methods=["GET"])

# Carta
router.add_api_route("/carta/lista", lista_transazioni_carta, methods=["GET"])
router.add_api_route("/carta/riconcilia-auto", riconcilia_carta_automatico, methods=["POST"])
router.add_api_route("/carta/riconcilia-manuale", riconcilia_carta_manuale, methods=["POST"])

# Supervisione
router.add_api_route("/supervisione/esegui", esegui_supervisione, methods=["POST"])

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
    if r1.matched_count == 0 and r2.matched_count == 0:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Movimento non trovato")
    return {"message": "Movimento ignorato", "movimento_id": mov_id}

router.add_api_route("/smart/ignora", _ignora_movimento, methods=["POST"])
