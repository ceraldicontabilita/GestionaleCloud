import asyncio

from app.services import colazioni_recensioni as servizio


def test_senza_credenziali_non_legge_ne_invia(monkeypatch):
    monkeypatch.setattr(servizio.settings, "WHATSAPP_CLOUD_PHONE_NUMBER_ID", "")
    monkeypatch.setattr(servizio.settings, "WHATSAPP_CLOUD_ACCESS_TOKEN", "")

    async def vietato(*_args, **_kwargs):
        raise AssertionError("non deve chiamare Supabase")

    monkeypatch.setattr(servizio, "_rpc_runtime", vietato)
    esito = asyncio.run(servizio.processa_inviti_recensioni())
    assert esito == {"configurato": False, "presi": 0, "inviati": 0, "falliti": 0}


def test_invia_e_registra_solo_job_rivendicati(monkeypatch):
    monkeypatch.setattr(servizio.settings, "WHATSAPP_CLOUD_PHONE_NUMBER_ID", "phone-id")
    monkeypatch.setattr(servizio.settings, "WHATSAPP_CLOUD_ACCESS_TOKEN", "token")
    monkeypatch.setattr(servizio.settings, "COLAZIONI_PUBLIC_URL", "https://example.test/convenzioni/")
    chiamate = []

    async def rpc(nome, payload):
        chiamate.append((nome, payload))
        if nome == "bb_recensioni_inviti_prendi":
            return [{
                "job_id": "00000000-0000-0000-0000-000000000001",
                "telefono": "+393331234567",
                "struttura": "Hotel Prova",
                "review_token": "00000000-0000-0000-0000-000000000002",
            }]
        return None

    async def invia(**dati):
        assert dati == {
            "telefono": "+393331234567",
            "struttura": "Hotel Prova",
            "link": "https://example.test/convenzioni/#/recensione-invito/00000000-0000-0000-0000-000000000002",
        }
        return "wamid.1"

    monkeypatch.setattr(servizio, "_rpc_runtime", rpc)
    monkeypatch.setattr(servizio, "_invia_template", invia)
    esito = asyncio.run(servizio.processa_inviti_recensioni())
    assert esito == {"configurato": True, "presi": 1, "inviati": 1, "falliti": 0}
    assert chiamate[-1] == (
        "bb_recensioni_invito_esito",
        {
            "pjob": "00000000-0000-0000-0000-000000000001",
            "pinviato": True,
            "pprovider": "wamid.1",
            "perrore": "",
        },
    )
