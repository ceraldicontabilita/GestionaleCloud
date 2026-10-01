"""Collaudo funzionale: su `invoices` l'`id` e' un numero su meta' delle righe (CLAUDE.md, regola 12).

Le pagine mandano l'id come lo ricevono (un numero) e l'URL lo porta come testo: ogni azione dell'utente su
una fattura con id numerico deve trovarla. Qui si prova ogni azione che la UI fa su una fattura, con una
fattura il cui id e' un numero.
"""
import pytest

from tests.fatture._scenari_comuni import (
    app_con, archivio_scenari, crea_fornitore, esegui, fattura, importa, richiesta, tutti, xml_fattura,
)

__all__ = ["archivio_scenari"]

ID = 850878

AZIONI = [
    ("GET", "/api/fatture/{id}", None),
    ("GET", "/api/invoices/{id}", None),
    ("GET", "/api/fatture-ricevute/fattura/{id}", None),
    ("GET", "/api/fatture-ricevute/fattura/{id}/storia", None),
    ("GET", "/api/fatture-ricevute/fattura/{id}/allegati", None),
    ("GET", "/api/fatture-ricevute/fattura/{id}/candidati-bancari", None),
    ("GET", "/api/fatture-ricevute/fattura/{id}/view-assoinvoice", None),
    ("GET", "/api/fatture/{id}/entita-correlate", None),
    ("PUT", "/api/fatture-ricevute/fattura/{id}", {"note": "controllata"}),
    ("PUT", "/api/fatture/{id}/classifica", {"centro_costo_id": "1.3_MATERIE_PRIME_PASTICCERIA"}),
    ("PUT", "/api/fatture/{id}/paga", None),
    ("DELETE", "/api/fatture/{id}", None),
]


def _app():
    from app.routers.fatture_module import router as ricevute
    from app.routers.invoices.fatture_upload import router as upload
    from app.routers.invoices.invoices_main import router as invoices

    return app_con((upload, "/api/fatture"), (invoices, "/api/invoices"), (ricevute, "/api/fatture-ricevute"))


@pytest.mark.parametrize("metodo,url,corpo", AZIONI, ids=[f"{m} {u.split('/api/')[1]}" for m, u, _ in AZIONI])
def test_ogni_azione_sulla_fattura_con_id_numerico_la_trova(archivio_scenari, metodo, url, corpo):
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="contanti", iban=None)
        esito = await importa(db, xml_fattura(), "drive")
        # su meta' delle righe di produzione l'id e' un numero
        await db["invoices"].update_one({"id": esito["id"]}, {"$set": {"id": ID}})
        for coll, campo in (("partite_aperte", "documento_id"), ("prima_nota_banca", "fattura_id"),
                            ("movimenti_contabili", "fattura_id")):
            await db[coll].update_many({campo: esito["id"]}, {"$set": {campo: ID}})
        risposta = await richiesta(_app(), metodo, url.format(id=ID), json=corpo)
        return risposta, await tutti(db, "invoices")

    risposta, fatture = esegui(scenario())
    assert risposta.status_code == 200, f"{metodo} {url}: {risposta.status_code} {risposta.text[:200]}"
    assert len(fatture) == 1


def _app_pagamenti():
    from app.routers.fatture_module import router as ricevute

    return app_con((ricevute, "/api/fatture-ricevute"))


def _con_id_numerico(db, esito_id):
    async def _rinumera():
        await db["invoices"].update_one({"id": esito_id}, {"$set": {"id": ID}})
        for coll, campo in (("partite_aperte", "documento_id"), ("prima_nota_banca", "fattura_id"),
                            ("prima_nota_cassa", "fattura_id"), ("movimenti_contabili", "fattura_id")):
            await db[coll].update_many({campo: esito_id}, {"$set": {campo: ID}})
    return _rinumera()


def test_paga_manuale_in_cassa_con_id_numerico(archivio_scenari):
    """«Paga» da Scadenze o da Fornitori: l'id arriva come numero dal JSON della pagina."""
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="contanti", iban=None)
        esito = await importa(db, xml_fattura(), "drive")
        await _con_id_numerico(db, esito["id"])
        risposta = await richiesta(_app_pagamenti(), "POST", "/api/fatture-ricevute/paga-manuale", json={
            "fattura_id": ID, "metodo": "cassa", "importo": 122.0, "fornitore": "FORNITORE TEST SRL",
            "numero_fattura": "123", "data_pagamento": "2026-09-12"})
        return risposta, await fattura(db, ID), await tutti(db, "prima_nota_cassa")

    risposta, f, cassa = esegui(scenario())
    from tests.fatture._scenari_comuni import e_pagata_su_ogni_campo

    assert risposta.status_code == 201, risposta.text
    assert e_pagata_su_ogni_campo(f)
    assert len(cassa) == 1 and cassa[0]["importo"] == 122.0


def test_collega_bonifico_alla_fattura_con_id_numerico(archivio_scenari):
    """«Collega bonifico» dalla scheda fattura: il movimento d'estratto scelto paga la fattura."""
    db = archivio_scenari
    from tests.fatture._scenari_comuni import FileCsv, importa_estratto, riga_csv

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        esito = await importa(db, xml_fattura(), "drive")
        await _con_id_numerico(db, esito["id"])
        await importa_estratto(FileCsv([riga_csv(
            "VOSTRA DISPOSIZIONE - VS.DISP. RIF. MBVT12345678/001 FAVORE FORNITORE TEST SRL FATT. 123", "-122,00")]))
        movimento = (await tutti(db, "estratto_conto_movimenti"))[0]
        candidati = await richiesta(_app_pagamenti(), "GET", f"/api/fatture-ricevute/fattura/{ID}/candidati-bancari")
        risposta = await richiesta(_app_pagamenti(), "POST", "/api/fatture-ricevute/riconcilia-con-estratto-conto",
                                   json={"fattura_id": ID, "movimento_id": movimento["id"]})
        return candidati, risposta, await fattura(db, ID), await tutti(db, "estratto_conto_movimenti")

    candidati, risposta, f, ec = esegui(scenario())
    assert candidati.status_code == 200 and candidati.json()["candidati"], candidati.text
    assert risposta.status_code == 200, risposta.text
    assert f["pagato"] is True and ec[0]["riconciliato"] is True
