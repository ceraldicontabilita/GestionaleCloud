import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.fiscal_relations_view import prove_fiscali_periodo


def _run(coro):
    return asyncio.run(coro)


def test_collega_iva_quietanza_banca_e_avviso_solo_con_periodo_e_codice_certi():
    db = ClientArchivioMemoria()["fiscal-relations-view"]

    async def scenario():
        await db["f24_unificato"].insert_one({
            "id": "F24-IVA-1",
            "file_name": "F24 gennaio 2025.pdf",
            "quietanza_id": "Q-1",
            "protocollo_quietanza": "250216123456",
            "data_pagamento_quietanza": "2025-02-16",
            "movimento_bancario_id": "EC-2025-02-16-100.00-aa",
            "data_pagamento_effettivo": "2025-02-16",
            "sezione_erario": [{
                "codice_tributo": "6001",
                "periodo_riferimento": "01/2025",
                "importo_debito": 100,
            }],
        })
        await db["quietanze_f24"].insert_one({
            "id": "Q-1", "filename": "quietanza gennaio.pdf",
        })
        await db["estratto_conto_movimenti"].insert_one({
            "id": "EC-2025-02-16-100.00-aa", "data": "2025-02-16",
        })
        await db["documents_inbox"].insert_many([
            {"id": "A-1", "category": "avviso_bonario", "filename": "Lettera ADE gennaio 2025.pdf"},
            {"id": "A-AMB", "category": "avviso_bonario", "filename": "Lettera ADE 2025.pdf"},
        ])
        await db["agenti_segnalazioni"].insert_one({
            "agente": "FiscaleSentinella",
            "dati_riferimento": {
                "documento_id": "A-1", "periodo": "01/2025", "codice_tributo": "6001",
            },
        })
        return await prove_fiscali_periodo(db, 2025)

    result = _run(scenario())
    january = next(period for period in result["periodi"] if period["periodo"] == "2025-01")
    assert january["stato_iva"] == "PAGATA_E_VERIFICATA"
    assert january["f24"][0]["quietanza_url"].endswith("/Q-1")
    assert january["f24"][0]["movimento_bancario_id"] == "EC-2025-02-16-100.00-aa"
    notice = january["avvisi_ade"][0]
    assert notice["associazione_certa"] is True
    assert notice["f24_ids"] == ["F24-IVA-1"]
    assert notice["messaggio_pagamento"] == (
        "Pagamento richiesto da Agenzia delle Entrate pagato — vedi quietanza"
    )
    assert all(notice["id"] != "A-AMB" for period in result["periodi"] for notice in period["avvisi_ade"])


def test_quietanza_senza_banca_non_viene_presentata_come_riconciliazione_bancaria_certa():
    db = ClientArchivioMemoria()["fiscal-relations-view-receipt-only"]

    async def scenario():
        await db["f24_unificato"].insert_one({
            "id": "F24-IVA-2", "quietanza_id": "Q-2",
            "sezione_erario": [{
                "codice_tributo": "6002", "periodo_riferimento": "02/2025",
                "importo_debito": 80,
            }],
        })
        await db["quietanze_f24"].insert_one({"id": "Q-2"})
        return await prove_fiscali_periodo(db, 2025)

    result = _run(scenario())
    february = result["periodi"][0]
    assert february["stato_iva"] == "VERSATA_O_COMPENSATA_CON_QUIETANZA"
    assert february["f24"][0]["banca_verificata"] is False
    assert "movimento bancario da verificare" in february["f24"][0]["messaggio"]
