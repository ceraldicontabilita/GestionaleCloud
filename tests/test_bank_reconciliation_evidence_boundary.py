from pathlib import Path


def test_proposals_only_use_unreconciled_bank_movements():
    src = Path("app/services/dati_provvisori_service.py").read_text()
    generate = src.split("async def genera_proposte_pagamento", 1)[1].split("async def conferma_proposta", 1)[0]
    assert '"riconciliato": {"$ne": True}' in generate
    assert "existing_movement_refs" in generate
    assert 'if not movimento_id:' in generate


def test_confirm_claims_proposal_and_bank_movement_before_writing():
    src = Path("app/services/dati_provvisori_service.py").read_text()
    confirm = src.split("async def conferma_proposta", 1)[1].split("async def conferma_tutte", 1)[0]
    assert '"stato": "in_conferma"' in confirm
    assert '"riconciliazione_claim": proposta_id' in confirm
    assert '"riconciliato": True' in confirm
    assert '"movimento_bancario_id": movimento_id' in confirm
    assert '"estratto_conto_id": movimento_id' in confirm
    assert '"pagato": True' in confirm
    assert '"riconciliato": True' in confirm


def test_bulk_confirmation_is_disabled():
    router = Path("app/routers/dati_provvisori.py").read_text()
    block = router.split('@router.post("/conferma-tutte")', 1)[1].split('@router.post("/rifiuta/', 1)[0]
    assert "status_code=409" in block
    assert "confermarla singolarmente" in block
    service = Path("app/services/dati_provvisori_service.py").read_text()
    bulk = service.split("async def conferma_tutte", 1)[1].split("async def rifiuta_proposta", 1)[0]
    assert '"success": False' in bulk
    assert "for p in proposte" not in bulk
