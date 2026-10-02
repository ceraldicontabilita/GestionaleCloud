"""La data di pagamento di una fattura pagata con assegno e' quella dell'addebito.

Prima dell'addebito vale la dichiarazione del titolare (compilazione dell'assegno
o report), con `data_pagamento_fonte = dichiarata`; quando l'assegno e' addebitato
nell'estratto ufficiale, `fatture_pagate_con_assegno` (job bancario corto) porta
sulla fattura la data dell'addebito con `data_pagamento_fonte = addebito_banca`.
Ritirare la dichiarazione azzera data e fonte.
"""
from app.services.bonifiche_automatiche import fatture_pagate_con_assegno
from app.services.pagamenti_dichiarati_titolare import (
    DATA_PAGAMENTO_ADDEBITO_BANCA, DATA_PAGAMENTO_DICHIARATA,
    dichiara_pagamento_banca, ritira_dichiarazione_banca,
)

from tests.fatture._scenari_comuni import (  # noqa: F401 - fixture pytest
    archivio_scenari, crea_fornitore, esegui, fattura, importa_xml, xml_fattura,
)


def _assegno_addebitato(fattura_id, data_incasso="2026-09-25"):
    return {"id": "a1", "numero": "0000000001", "stato": "incassato",
            "evidenza_bancaria_ufficiale": True, "movimento_estratto_conto_id": "m1",
            "data_incasso": data_incasso, "importo": 122.0, "fattura_id": fattura_id}


def test_dichiarata_poi_addebitata_la_data_segue_l_addebito(archivio_scenari):
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        esito = await importa_xml(db, xml_fattura(data="2026-09-10"))
        f = await fattura(db, esito["id"])
        await dichiara_pagamento_banca(db, f, metodo="assegno", data="2026-09-12",
                                       assegno_numero="0000000001")
        dichiarata = await fattura(db, f["id"])

        await db["assegni"].insert_one(_assegno_addebitato(f["id"]))
        primo = await fatture_pagate_con_assegno(db)
        secondo = await fatture_pagate_con_assegno(db)
        addebitata = await fattura(db, f["id"])
        return dichiarata, primo, secondo, addebitata

    dichiarata, primo, secondo, addebitata = esegui(scenario())
    assert dichiarata["data_pagamento"] == "2026-09-12"
    assert dichiarata["data_pagamento_fonte"] == DATA_PAGAMENTO_DICHIARATA
    assert dichiarata["pagato"] is True and dichiarata["in_attesa_riscontro_banca"] is True

    assert primo == {"fatture": 1, "totale_diverso": 0}
    assert secondo == {"fatture": 0, "totale_diverso": 0}          # idempotente
    assert addebitata["data_pagamento"] == "2026-09-25"             # l'addebito, non la compilazione
    assert addebitata["data_pagamento_fonte"] == DATA_PAGAMENTO_ADDEBITO_BANCA
    assert addebitata["stato_pagamento"] == "pagata" and addebitata["paid"] is True
    assert addebitata["pagamento_prova"] == {"tipo": "assegno", "assegni": ["a1"]}


def test_ritirare_la_dichiarazione_azzera_data_e_fonte(archivio_scenari):
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        esito = await importa_xml(db, xml_fattura(data="2026-09-10"))
        f = await fattura(db, esito["id"])
        await dichiara_pagamento_banca(db, f, metodo="assegno", data="2026-09-12")
        await ritira_dichiarazione_banca(db, f["id"], motivo="assegno annullato")
        return await fattura(db, f["id"])

    ritirata = esegui(scenario())
    assert ritirata["data_pagamento"] is None and ritirata["data_pagamento_fonte"] is None
    assert ritirata["pagato"] is False


def test_senza_addebito_ufficiale_la_data_resta_quella_dichiarata(archivio_scenari):
    """Un assegno solo compilato (nessuna evidenza bancaria) non sposta la data."""
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        esito = await importa_xml(db, xml_fattura(data="2026-09-10"))
        f = await fattura(db, esito["id"])
        await dichiara_pagamento_banca(db, f, metodo="assegno", data="2026-09-12")
        compilato = {**_assegno_addebitato(f["id"]), "stato": "emesso",
                     "evidenza_bancaria_ufficiale": False, "movimento_estratto_conto_id": None}
        await db["assegni"].insert_one(compilato)
        esito_job = await fatture_pagate_con_assegno(db)
        return esito_job, await fattura(db, f["id"])

    esito_job, f = esegui(scenario())
    assert esito_job == {"fatture": 0, "totale_diverso": 0}
    assert f["data_pagamento"] == "2026-09-12" and f["data_pagamento_fonte"] == DATA_PAGAMENTO_DICHIARATA
