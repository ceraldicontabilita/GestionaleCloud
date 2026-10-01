import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from mongomock_motor import AsyncMongoMockClient

from app.lotti.servizi import ordini_hotel as servizio
from app.routers import colazioni


def test_endpoint_usa_catalogo_autorizzato_e_non_un_prezzo_del_browser(monkeypatch):
    db = AsyncMongoMockClient()["endpoint_ordini_hotel_test"]
    monkeypatch.setattr(servizio, "db", db)

    async def contesto(_sid, _token):
        return ({
            "interno:p1": {
                "chiave": "interno:p1", "origine": "produzione_interna",
                "nome": "Sfogliatella", "prezzo": 2.4, "allergeni": ["Glutine"],
            }
        }, {"struttura": {"nome": "Hotel Centro"}})

    monkeypatch.setattr(colazioni, "_contesto_ordine_albergatore", contesto)
    domani = datetime.now(ZoneInfo("Europe/Rome")).date() + timedelta(days=1)
    richiesta = colazioni.OrdineHotelRequest(
        sid="hotel-1", p="sessione-opaca", data_consegna=domani,
        righe=[colazioni.RigaOrdineHotel(chiave="interno:p1", quantita=4)],
        nota="mattina", idempotenza="req-1",
    )

    risposta = asyncio.run(colazioni.crea_ordine_prodotti_hotel(richiesta))

    assert risposta["ok"] is True
    assert risposta["ordine"]["struttura_nome"] == "Hotel Centro"
    assert risposta["ordine"]["totale"] == 9.6
    assert risposta["ordine"]["righe"][0]["prezzo_unitario"] == 2.4


def test_endpoint_rifiuta_prodotto_non_assegnato(monkeypatch):
    db = AsyncMongoMockClient()["endpoint_ordini_hotel_negato_test"]
    monkeypatch.setattr(servizio, "db", db)

    async def contesto(_sid, _token):
        return ({}, {"struttura": {"nome": "Hotel Centro"}})

    monkeypatch.setattr(colazioni, "_contesto_ordine_albergatore", contesto)
    domani = datetime.now(ZoneInfo("Europe/Rome")).date() + timedelta(days=1)
    richiesta = colazioni.OrdineHotelRequest(
        sid="hotel-1", p="sessione-opaca", data_consegna=domani,
        righe=[colazioni.RigaOrdineHotel(chiave="interno:non-autorizzato", quantita=1)],
    )

    try:
        asyncio.run(colazioni.crea_ordine_prodotti_hotel(richiesta))
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 422
        assert "non disponibile" in str(getattr(exc, "detail", ""))
    else:
        raise AssertionError("Il prodotto non assegnato doveva essere rifiutato")
