"""
Operazioni Module - Gestione operazioni da confermare.
Modulo suddiviso per funzionalità:
- base: CRUD operazioni, conferma, lista
- smart: Riconciliazione smart, banca veloce, analisi
- carta: Transazioni carta, supervisione
"""
from fastapi import APIRouter, Query, Body
from typing import Optional, Dict, Any

router = APIRouter()

# Import functions from modules
from .base import (
    lista_operazioni, conferma_operazione, elimina_operazione,
    lista_aruba_pendenti, get_fornitore_preferenza, check_fattura_esistente
)
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

# Base operations
router.add_api_route("/lista", lista_operazioni, methods=["GET"])
router.add_api_route("/aruba-pendenti", lista_aruba_pendenti, methods=["GET"])
router.add_api_route("/check-fattura-esistente", check_fattura_esistente, methods=["GET"])

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

router.add_api_route("/fornitore-preferenza/{fornitore}", get_fornitore_preferenza, methods=["GET"])
router.add_api_route("/smart/movimento/{movimento_id}", analizza_singolo_movimento, methods=["GET"])


# Wrapper per conferma con path parameter
async def _conferma_operazione_wrapper(
    operazione_id: str,
    metodo_pagamento: str = Body(..., embed=True),
    crea_movimento: bool = Body(False, embed=True),
    crea_scadenza: bool = Body(False, embed=True)
):
    return await conferma_operazione(operazione_id, metodo_pagamento, crea_movimento, crea_scadenza)

router.add_api_route("/{operazione_id}/conferma", _conferma_operazione_wrapper, methods=["POST"])
router.add_api_route("/{operazione_id}", elimina_operazione, methods=["DELETE"])
