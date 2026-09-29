import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.assegni_beneficiario import ricompila_beneficiari_da_fatture


def _esegui(assegni, fatture, **kw):
    async def scenario():
        db = ClientArchivioMemoria()["assegni_beneficiario"]
        for a in assegni:
            await db.assegni.insert_one(dict(a))
        for f in fatture:
            await db.invoices.insert_one(dict(f))
        esito = await ricompila_beneficiari_da_fatture(db, **kw)
        return esito, await db.assegni.find({}, {"_id": 0}).to_list(50)

    return asyncio.run(scenario())


def _assegno(id_, fatture, **extra):
    return {"id": id_, "numero": id_, "stato": "incassato",
            "fatture_collegate": [{"fattura_id": f, "quota": 10} for f in fatture], **extra}


def _fattura(id_, forn_id, nome):
    return {"id": id_, "supplier_id": forn_id, "supplier_name": nome}


def test_beneficiario_vuoto_prende_il_fornitore_della_fattura():
    esito, assegni = _esegui([_assegno("a1", ["f1"])], [_fattura("f1", "45", "Amazon Business EU")])
    assert esito["aggiornati"] == 1
    assert assegni[0]["beneficiario"] == "Amazon Business EU"
    assert assegni[0]["storico"][0]["azione"] == "beneficiario_da_fattura"


def test_beneficiario_gia_scritto_non_si_tocca():
    esito, assegni = _esegui(
        [_assegno("a1", ["f1"], beneficiario="Scelto dal titolare")],
        [_fattura("f1", "45", "Amazon Business EU")],
    )
    assert esito["esaminati"] == 0
    assert assegni[0]["beneficiario"] == "Scelto dal titolare"


def test_fatture_di_fornitori_diversi_restano_ambigue():
    esito, assegni = _esegui(
        [_assegno("a1", ["f1", "f2"], beneficiario="-")],
        [_fattura("f1", "45", "Amazon"), _fattura("f2", "9", "Rossi Srl")],
    )
    assert esito["ambigui"] == 1 and esito["aggiornati"] == 0
    assert assegni[0]["beneficiario"] == "-"


def test_assegno_senza_fatture_e_dry_run_non_scrivono():
    esito, assegni = _esegui(
        [{"id": "a0", "numero": "a0", "stato": "incassato"}, _assegno("a1", ["f1"])],
        [_fattura("f1", "45", "Amazon")], dry_run=True,
    )
    assert esito["aggiornati"] == 1 and esito["dry_run"] is True
    assert all(not a.get("beneficiario") for a in assegni)


def test_secondo_giro_non_rifa_nulla():
    async def scenario():
        db = ClientArchivioMemoria()["assegni_beneficiario_bis"]
        await db.assegni.insert_one(_assegno("a1", ["f1"]))
        await db.invoices.insert_one(_fattura("f1", "45", "Amazon"))
        await ricompila_beneficiari_da_fatture(db)
        return await ricompila_beneficiari_da_fatture(db)

    assert asyncio.run(scenario())["aggiornati"] == 0
