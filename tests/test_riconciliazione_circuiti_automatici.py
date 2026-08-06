import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services import riconciliazione_bancaria as mod


def _run(coro):
    return asyncio.run(coro)


async def _noop(*args, **kwargs):
    return None


def _patch_db(monkeypatch, name):
    db = AsyncMongoMockClient()[name]
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    monkeypatch.setattr(mod, "_propaga_fattura_pagata", _noop)
    monkeypatch.setattr(mod, "_registra_match_partita_aperta", _noop)
    monkeypatch.setattr(mod, "_alert_non_riconciliato", _noop)
    monkeypatch.setattr(mod, "_alert_pagamento_multiplo", _noop)
    return db


def _fattura(fid, numero, fornitore, importo, data, **extra):
    return {
        "id": fid,
        "invoice_number": numero,
        "invoice_date": data,
        "supplier_name": fornitore,
        "supplier_vat": extra.pop("supplier_vat", "01234567890"),
        "total_amount": importo,
        "importo_residuo": importo,
        "importo_pagato": 0.0,
        "pagato": False,
        "stato_pagamento": "da_pagare",
        **extra,
    }


def test_quattro_componenti_numia_chiudono_un_solo_trasferimento(monkeypatch):
    async def scenario():
        db = _patch_db(monkeypatch, "numia_quattro_componenti")
        await db.prima_nota_banca.insert_one({
            "id": "trasf-pos", "source": "trasferimento_pos",
            "data": "2026-07-16", "giorno_vendita": "2026-07-16",
            "importo": 1274.90, "riconciliato": False,
        })
        componenti = [
            ("ec-amex", 43.80, "INC.POS CARTE CREDIT - NUMIA-AMEX DEL 16/07/26"),
            ("ec-bncmt", 99.30, "INCAS. TRAMITE P.O.S - NUMIA-BNCMT DEL 16/07/26"),
            ("ec-inter-1", 281.50, "INC.POS CARTE CREDIT - NUMIA-INTER DEL 16/07/26"),
            ("ec-inter-2", 850.30, "INC.POS CARTE CREDIT - NUMIA-INTER DEL 16/07/26"),
        ]
        await db.estratto_conto_movimenti.insert_many([{
            "id": ec_id, "data": "2026-07-17", "tipo": "entrata",
            "importo": importo, "descrizione_originale": descrizione,
            "riconciliato": False,
        } for ec_id, importo, descrizione in componenti])

        await mod.riconcilia_movimenti_banca()

        trasferimento = await db.prima_nota_banca.find_one({"id": "trasf-pos"})
        assert trasferimento["accreditato_ec"] == 1274.90
        assert trasferimento["riconciliato"] is True
        assert await db.estratto_conto_movimenti.count_documents({
            "riconciliato": True,
            "tipo_riconciliazione": "accredito_pos_trasferimento",
        }) == 4

        # Secondo giro completamente idempotente.
        await mod.riconcilia_movimenti_banca()
        trasferimento = await db.prima_nota_banca.find_one({"id": "trasf-pos"})
        assert trasferimento["accreditato_ec"] == 1274.90

    _run(scenario())


def test_sdd_univoco_usa_creditore_importo_e_data(monkeypatch):
    async def scenario():
        db = _patch_db(monkeypatch, "sdd_univoco")
        await db.invoices.insert_one(_fattura(
            "fatt-eni", "2615268875", "Eni Plenitude S.p.A.",
            151.73, "2026-03-20",
        ))
        await db.estratto_conto_movimenti.insert_one({
            "id": "ec-eni", "data": "2026-04-17", "tipo": "uscita",
            "importo": 151.73,
            "descrizione_originale": (
                "ADDEBITO DIRETTO SDD - SDD CORE: MANDATO123 "
                "Eni Spa - Eni Regolamento Monetario"
            ),
            "riconciliato": False,
        })

        risultato = await mod.riconcilia_movimenti_banca()
        assert risultato["riconciliati_fatture"] == 1
        ec = await db.estratto_conto_movimenti.find_one({"id": "ec-eni"})
        assert ec["riconciliato"] is True
        assert ec["dettagli_riconciliazione"]["match_type"] == "sdd+fornitore+importo+data"

    _run(scenario())


def test_sdd_paypal_non_viene_scambiato_per_fattura(monkeypatch):
    evidenza = mod._evidenza_sdd_fattura_banca(
        _fattura("fatt-x", "X-1", "InfoCert S.p.A.", 42.62, "2026-07-15"),
        "ADDEBITO DIRETTO SDD PAYPAL EUROPE S.A.R.L.",
        42.62,
        "2026-07-17",
    )
    assert evidenza["collettore_escluso"] is True
    assert evidenza["auto_ammesso"] is False


def test_numero_assegno_e_importo_identificano_la_fattura(monkeypatch):
    async def scenario():
        db = _patch_db(monkeypatch, "assegno_numero_importo")
        await db.invoices.insert_one(_fattura(
            "fatt-kimbo", "0070008705", "KIMBO S.P.A.", 3065.90,
            "2026-03-16", metodo_pagamento="Assegno N.0208770769",
        ))
        await db.estratto_conto_movimenti.insert_one({
            "id": "ec-assegno", "data": "2026-03-20", "tipo": "uscita",
            "importo": 3065.90,
            "descrizione_originale": "VOSTRO ASSEGNO N. 0208770769",
            "riconciliato": False,
        })

        risultato = await mod.riconcilia_movimenti_banca()
        assert risultato["riconciliati_fatture"] == 1
        assegno = await db.assegni.find_one({"numero": "0208770769"})
        assert assegno["fattura_id"] == "fatt-kimbo"
        assert assegno["stato"] == "incassato"

    _run(scenario())
