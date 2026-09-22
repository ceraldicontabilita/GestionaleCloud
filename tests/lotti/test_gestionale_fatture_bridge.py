import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def bridge(monkeypatch):
    import app.lotti.routers.fatture as fatture
    import app.lotti.routers.gestionale_fatture as module
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(module, "db", database)
    monkeypatch.setattr(fatture, "db", database)
    monkeypatch.setenv("GESTIONALECLOUD_API_URL", "https://gestionale.example")
    monkeypatch.setenv("LOTTI_INTEGRATION_KEY", "test-secret")
    return module, database


def _item(source_hash="hash-1"):
    return {
        "source_id": "invoice-1",
        "source_hash": source_hash,
        "invoice_number": "42/A",
        "invoice_date": "2026-08-31",
        "supplier_name": "FORNITORE TEST SRL",
        "supplier_vat": "01234567890",
        "has_xml": True,
        "source": "gestionalecloud",
    }


def test_anteprima_non_scrive(bridge, monkeypatch):
    module, database = bridge

    async def elenco(_client, _anno):
        return [_item()], 1

    monkeypatch.setattr(module, "_elenco", elenco)
    result = run(module.esegui_sync_gestionale(anno=2026, anteprima=True))

    assert result["importabili"] == 1
    assert result["importate"] == 0
    assert run(database.gestionale_fatture_ricevute.count_documents({})) == 0
    assert run(database.fatture.count_documents({})) == 0


def test_secondo_giro_non_duplica(bridge, monkeypatch):
    module, database = bridge

    async def elenco(_client, _anno):
        return [_item()], 1

    async def dettaglio(_client, _path, **_params):
        return {**_item(), "xml_raw": "<FatturaElettronica/>"}

    async def importa(_files):
        await database.fatture.insert_one({
            "id": "lotti-1", "numero_fattura": "42/A", "piva": "01234567890",
            "prodotti": [{"descrizione": "FARINA"}],
        })
        return {"fatture_processate": 1, "fatture_duplicate_saltate": 0}

    import app.lotti.routers.fatture as fatture
    monkeypatch.setattr(module, "_elenco", elenco)
    monkeypatch.setattr(module, "_get_json", dettaglio)
    monkeypatch.setattr(fatture, "importa_fattura_xml", importa)

    first = run(module.esegui_sync_gestionale(anno=2026, anteprima=False))
    second = run(module.esegui_sync_gestionale(anno=2026, anteprima=False))

    assert first["importate"] == 1
    assert second["gia_ricevute"] == 1
    assert run(database.fatture.count_documents({})) == 1
    assert run(database.gestionale_fatture_ricevute.count_documents({})) == 1


def test_hash_cambiato_diventa_conflitto_e_non_sovrascrive(bridge, monkeypatch):
    module, database = bridge
    run(database.gestionale_fatture_ricevute.insert_one({
        "source_id": "invoice-1", "source_hash": "hash-vecchio", "stato": "importata"
    }))

    async def elenco(_client, _anno):
        return [_item("hash-nuovo")], 1

    monkeypatch.setattr(module, "_elenco", elenco)
    result = run(module.esegui_sync_gestionale(anno=2026, anteprima=False))

    assert result["importate"] == 0
    assert len(result["conflitti"]) == 1
    receipt = run(database.gestionale_fatture_ricevute.find_one({"source_id": "invoice-1"}))
    assert receipt["source_hash"] == "hash-vecchio"
    assert receipt["stato"] == "conflitto_hash"
    assert receipt["nuovo_source_hash"] == "hash-nuovo"


def test_fattura_manualemente_presente_viene_solo_collegata(bridge, monkeypatch):
    module, database = bridge
    run(database.fatture.insert_one({
        "id": "manuale-1", "numero_fattura": "42/A", "piva": "01234567890",
        "prodotti": [{"descrizione": "FARINA"}],
    }))

    async def elenco(_client, _anno):
        return [_item()], 1

    monkeypatch.setattr(module, "_elenco", elenco)
    result = run(module.esegui_sync_gestionale(anno=2026, anteprima=False))

    assert result["collegate_esistenti"] == 1
    assert result["importate"] == 0
    invoice = run(database.fatture.find_one({"id": "manuale-1"}))
    assert invoice["gestionale_source_id"] == "invoice-1"
    assert run(database.fatture.count_documents({})) == 1


def test_righe_strutturate_funzionano_anche_senza_xml_raw(bridge, monkeypatch):
    module, database = bridge
    item = {
        **_item(), "has_xml": False,
        "lines": [{"descrizione": "FARINA 00", "quantita": "2", "unita_misura": "KG",
                   "prezzo_unitario": "3.50", "prezzo_totale": "7.00"}],
    }

    async def elenco(_client, _anno):
        return [item], 1

    async def dettaglio(_client, _path, **_params):
        return item

    captured = {}

    async def importa(files):
        captured["xml"] = (await files[0].read()).decode("utf-8")
        await database.fatture.insert_one({
            "id": "lotti-2", "numero_fattura": "42/A", "piva": "01234567890",
            "prodotti": [{"descrizione": "FARINA 00"}],
        })
        return {"fatture_processate": 1, "fatture_duplicate_saltate": 0}

    import app.lotti.routers.fatture as fatture
    monkeypatch.setattr(module, "_elenco", elenco)
    monkeypatch.setattr(module, "_get_json", dettaglio)
    monkeypatch.setattr(fatture, "importa_fattura_xml", importa)

    result = run(module.esegui_sync_gestionale(anno=2026, anteprima=False))

    assert result["importate"] == 1
    assert "FARINA 00" in captured["xml"]
    assert "<Quantita>2</Quantita>" in captured["xml"]


def test_monolite_legge_fatture_locali_senza_url_o_segreto(bridge, monkeypatch):
    module, database = bridge
    monkeypatch.delenv("GESTIONALECLOUD_API_URL", raising=False)
    monkeypatch.delenv("LOTTI_INTEGRATION_KEY", raising=False)

    import app.routers.lotti_integration as source

    async def documents():
        return [{
            "id": "invoice-local-1",
            "numero_fattura": "77/2026",
            "data_fattura": "2026-09-14",
            "fornitore_ragione_sociale": "FORNITORE LOCALE SRL",
            "fornitore_partita_iva": "01234567890",
            "righe": [{"descrizione": "FARINA 00", "quantita": 2, "unita_misura": "KG"}],
        }]

    monkeypatch.setattr(source, "_documents", documents)
    result = run(module.esegui_sync_gestionale(anno=2026, anteprima=True))
    stato = run(module.stato_gestionale_fatture())

    assert result["ok"] is True
    assert result["totale_fonte"] == 1
    assert result["importabili"] == 1
    assert run(database.fatture.count_documents({})) == 0
    assert stato["configurato"] is True
    assert stato["modalita"] == "interna"
    assert stato["database_separati"] is False


def test_lista_fatture_compatibile_con_store_supabase(bridge):
    _, database = bridge
    import app.lotti.routers.fatture as fatture

    run(database.fatture.insert_one({
        "id": "f-2026", "numero_fattura": "88/2026", "data_fattura": "2026-09-10",
        "fornitore": "FORNITORE TEST", "prodotti": [{"descrizione": "UOVA"}],
        "xml_raw": "<FatturaElettronica/>",
    }))
    result = run(fatture.get_fatture(escludi_fornitori=False, anno=2026, limit=10))

    assert len(result) == 1
    assert result[0]["num_prodotti"] == 1
    assert result[0]["has_xml"] is True
    assert "prodotti" not in result[0]
    assert "xml_raw" not in result[0]


def test_invoice_query_riconosce_la_copia_con_piva_diversa(bridge):
    """Fiorentino 1/163 era in Lotti con P.IVA troncata «03473»: la chiave
    solo-P.IVA non combaciava e il ponte creava un secondo documento. Ora
    basta numero + fornitore + data."""
    module, database = bridge
    run(database.fatture.insert_one({
        "id": "vecchia", "numero_fattura": "1/163", "piva": "03473",
        "fornitore": "F.lli Fiorentino Srl", "data_fattura": "05/01/2026",
        "prodotti": [{"descrizione": "Farina"}],
    }))
    item = {
        "invoice_number": "1/163", "invoice_date": "2026-01-05",
        "supplier_name": "F.lli Fiorentino Srl", "supplier_vat": "01637290634",
    }
    trovata = run(database.fatture.find_one(module._invoice_query(item), {"_id": 0, "id": 1}))
    assert trovata == {"id": "vecchia"}
    # la stessa chiave trova anche la copia con la P.IVA giusta
    run(database.fatture.insert_one({
        "id": "nuova", "numero_fattura": "2/200", "piva": "01637290634",
        "fornitore": "F.LLI FIORENTINO", "data_fattura": "06/01/2026",
    }))
    item2 = {"invoice_number": "2/200", "invoice_date": "2026-01-06",
             "supplier_name": "Fiorentino diverso", "supplier_vat": "01637290634"}
    assert run(database.fatture.find_one(module._invoice_query(item2), {"_id": 0, "id": 1})) == {"id": "nuova"}
    # senza P.IVA resta la sola chiave fornitore+numero+data
    query = module._invoice_query({"invoice_number": "3/1", "invoice_date": "2026-02-01", "supplier_name": "X"})
    assert query == {"numero_fattura": "3/1", "fornitore": "X", "data_fattura": "01/02/2026"}
    # un numero diverso non combacia con nessun ramo
    assert run(database.fatture.find_one(module._invoice_query({**item, "invoice_number": "9/9"}))) is None
