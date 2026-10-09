import asyncio

from app.services import colazioni_notifiche as servizio


def test_senza_telegram_non_consuma_la_coda(monkeypatch):
    monkeypatch.setattr(servizio, "is_configured", lambda: False)

    async def vietato(*_args, **_kwargs):
        raise AssertionError("non deve chiamare Supabase")

    monkeypatch.setattr(servizio, "_rpc_runtime", vietato)
    assert asyncio.run(servizio.processa_notifiche_colazioni()) == {
        "configurato": False, "presi": 0, "inviati": 0, "falliti": 0,
    }


def test_invia_prenotazione_e_registra_esito(monkeypatch):
    monkeypatch.setattr(servizio, "is_configured", lambda: True)
    chiamate = []

    async def rpc(nome, payload):
        chiamate.append((nome, payload))
        if nome == "bb_notifiche_operative_prendi":
            return [{
                "job_id": "00000000-0000-0000-0000-000000000001",
                "tipo": "prenotazione_hotel",
                "payload": {
                    "struttura": "Hotel Enzo", "camera": "12",
                    "periodo": "02/10/2026", "quantita": 2,
                    "colazione": "Colazione da €6", "totale": 12,
                    "servizio_tavolo": False,
                },
            }]
        return None

    async def invia(testo):
        assert "Nuovo acquisto colazioni hotel" in testo
        assert "Hotel Enzo" in testo and "Camera: <b>12</b>" in testo
        return {"success": True, "message_id": 91}

    monkeypatch.setattr(servizio, "_rpc_runtime", rpc)
    monkeypatch.setattr(servizio, "send_notification", invia)
    esito = asyncio.run(servizio.processa_notifiche_colazioni())
    assert esito == {"configurato": True, "presi": 1, "inviati": 1, "falliti": 0}
    assert chiamate[-1] == (
        "bb_notifiche_operative_esito",
        {"pjob": "00000000-0000-0000-0000-000000000001", "pinviato": True,
         "pprovider": "91", "perrore": ""},
    )


def test_extra_mostra_prodotti_e_importo_senza_dati_ospite():
    testo = servizio._testo({
        "tipo": "extra_ospite",
        "payload": {"struttura": "Hotel", "camera": "7", "totale": 4.5,
                    "extra": [{"nome": "Cappuccino", "qta": 2}]},
    })
    assert "2x Cappuccino" in testo
    assert "€ 4.50" in testo
    assert "ospite" not in testo.lower()
