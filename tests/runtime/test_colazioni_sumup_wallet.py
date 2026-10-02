from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import colazioni
from app.services import colazioni_sumup


def test_esito_checkout_paid_con_rimborso_parziale():
    esito = colazioni_sumup.esito_checkout({
        "id": "chk-1",
        "checkout_reference": "RICARICA-HOTEL-000001",
        "amount": 250,
        "currency": "EUR",
        "merchant_code": "MC1",
        "status": "PAID",
        "transactions": [{
            "id": "tx-1", "transaction_code": "ABC", "type": "PAYMENT",
            "status": "REFUNDED", "amount": 250, "refunded_amount": 40,
        }],
    })
    assert esito["stato"] == "PAID"
    assert esito["importo"] == Decimal("250.00")
    assert esito["rimborsato"] == Decimal("40.00")
    assert esito["transaction_id"] == "tx-1"
    assert "transactions" not in esito["audit"]


def test_rimborso_totale_senza_importo_usa_importo_transazione():
    esito = colazioni_sumup.esito_checkout({
        "id": "chk-2", "checkout_reference": "R-2", "amount": "100.00",
        "currency": "EUR", "status": "PAID",
        "transactions": [{"id": "tx-2", "status": "REFUNDED", "amount": 100}],
    })
    assert esito["rimborsato"] == Decimal("100.00")


def test_creazione_checkout_passa_dal_backend_e_collega_il_riferimento(monkeypatch):
    chiamate = []

    async def rpc_pubblica(nome, payload):
        assert nome == "bb_alb_ricarica_prepara"
        assert payload["sid"] == "11111111-1111-1111-1111-111111111111"
        return {"id": "22222222-2222-2222-2222-222222222222",
                "riferimento": "RICARICA-HOTEL-000123", "importo": "100.00",
                "struttura": "Hotel Enzo", "stato": "CREATA"}

    async def rpc_runtime(nome, payload):
        chiamate.append((nome, payload))

    async def crea(**kwargs):
        assert kwargs["riferimento"] == "RICARICA-HOTEL-000123"
        assert kwargs["importo"] == Decimal("100.00")
        return {"id": "checkout-1", "url": "https://checkout.sumup.com/pay/checkout-1",
                "merchant_code": "MC1", "status": "PENDING"}

    monkeypatch.setattr(colazioni, "_rpc_bb", rpc_pubblica)
    monkeypatch.setattr(colazioni, "_rpc_runtime_bb", rpc_runtime)
    monkeypatch.setattr(colazioni, "_url_ricariche", lambda: ("https://example.test/ritorno", "https://example.test/webhook"))
    monkeypatch.setattr(colazioni_sumup, "crea_checkout", crea)
    app = FastAPI()
    app.include_router(colazioni.router, prefix="/api/colazioni")
    risposta = TestClient(app).post("/api/colazioni/ricariche/sumup", json={
        "sid": "11111111-1111-1111-1111-111111111111", "p": "tk:hotel",
        "importo": 100, "idempotenza": "richiesta-123456",
    })
    assert risposta.status_code == 200, risposta.text
    assert risposta.json()["url"].startswith("https://checkout.sumup.com/")
    assert chiamate[0][0] == "bb_ricarica_collega_checkout"


def test_webhook_ignora_eventi_sconosciuti_e_verifica_quelli_sumup(monkeypatch):
    verificati = []

    async def applica(checkout_id):
        verificati.append(checkout_id)
        return {"stato": "PAID"}

    monkeypatch.setattr(colazioni, "_applica_checkout_sumup", applica)
    app = FastAPI()
    app.include_router(colazioni.router, prefix="/api/colazioni")
    client = TestClient(app)
    assert client.post("/api/colazioni/ricariche/sumup/webhook", json={
        "event_type": "NUOVO_EVENTO", "id": "x"
    }).status_code == 204
    assert verificati == []
    assert client.post("/api/colazioni/ricariche/sumup/webhook", json={
        "event_type": "CHECKOUT_STATUS_CHANGED", "id": "checkout-9"
    }).status_code == 204
    assert verificati == ["checkout-9"]
