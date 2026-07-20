"""Quadratura POS: il giorno viene dalla descrizione dell'estratto conto."""
import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.routers import pos_corrispettivi_check as pc


def _run(coro):
    return asyncio.run(coro)


def test_somma_circuiti_sul_giorno_del_riferimento_non_sulla_data_contabile():
    async def scenario():
        db = AsyncMongoMockClient()["test_accrediti_giorno_operazione"]
        await db["estratto_conto_movimenti"].insert_many([
            {
                "data": "2026-07-07", "importo": 1000.20,
                "descrizione_originale": (
                    "INCAS. TRAMITE P.O.S - NUMIA-BNCMT DEL 06/07/26 PDV 3757283/00012"
                ),
            },
            {
                "data": "2026-07-08", "importo": 300.30,
                "descrizione_originale": (
                    "INC.POS CARTE CREDIT - NUMIA-INTER DEL 06/07/26 PDV 3757283/00011"
                ),
            },
            {
                "data": "2026-07-08", "importo": 53.20,
                "descrizione_originale": (
                    "INCAS. TRAMITE P.O.S - NUMIA-PGBNT DEL 06/07/26 PDV 3757283/00012"
                ),
            },
        ])

        out = await pc._carica_accrediti_banca_pos(db, "2026-07-01", "2026-07-31")

        assert out == {"2026-07-06": 1353.70}

    _run(scenario())


def test_esclude_righe_numia_che_non_sono_accrediti_pos_giornalieri():
    async def scenario():
        db = AsyncMongoMockClient()["test_esclusioni_numia"]
        await db["estratto_conto_movimenti"].insert_many([
            {"data": "2026-07-09", "importo": 0.02,
             "descrizione_originale": "INC.POS CARTE CREDIT - REMUNERAZIONE DCC 06/26 NUMIA"},
            {"data": "2026-07-09", "importo": 12.00,
             "descrizione_originale": "SPESE - COMMISSIONI NUMIA"},
            {"data": "2026-07-09", "importo": 20.00,
             "descrizione_originale": "SPESE - FATTURA NUMIA"},
            {"data": "2026-07-09", "importo": 99.00,
             "descrizione_originale": "ACCREDITO NUMIA POS"},
            {"data": "2026-07-09", "importo": -50.00,
             "descrizione_originale": "INC.POS CARTE CREDIT - NUMIA-INTER DEL 08/07/26"},
        ])

        out = await pc._carica_accrediti_banca_pos(db, "2026-07-01", "2026-07-31")

        assert out == {}

    _run(scenario())


def test_riferimento_operazione_fuori_periodo_non_viene_contato():
    async def scenario():
        db = AsyncMongoMockClient()["test_periodo_giorno_operazione"]
        await db["estratto_conto_movimenti"].insert_one({
            "data": "2026-07-01", "importo": 700.00,
            "descrizione_originale": (
                "INC.POS CARTE CREDIT - NUMIA-INTER DEL 30/06/26 PDV 3757283/00011"
            ),
        })

        out = await pc._carica_accrediti_banca_pos(db, "2026-07-01", "2026-07-31")

        assert out == {}

    _run(scenario())


def test_riconoscimento_causale_richiede_numia_incasso_e_giorno():
    assert pc._e_accredito_pos_numia_con_giorno(
        "INCAS. TRAMITE P.O.S - NUMIA-BNCMT DEL 16/07/26 PDV 3757283/00012"
    )
    assert not pc._e_accredito_pos_numia_con_giorno(
        "INC.POS CARTE CREDIT - REMUNERAZIONE DCC 06/26 NUMIA"
    )
    assert not pc._e_accredito_pos_numia_con_giorno("ACCREDITO NUMIA POS")
