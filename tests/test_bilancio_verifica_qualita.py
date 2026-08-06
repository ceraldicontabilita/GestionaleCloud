import asyncio
from mongomock_motor import AsyncMongoMockClient

from app.routers.accounting.contabilita_gestionale import (
    _bilancio_verifica_da_registro,
)


def test_non_confonde_compensazione_annuale_con_scritture_in_quadratura():
    async def scenario():
        db = AsyncMongoMockClient().db
        await db.movimenti_contabili.insert_many([
            {
                "id": "s1",
                "anno": 2026,
                "data": "2026-01-10",
                "righe": [
                    {"conto_codice": "01.01.01", "conto_nome": "Cassa", "dare": 100},
                    {"conto_codice": "04.01.01", "conto_nome": "Ricavi", "avere": 90},
                ],
            },
            {
                "id": "s2",
                "anno": 2026,
                "data": "2026-01-11",
                "righe": [
                    {"conto_codice": "05.01.01", "conto_nome": "Costi", "dare": 90},
                    {"conto_codice": "02.01.01", "conto_nome": "Debiti", "avere": 100},
                ],
            },
        ])
        return await _bilancio_verifica_da_registro(db, 2026, False)

    result = asyncio.run(scenario())

    assert result["totali"]["dare"] == result["totali"]["avere"] == 190
    assert result["qualita_registro"]["quadratura_totali"] is True
    assert result["qualita_registro"]["scritture_sbilanciate"] == 2
    assert result["qualita_registro"]["registro_valido"] is False
    assert result["quadratura"] is False


def test_segnala_righe_invalide_e_scritture_senza_righe():
    async def scenario():
        db = AsyncMongoMockClient().db
        await db.movimenti_contabili.insert_many([
            {
                "id": "valida-con-riga-errata",
                "anno": 2026,
                "data": "2026-02-10",
                "righe": [
                    {"conto_codice": "01.01.01", "conto_nome": "Cassa", "dare": 50},
                    {"conto_codice": "02.01.01", "conto_nome": "Debiti", "avere": 50},
                    {"conto_codice": "05.01.01", "conto_nome": "Costi", "dare": "non-numero"},
                    {"conto_codice": "", "conto_nome": "Senza conto", "dare": 1},
                ],
            },
            {"id": "vuota", "anno": 2026, "data": "2026-02-11", "righe": []},
        ])
        return await _bilancio_verifica_da_registro(db, 2026, False)

    result = asyncio.run(scenario())

    quality = result["qualita_registro"]
    assert quality["righe_non_numeriche"] == 1
    assert quality["righe_senza_conto"] == 1
    assert quality["scritture_senza_righe"] == 1
    assert quality["registro_valido"] is False
    assert result["completezza_registro"]["completo"] is False


def test_espone_il_patrimonio_netto_nel_riepilogo():
    async def scenario():
        db = AsyncMongoMockClient().db
        await db.movimenti_contabili.insert_one({
            "id": "apertura",
            "anno": 2026,
            "data": "2026-01-01",
            "righe": [
                {"conto_codice": "01.01.02", "conto_nome": "Banca", "dare": 1000},
                {"conto_codice": "03.01.01", "conto_nome": "Capitale", "avere": 1000},
            ],
        })
        return await _bilancio_verifica_da_registro(db, 2026, False)

    result = asyncio.run(scenario())

    assert result["quadratura"] is True
    assert result["riepilogo"]["n_conti_patrimonio_netto"] == 1
    assert {c["tipo"] for c in result["conti"]} == {"attivo", "patrimonio_netto"}
