import asyncio
from datetime import date
from mongomock_motor import AsyncMongoMockClient
from app.services.piano_iva import arricchisci_piano_iva, quadro_lipe


def lipe(month, initial, delta, final, annual=0):
    return {
        "periodo": f"2026-{month:02d}",
        "quadratura_ok": True,
        "stato": "canonica",
        "credito_periodo_precedente": initial,
        "credito_anno_precedente": annual,
        "iva_esigibile": max(delta, 0),
        "iva_detratta": max(-delta, 0),
        "iva_dovuta_o_credito": abs(delta),
        "iva_dovuta_o_credito_segno": "debito" if delta > 0 else "credito",
        "iva_da_versare_o_credito": abs(final),
        "iva_da_versare_o_credito_segno": "debito" if final > 0 else "credito",
    }


def grid():
    return {
        "anno": 2026,
        "mancano": [],
        "voci": [
            {
                "voce": {"id": "iva_mensile", "etichetta": "IVA mensile (6001-6012)"},
                "caselle": [
                    {
                        "periodo": str(m),
                        "etichetta_periodo": f"{m:02d}/2026",
                        "stato": "nessun_f24",
                        "scadenza": f"2026-{m+1:02d}-16",
                        "giorni_scaduto": 200,
                        "mandatory": False,
                        "expectation_status": "ATTESO",
                        "modelli": [],
                        "debito_cents": 0,
                        "residuo_cents": 0,
                    }
                    for m in [1, 2, 3]
                ],
            }
        ],
    }


def test_il_credito_annuale_si_consuma_senza_pagamento_e_il_debito_richiede_quietanza():
    async def scenario():
        db = AsyncMongoMockClient()["iva_credito"]
        await db.lipe_periodi.insert_many(
            [lipe(1, 0, 60, -40, annual=100), lipe(2, 40, 30, -10), lipe(3, 10, 35, 25)]
        )
        g = grid()
        g["voci"][0]["caselle"][2].update(
            modelli=[{"tipo_documento": "quietanza"}],
            debito_cents=2000,
            residuo_cents=0,
        )
        result = await arricchisci_piano_iva(db, g, date(2026, 10, 11))
        jan, feb, mar = result["voci"][0]["caselle"]
        assert jan["iva"]["credito_iniziale_cents"] == 10000
        assert (
            jan["iva"]["credito_residuo_cents"] == 4000
            and jan["stato"] == "iva_a_credito"
        )
        assert (
            feb["iva"]["credito_residuo_cents"] == 1000
            and feb["iva"]["riporto_coerente"] is True
        )
        assert mar["residuo_cents"] == 500 and mar["stato"] == "scaduto_non_pagato"
        assert len(result["mancano"]) == 1

    asyncio.run(scenario())


def test_credito_incoerente_e_riporto_annuale_non_indicato_non_vengono_inventati():
    q = quadro_lipe({**lipe(1, 0, -100, -100), "credito_anno_precedente": None})
    assert q["riporto_annuale_indicato"] is False
    assert q["credito_iniziale_cents"] == 0
    assert quadro_lipe({**lipe(1, 0, 10, 10), "quadratura_ok": False}) is None


def test_senza_lipe_e_dati_completi_il_credito_non_diventa_zero(monkeypatch):
    async def missing(*args, **kw):
        return {
            "stato_calcolo": "DATI_MANCANTI",
            "attendibile": False,
            "credito_periodo_cents": None,
            "debito_periodo_cents": None,
            "motivi": ["nessun_corrispettivo_nel_mese"],
        }

    monkeypatch.setattr("app.services.piano_iva.get_iva_period_snapshot", missing)

    async def scenario():
        r = await arricchisci_piano_iva(
            AsyncMongoMockClient()["missing"], grid(), date(2026, 10, 11)
        )
        c = r["voci"][0]["caselle"][0]
        assert c["iva"]["credito_residuo_cents"] is None
        assert c["stato"] == "iva_da_verificare"

    asyncio.run(scenario())


def test_email_commercialista_non_inventa_credito_o_pagamento(monkeypatch):
    async def missing(*args, **kw):
        return {"stato_calcolo": "DATI_MANCANTI", "attendibile": False}
    monkeypatch.setattr("app.services.piano_iva.get_iva_period_snapshot", missing)
    async def scenario():
        db = AsyncMongoMockClient()["iva_mail"]
        await db.iva_comunicazioni.insert_one({
            "periodo": "2026-02", "verificato": True,
            "compensazione_comunicata": True, "source_message_id": "mail-fixture",
            "source_sha256": "a" * 64, "debito_mese_cents": 360000,
        })
        result = await arricchisci_piano_iva(db, grid(), date(2026, 10, 12))
        c = result["voci"][0]["caselle"][1]
        assert c["stato"] == "iva_compensazione_comunicata"
        assert c["iva"]["comunicazione"]["debito_mese_cents"] == 360000
        assert c["iva"]["credito_residuo_cents"] is None
        assert c["iva"]["verificato"] is False
        assert c["stato"] != "pagato"
    asyncio.run(scenario())
