import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.routers.bank import assegni as assegni_router


async def _scenario_carnet_salvato(monkeypatch):
    db = AsyncMongoMockClient()["test_assegni_carnet"]
    monkeypatch.setattr(
        assegni_router.Database,
        "get_db",
        staticmethod(lambda: db),
    )

    esito = await assegni_router.genera_assegni(
        numero_primo="0208770000-01",
        quantita=3,
        anno=2026,
    )

    assert esito["success"] is True
    assert esito["generati"] == 3
    assert await db["assegni"].count_documents({"anno_creazione": 2026}) == 3

    righe = await assegni_router.list_assegni(
        skip=0, limit=1000, stato=None, fornitore_piva=None,
        search=None, anno=2026,
    )
    assert [r["numero"] for r in righe] == [
        "0208770000-01",
        "0208770000-02",
        "0208770000-03",
    ]


async def _scenario_carnet_duplicato(monkeypatch):
    db = AsyncMongoMockClient()["test_assegni_carnet_duplicato"]
    await db["assegni"].insert_one({"numero": "0208770001-02"})
    monkeypatch.setattr(
        assegni_router.Database,
        "get_db",
        staticmethod(lambda: db),
    )

    with pytest.raises(Exception) as exc:
        await assegni_router.genera_assegni(
            numero_primo="0208770001-01",
            quantita=3,
            anno=2026,
        )

    assert getattr(exc.value, "status_code", None) == 400
    assert await db["assegni"].count_documents({}) == 1


async def _scenario_carnet_numero_continuo(monkeypatch):
    db = AsyncMongoMockClient()["test_assegni_carnet_continuo"]
    monkeypatch.setattr(
        assegni_router.Database,
        "get_db",
        staticmethod(lambda: db),
    )

    esito = await assegni_router.genera_assegni(
        numero_primo="0208770985",
        quantita=3,
        anno=2026,
    )

    assert esito["numeri"] == ["0208770985", "0208770986", "0208770987"]
    assert esito["carnet_id"] == "0208770985"
    assert await db["assegni"].count_documents({"anno": 2026}) == 3


async def _scenario_carnet_formato_non_valido(monkeypatch):
    db = AsyncMongoMockClient()["test_assegni_carnet_formato_non_valido"]
    monkeypatch.setattr(
        assegni_router.Database,
        "get_db",
        staticmethod(lambda: db),
    )

    with pytest.raises(Exception) as exc:
        await assegni_router.genera_assegni(
            numero_primo="02087709A5",
            quantita=3,
            anno=2026,
        )

    assert getattr(exc.value, "status_code", None) == 400
    assert await db["assegni"].count_documents({}) == 0


async def _scenario_fatture_disponibili(monkeypatch):
    db = AsyncMongoMockClient()["test_fatture_disponibili_assegno"]
    await db["invoices"].insert_many([
        {
            "id": "f1", "invoice_key": "K1", "invoice_number": "10",
            "invoice_date": "2026-06-01", "supplier_name": "Fornitore A",
            "total_amount": 100.0, "pagato": False, "xml_content": "molto grande",
        },
        {
            "id": "f1-duplicata", "invoice_key": "K1", "invoice_number": "10",
            "invoice_date": "2026-06-01", "supplier_name": "Fornitore A",
            "total_amount": 100.0, "pagato": False,
        },
        {
            "id": "f2", "invoice_key": "K2", "invoice_number": "11",
            "invoice_date": "2026-06-02", "supplier_name": "Fornitore B",
            "total_amount": 200.0, "pagato": True,
        },
        {
            "id": "f3", "invoice_key": "K3", "invoice_number": "12",
            "invoice_date": "2025-06-02", "supplier_name": "Fornitore C",
            "total_amount": 300.0, "pagato": False,
        },
    ])
    monkeypatch.setattr(
        assegni_router.Database,
        "get_db",
        staticmethod(lambda: db),
    )

    righe = await assegni_router.fatture_disponibili_per_assegno(
        anno=2026, limit=1000,
    )

    assert len(righe) == 1
    assert righe[0]["invoice_key"] == "K1"
    assert "xml_content" not in righe[0]


async def _scenario_incassato_arricchito(monkeypatch):
    db = AsyncMongoMockClient()["test_assegno_incassato_arricchito"]
    await db["assegni"].insert_one({
        "id": "a-incassato", "numero": "0208770985", "stato": "incassato",
        "importo": 9760.0, "anno": 2026, "fattura_collegata": "f-1",
        "movimento_estratto_conto_id": "ec-1",
    })
    await db["invoices"].insert_one({
        "id": "f-1", "invoice_number": "120", "invoice_date": "2026-06-15",
        "supplier_name": "Fornitore Verificato S.r.l.",
    })
    await db["estratto_conto_movimenti"].insert_one({
        "id": "ec-1", "data": "2026-06-30",
    })
    monkeypatch.setattr(
        assegni_router.Database, "get_db", staticmethod(lambda: db),
    )

    righe = await assegni_router.list_assegni(
        skip=0, limit=1000, stato=None, fornitore_piva=None,
        search=None, anno=2026,
    )

    assert len(righe) == 1
    assegno = righe[0]
    assert assegno["fornitore_fattura"] == "Fornitore Verificato S.r.l."
    assert assegno["numero_fattura"] == "120"
    assert assegno["data_fattura"] == "2026-06-15"
    assert assegno["data_incasso"] == "2026-06-30"
    assert assegno["evidenza_estratto_conto_id"] == "ec-1"
    assert assegno["dati_riconciliazione_mancanti"] == []


def test_carnet_salvato_in_blocco_e_visibile_nell_anno(monkeypatch):
    asyncio.run(_scenario_carnet_salvato(monkeypatch))


def test_carnet_duplicato_non_inserisce_righe_parziali(monkeypatch):
    asyncio.run(_scenario_carnet_duplicato(monkeypatch))


def test_carnet_accetta_numero_bancario_continuo(monkeypatch):
    asyncio.run(_scenario_carnet_numero_continuo(monkeypatch))


def test_carnet_rifiuta_formati_ambigui_senza_salvare(monkeypatch):
    asyncio.run(_scenario_carnet_formato_non_valido(monkeypatch))


def test_fatture_disponibili_sono_leggere_aperte_e_deduplicate(monkeypatch):
    asyncio.run(_scenario_fatture_disponibili(monkeypatch))


def test_assegno_incassato_espone_fornitore_fattura_e_data_ec(monkeypatch):
    asyncio.run(_scenario_incassato_arricchito(monkeypatch))
