import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.handlers.estratto_conto import handler_matching_estratto_conto


@pytest.fixture
def db():
    return AsyncMongoMockClient()["test_gestionale"]


def test_f24_multi_tributo_per_solo_importo_resta_proposta_idempotente(db):
    asyncio.run(_test_f24_multi_tributo(db))


async def _test_f24_multi_tributo(db):
    await db["f24_unificato"].insert_one({
        "id": "f24-1",
        "totale_debito": 780.0,
        "tributi": [
            {"codice": "6006", "importo": 500.0},
            {"codice": "1040", "importo": 280.0},
        ],
        "riconciliato_banca": False,
    })
    await db["estratto_conto_movimenti"].insert_one({"id": "mov-f24"})
    payload = {
        "banca": "Banco BPM",
        "movimenti": [{
            "id": "mov-f24",
            "tipo": "uscita",
            "importo": 780.0,
            "data": "2026-07-16",
            "descrizione": "ADDEBITO F24 IVA E RITENUTE",
        }],
    }

    await handler_matching_estratto_conto(payload, db)
    await handler_matching_estratto_conto(payload, db)

    f24 = await db["f24_unificato"].find_one({"id": "f24-1"})
    movimento = await db["estratto_conto_movimenti"].find_one({"id": "mov-f24"})
    proposte = await db["operazioni_da_confermare"].find({
        "movimento_id": "mov-f24"
    }).to_list(10)
    assert f24["riconciliato_banca"] is False
    assert movimento.get("abbinato") is not True
    assert len(proposte) == 1
    assert proposte[0]["tipo"] == "abbinamento_f24_estratto_conto"
    assert proposte[0]["richiede_conferma"] is True


def test_stipendio_stesso_importo_non_modifica_cedolino_o_movimento(db):
    asyncio.run(_test_stipendio(db))


async def _test_stipendio(db):
    await db["prima_nota_salari"].insert_one({
        "id": "sal-1",
        "importo": 1000.0,
        "nome_dipendente": "Mario Rossi",
        "dipendente_id": "dip-1",
        "riconciliato": False,
    })
    await db["estratto_conto_movimenti"].insert_one({"id": "mov-sal"})

    await handler_matching_estratto_conto({
        "banca": "Banco BPM",
        "movimenti": [{
            "id": "mov-sal",
            "tipo": "uscita",
            "importo": 1000.0,
            "data": "2026-07-10",
            "descrizione": "BONIFICO STIPENDIO MARIO ROSSI",
        }],
    }, db)

    salario = await db["prima_nota_salari"].find_one({"id": "sal-1"})
    movimento = await db["estratto_conto_movimenti"].find_one({"id": "mov-sal"})
    proposta = await db["operazioni_da_confermare"].find_one({
        "movimento_id": "mov-sal"
    })
    assert salario["riconciliato"] is False
    assert salario.get("movimento_id") is None
    assert movimento.get("abbinato") is not True
    assert proposta["tipo"] == "abbinamento_stipendio_estratto_conto"
    assert proposta["identita_dipendente_presente"] is True


def test_pos_per_importo_e_data_non_chiude_corrispettivo(db):
    asyncio.run(_test_pos(db))


async def _test_pos(db):
    await db["corrispettivi"].insert_one({
        "id": "corr-1",
        "data": "2026-07-09",
        "totale": 500.0,
        "riconciliato": False,
    })
    await db["estratto_conto_movimenti"].insert_one({"id": "mov-pos"})

    await handler_matching_estratto_conto({
        "banca": "Banco BPM",
        "movimenti": [{
            "id": "mov-pos",
            "tipo": "entrata",
            "importo": 500.0,
            "data": "2026-07-10",
            "descrizione": "ACCREDITO NEXI PAGAMENTI ELETTRONICI",
        }],
    }, db)

    corrispettivo = await db["corrispettivi"].find_one({"id": "corr-1"})
    movimento = await db["estratto_conto_movimenti"].find_one({"id": "mov-pos"})
    proposta = await db["operazioni_da_confermare"].find_one({
        "movimento_id": "mov-pos"
    })
    assert corrispettivo["riconciliato"] is False
    assert corrispettivo.get("movimento_id") is None
    assert movimento.get("abbinato") is not True
    assert proposta["tipo"] == "abbinamento_pos_estratto_conto"
