import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.routers.prima_nota_module import banca
from app.services.scritture_contabili import riconcilia_accredito_pos_ec


def _run(coro):
    return asyncio.run(coro)


def test_badge_pos_verde_solo_se_importi_quadrano():
    async def scenario():
        db = AsyncMongoMockClient()["test_badge_pos_quadrato"]
        movimenti = [
            {"id": "pos-ok", "source": "trasferimento_pos", "importo": 1353.70,
             "accreditato_ec": 1353.70, "riconciliato": True},
            {"id": "pos-diff", "source": "trasferimento_pos", "importo": 1152.70,
             "accreditato_ec": 1098.40, "riconciliato": True},
        ]

        await banca._arricchisci_riconciliazione(db, movimenti)

        assert movimenti[0]["riconciliazione"]["verificata"] is True
        assert movimenti[0]["riconciliazione"]["differenza_ec"] == 0
        assert movimenti[1]["riconciliazione"]["verificata"] is False
        assert movimenti[1]["riconciliazione"]["accredito_trovato"] is True
        assert movimenti[1]["riconciliazione"]["differenza_ec"] == -54.30

    _run(scenario())


def test_accrediti_separati_diventano_verdi_solo_alla_quadratura():
    async def scenario():
        db = AsyncMongoMockClient()["test_pos_componenti"]
        await db["prima_nota_banca"].insert_one({
            "id": "trasferimento", "source": "trasferimento_pos",
            "giorno_vendita": "2026-07-05", "data": "2026-07-05",
            "importo": 100.0, "accreditato_ec": 0, "riconciliato": False,
        })
        for ec_id, importo in (("ec-60", 60.0), ("ec-40", 40.0)):
            await db["estratto_conto_movimenti"].insert_one({
                "id": ec_id, "data": "2026-07-06", "importo": importo,
                "descrizione_originale": "INC.POS CARTE CREDIT - NUMIA-INTER DEL 05/07/26",
            })

        assert await riconcilia_accredito_pos_ec(
            db, await db["estratto_conto_movimenti"].find_one({"id": "ec-60"}))
        parziale = await db["prima_nota_banca"].find_one({"id": "trasferimento"})
        assert parziale["accreditato_ec"] == 60.0
        assert parziale["riconciliato"] is False
        assert (await db["estratto_conto_movimenti"].find_one({"id": "ec-60"}))["riconciliato"] is False

        # Riesaminare la stessa componente non deve sommarla una seconda
        # volta: lo scheduler gira periodicamente sulle righe ancora aperte.
        assert await riconcilia_accredito_pos_ec(
            db, await db["estratto_conto_movimenti"].find_one({"id": "ec-60"}))
        ripetuto = await db["prima_nota_banca"].find_one({"id": "trasferimento"})
        assert ripetuto["accreditato_ec"] == 60.0

        assert await riconcilia_accredito_pos_ec(
            db, await db["estratto_conto_movimenti"].find_one({"id": "ec-40"}))
        completo = await db["prima_nota_banca"].find_one({"id": "trasferimento"})
        assert completo["accreditato_ec"] == 100.0
        assert completo["riconciliato"] is True
        for ec_id in ("ec-60", "ec-40"):
            ec = await db["estratto_conto_movimenti"].find_one({"id": ec_id})
            assert ec["riconciliato"] is True
            assert ec["tipo_riconciliazione"] == "accredito_pos_trasferimento"

    _run(scenario())


def test_differenza_di_un_euro_non_e_riconciliazione():
    async def scenario():
        db = AsyncMongoMockClient()["test_pos_un_euro"]
        await db["prima_nota_banca"].insert_one({
            "id": "trasferimento", "source": "trasferimento_pos",
            "giorno_vendita": "2026-07-05", "data": "2026-07-05",
            "importo": 100.0, "accreditato_ec": 0,
        })
        movimento = {
            "id": "ec-99", "data": "2026-07-06", "importo": 99.0,
            "descrizione_originale": "INC.POS CARTE CREDIT - NUMIA-INTER DEL 05/07/26",
        }
        await db["estratto_conto_movimenti"].insert_one(movimento)

        assert await riconcilia_accredito_pos_ec(db, movimento)

        trasferimento = await db["prima_nota_banca"].find_one({"id": "trasferimento"})
        assert trasferimento["riconciliato"] is False
        ec = await db["estratto_conto_movimenti"].find_one({"id": "ec-99"})
        assert ec["riconciliato"] is False
        assert ec["stato_riconciliazione"] == "da_verificare"

    _run(scenario())
