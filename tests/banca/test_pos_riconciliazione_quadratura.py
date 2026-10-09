import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria

from app.routers.prima_nota_module import banca
from app.services.scritture_contabili import riconcilia_accredito_pos_ec


def _run(coro):
    return asyncio.run(coro)


def test_badge_pos_verde_solo_se_importi_quadrano():
    async def scenario():
        db = ClientArchivioMemoria()["test_badge_pos_quadrato"]
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
        db = ClientArchivioMemoria()["test_pos_componenti"]
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
        db = ClientArchivioMemoria()["test_pos_un_euro"]
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


def test_credito_sumup_chiuso_dal_payout_e_verde(monkeypatch):
    """Il payout che copre il giorno estingue il credito: non e' «da verificare»."""
    async def scenario():
        db = ClientArchivioMemoria()["test_pos_payout"]
        movimenti = [{
            "id": "sumup-25", "source": "trasferimento_pos", "gestore": "sumup",
            "data": "2026-09-25", "importo": 2702.40, "riconciliato": True,
            "stato_riconciliazione": "riconciliato", "payout_id": "SUMUP PID707481962",
        }]
        await banca._arricchisci_riconciliazione(db, movimenti)
        ric = movimenti[0]["riconciliazione"]
        assert ric["verificata"] is True
        assert ric["payout_id"] == "SUMUP PID707481962"
        assert ric["in_attesa_accredito"] is False

    _run(scenario())


def test_credito_non_ancora_dovuto_e_in_attesa_poi_da_verificare(monkeypatch):
    """Fino alla data del calendario POS e' un'attesa; dopo, un'anomalia."""
    async def scenario(oggi):
        monkeypatch.setattr(banca, "_oggi_roma", lambda: oggi)
        db = ClientArchivioMemoria()["test_pos_attesa"]
        movimenti = [{
            "id": "sumup-24", "source": "trasferimento_pos", "gestore": "sumup",
            "data": "2026-09-24", "importo": 3685.30, "riconciliato": False,
            "stato_riconciliazione": "da_verificare",
        }]
        await banca._arricchisci_riconciliazione(db, movimenti)
        return movimenti[0]["riconciliazione"]

    # Giovedi' 24/09: accredito previsto venerdi' 25/09.
    oggi = _run(scenario("2026-09-24"))
    assert oggi["verificata"] is False
    assert oggi["data_accredito_attesa"] == "2026-09-25"
    assert oggi["in_attesa_accredito"] is True
    scaduto = _run(scenario("2026-09-28"))
    assert scaduto["in_attesa_accredito"] is False
    assert scaduto["verificata"] is False
