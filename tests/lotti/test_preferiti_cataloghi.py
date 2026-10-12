import asyncio

from mongomock_motor import AsyncMongoMockClient
from app.database import Database
from app.lotti.servizi.preferiti_cataloghi import articoli_acquistati, collega_preferiti, fatture_catalogo
from app.lotti.routers.utils import prezzi_fatture_per_fornitore, applica_prezzo_da_fatture
from app.lotti.routers import cataloghi_prezzi


def run(c):
    return asyncio.run(c)


def fattura(**campi):
    return {"id": "f1", "supplier_name": "ME.PA. ALIMENTARI S.R.L.", "supplier_vat": "04352551214",
            "invoice_date": "2026-09-14", "tipo_documento": "TD01", "linee": [
                {"descrizione": "IRCA MIX DOLCE FORNO CF 25 KG", "codici_articolo": [{"tipo": "AswArtFor", "valore": "IRCA240"}],
                 "quantita": "2.00", "prezzo_unitario": "70", "prezzo_totale": "133.12", "unita_misura": "Confezioni"}], **campi}


def test_fatture_erp_mepa_popolano_preferiti_oltre_prima_pagina_e_acquisti_futuri(monkeypatch):
    async def scenario():
        erp, lotti = AsyncMongoMockClient().erp, AsyncMongoMockClient().lotti
        monkeypatch.setattr(Database, "db", erp)
        monkeypatch.setattr(cataloghi_prezzi, "db", lotti)
        await erp.invoices.insert_one(fattura())
        await lotti.dizionario_ingredienti.insert_many([
            {"id": str(i), "nome": f"Altro {i}", "fonte": "mepa"} for i in range(240)])
        await lotti.dizionario_ingredienti.insert_one({"id": "mix", "nome": "Dolce forno", "codice_articolo": "IRCA240", "fonte": "mepa"})
        primo = await cataloghi_prezzi.preferiti_acquisti("mepa")
        assert primo["totale"] == 1 and primo["prodotti"][0]["id"] == "mix"
        assert primo["prodotti"][0]["prezzo_fattura"] == 66.56
        assert await cataloghi_prezzi.preferiti_acquisti("mepa") == primo
        await erp.invoices.insert_one(fattura(id="f2", invoice_date="2026-10-01", linee=[
            {"descrizione": "Nuovo articolo", "codice_articolo": "NEW01", "quantita": 1, "prezzo_unitario": 12}]))
        nuovo = await cataloghi_prezzi.preferiti_acquisti("mepa")
        assert nuovo["totale"] == 2
        assert next(p for p in nuovo["prodotti"] if p["codice_articolo"] == "NEW01")["da_fattura_senza_catalogo"]
        assert await lotti.fatture.count_documents({}) == 0  # nessuna copia/stock generato
    run(scenario())


def test_esclude_crediti_archiviate_collisioni_fornitore_sbagliato(monkeypatch):
    async def scenario():
        erp, lotti = AsyncMongoMockClient().erp, AsyncMongoMockClient().lotti
        monkeypatch.setattr(Database, "db", erp)
        await erp.invoices.insert_many([fattura(), fattura(id="nc", tipo_documento="TD04"),
            fattura(id="arch", status="archived"), fattura(id="collisione", duplicate_review_required=True),
            fattura(id="altro", supplier_name="Super MEPA Service", supplier_vat="99999999999")])
        assert [f["id"] for f in await fatture_catalogo(lotti, "mepa")] == ["f1"]
        prezzi = await prezzi_fatture_per_fornitore(lotti, "mepa")
        assert prezzi["codart::IRCA240"]["prezzo"] == 66.56
    run(scenario())


def test_fornitore_dinamico_usa_piva_e_non_sottostringa(monkeypatch):
    async def scenario():
        erp, lotti = AsyncMongoMockClient().erp, AsyncMongoMockClient().lotti
        monkeypatch.setattr(Database, "db", erp)
        await lotti.fonti_catalogo_esterne.insert_one({"fornitore_key": "miofornitore", "nome": "Fornitore", "partita_iva": "12345678901"})
        await erp.invoices.insert_many([fattura(id="ok", supplier_name="Denominazione variata", supplier_vat="IT12345678901"),
            fattura(id="no", supplier_name="Fornitore", supplier_vat="99999999999")])
        assert [f["id"] for f in await fatture_catalogo(lotti, "miofornitore")] == ["ok"]
    run(scenario())


def test_catalogo_acquaviva_vandemoortele_legge_denom_in_fatture_2026(monkeypatch):
    async def scenario():
        erp, lotti = AsyncMongoMockClient().erp, AsyncMongoMockClient().lotti
        monkeypatch.setattr(Database, "db", erp)
        await lotti.fonti_catalogo_esterne.insert_one({"fornitore_key": "acquaviva", "nome": "Dolciaria Acquaviva S.p.A.", "partita_iva": ""})
        await erp.invoices.insert_many([
            fattura(id="aqv", supplier_name="Dolciaria Acquaviva S.p.A.", supplier_vat="01269431217"),
            fattura(id="vdm", supplier_name="VANDEMOORTELE EUROPE NV,           (SEDE SECONDARIA ITALIA)", supplier_vat="02644480994"),
            fattura(id="altro", supplier_name="Vandemoortele Europe Services", supplier_vat="99999999999"),
        ])
        assert {f["id"] for f in await fatture_catalogo(lotti, "acquaviva")} == {"aqv", "vdm"}
        assert {f["id"] for f in await fatture_catalogo(lotti, "vandemoortele")} == {"vdm"}
    run(scenario())


def test_ambigui_restano_originali_non_diventano_altro_prodotto():
    articoli = articoli_acquistati([fattura()])
    catalogo = [{"id": "a", "codice_articolo": "IRCA240", "nome": "Variante uno"},
                {"id": "b", "codice_articolo": "IRCA240", "nome": "Variante due"}]
    out = collega_preferiti(articoli, catalogo, "mepa")
    assert len(out) == 1 and out[0]["da_fattura_senza_catalogo"]
    assert out[0]["nome"] == "IRCA MIX DOLCE FORNO CF 25 KG"


def test_ultima_data_reale_omaggi_e_righe_servizio():
    vecchia = fattura(invoice_date="30/08/2026")
    recente = fattura(id="f2", invoice_date="02/09/2026")
    recente["linee"][0]["prezzo_totale"] = "120"
    recente["linee"].extend([{"descrizione": "Spese trasporto", "prezzo": 10},
        {"descrizione": "Omaggio cioccolato", "prezzo": 0, "quantita": 1},
        {"descrizione": "Reso", "prezzo": 10, "quantita": -1}])
    out = articoli_acquistati([recente, vecchia])
    assert len(out) == 2 and next(p for p in out if p["codice_articolo"])["prezzo"] == 60


def test_listino_reale_non_viene_azzerato_ne_sostituito_da_fattura():
    for prezzi in ({}, {"caffe": {"prezzo": 10}}):
        p = applica_prezzo_da_fatture([{"nome": "Caffe", "prezzo_listino": 12, "fonte_catalogo": "listino"}], prezzi)[0]
        assert p["prezzo_listino"] == 12


def test_righe_informative_xml_non_diventano_prodotti_ma_omaggi_si():
    righe = [
        {"descrizione": "Riga ausiliaria contenente informazioni tecniche e aggiuntive del documento",
         "quantita": "1", "prezzo_unitario": "0.00", "prezzo_totale": "0.00"},
        {"descrizione": "Dati documento", "quantita": "1", "prezzo_unitario": "0.00",
         "altri_dati_gestionali": [{"tipo_dato": "AswTRiga", "riferimento_testo": "Informazioni documento #ID#"}]},
        {"descrizione": "Cioccolato omaggio", "codice_articolo": "OM01", "quantita": "1",
         "prezzo_unitario": "0.00", "prezzo_totale": "0.00",
         "altri_dati_gestionali": [{"tipo_dato": "AswTRiga", "riferimento_testo": "Merce #ME#"}]},
    ]
    prodotti = collega_preferiti(articoli_acquistati([fattura(linee=righe)]), [], "mepa")
    assert len(prodotti) == 1
    assert prodotti[0]["codice_articolo"] == "OM01"
    assert prodotti[0]["prezzo_fattura"] == 0
    assert len(righe) == 3  # L'originale della fattura non viene modificato.
