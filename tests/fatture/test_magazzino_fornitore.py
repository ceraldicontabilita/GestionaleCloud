"""Nel magazzino / fuori dal magazzino: una decisione sola, mai una perdita di dati."""
import asyncio

import pytest

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services import magazzino_fornitore as mf


def _run(coro):
    return asyncio.run(coro)


def test_stato_erp_vince_poi_lotti_poi_non_deciso():
    d = mf.DecisioniMagazzino()
    d.carica_erp([
        {"partita_iva": "IT06356400637", "ragione_sociale": "BIG FOOD SRL", "esclude_magazzino": False},
        {"partita_iva": "111", "ragione_sociale": "ALFA", "esclude_magazzino": True},
        {"partita_iva": "222", "ragione_sociale": "SENZA SCELTA"},  # chiave assente: non deciso
    ])
    d.carica_lotti([
        {"nome": "SENZA SCELTA", "escluso": True, "piva": ""},
        {"nome": "ALFA", "escluso": False},  # Lotti dice incluso, ma ERP ha deciso
    ])
    assert d.stato("06356400637", "BIG FOOD SRL") == (False, "erp")
    assert d.stato("111", "ALFA") == (True, "erp")           # ERP batte Lotti
    assert d.stato("222", "SENZA SCELTA") == (True, "lotti")  # eredita dove ERP tace
    assert d.stato("333", "MAI VISTO") == (None, "non_deciso")
    assert d.escluso("333", "MAI VISTO") is False  # non deciso = incluso, senza inventare


def test_omonimo_con_altra_piva_non_eredita_la_decisione_di_lotti():
    d = mf.DecisioniMagazzino()
    d.carica_lotti([{"nome": "BIG FOOD SRL", "escluso": True, "piva": "12281740154"}])
    assert d.stato("06356400637", "BIG FOOD SRL") == (None, "non_deciso")
    assert d.stato("12281740154", "BIG FOOD SRL") == (True, "lotti")


def test_inventory_enabled_legacy_non_fa_piu_risultare_escluso_nessuno():
    from app.routers.suppliers_module.base import _legacy_supplier_view

    assert _legacy_supplier_view({"ragione_sociale": "X", "vat": "12345678901"})["esclude_magazzino"] is False
    assert _legacy_supplier_view({"ragione_sociale": "X", "vat": "12345678901", "inventory_enabled": False})["esclude_magazzino"] is False
    assert _legacy_supplier_view({"ragione_sociale": "X", "vat": "12345678901", "esclude_magazzino": True})["esclude_magazzino"] is True


def test_motivo_obbligatorio_e_altro_vuole_il_testo():
    assert mf.valida_motivo(True, "servizi_utenze")[0] == "servizi_utenze"
    with pytest.raises(ValueError):
        mf.valida_motivo(True, "")
    with pytest.raises(ValueError):
        mf.valida_motivo(True, "merce_alimentare")  # motivo di inclusione su un'esclusione
    with pytest.raises(ValueError):
        mf.valida_motivo(True, "altro", "  ")
    assert mf.valida_motivo(False, "altro", "prova")[1] == "prova"


@pytest.fixture
def ambiente(monkeypatch):
    from app.database import Database
    from app.lotti.db import database as db_lotti

    db = ClientArchivioMemoria()["magazzino_fornitore"]
    monkeypatch.setattr(Database, "get_db", classmethod(lambda cls: db))

    async def pulisci_lotti():
        # il database di Lotti in memoria e' di modulo: ogni prova parte vuota
        for nome in ("fornitori", "fornitori_decisioni", "fatture", "lotti_fornitori"):
            await getattr(db_lotti, nome).delete_many({})

    asyncio.run(pulisci_lotti())
    accodate = []
    monkeypatch.setattr(
        "app.services.handlers.fattura_handlers.accoda_alimentazione_lotti",
        lambda ids: accodate.append(list(ids)) or len(list(ids)))
    da_prendere = []

    async def finte(piva, nome):
        return list(da_prendere)

    monkeypatch.setattr("app.lotti.routers.gestionale_fatture.fatture_da_prendere_fornitore", finte)
    return db, db_lotti, accodate, da_prendere


def test_escludi_scrive_storico_proietta_su_lotti_e_non_cancella(ambiente):
    db, db_lotti, accodate, _ = ambiente

    async def scenario():
        await db["fornitori"].insert_one({
            "id": 7, "partita_iva": "06356400637", "ragione_sociale": "BIG FOOD SRL"})
        await db["warehouse_inventory"].insert_one({"id": "w1", "fornitore_piva": "06356400637"})
        await db["invoices"].insert_one({
            "id": "f1", "supplier_vat": "06356400637", "invoice_date": "2026-01-09"})
        f = await db["fornitori"].find_one({"id": 7})
        esito = await mf.applica(db, f, True, "servizi_utenze", "", "titolare")
        dopo = await db["fornitori"].find_one({"id": 7}, {"_id": 0})
        lotti = await db_lotti.fornitori.find_one({"nome": "BIG FOOD SRL"})
        decisione = await db_lotti.fornitori_decisioni.find_one({"chiave": "big food srl"})
        return esito, dopo, lotti, decisione, await db["warehouse_inventory"].count_documents({}), \
            await db["invoices"].count_documents({})

    esito, dopo, lotti, decisione, inventario, fatture = _run(scenario())
    assert dopo["esclude_magazzino"] is True
    assert dopo["magazzino_motivo"] == "servizi_utenze"
    assert dopo["magazzino_deciso_da"] == "titolare" and dopo["magazzino_deciso_il"]
    assert len(dopo["storico_magazzino"]) == 1 and dopo["storico_magazzino"][0]["escluso"] is True
    assert esito["proiezione_lotti"]["scritta"] is True
    assert lotti["escluso"] is True and decisione["escluso"] is True
    assert inventario == 1 and fatture == 1  # niente si cancella
    assert accodate == []  # escludere non importa nulla


def test_includi_accoda_le_fatture_da_prendere_e_toglie_il_flag_in_lotti(ambiente):
    db, db_lotti, accodate, da_prendere = ambiente
    da_prendere.extend(["s1", "s2"])

    async def scenario():
        await db["fornitori"].insert_one({
            "id": 8, "partita_iva": "111", "ragione_sociale": "ALFA", "esclude_magazzino": True})
        f = await db["fornitori"].find_one({"id": 8})
        esito = await mf.applica(db, f, False, "escluso_per_errore", "", "titolare")
        return esito, await db["fornitori"].find_one({"id": 8}, {"_id": 0}), \
            await db_lotti.fornitori.find_one({"nome": "ALFA"})

    esito, dopo, lotti = _run(scenario())
    assert dopo["esclude_magazzino"] is False
    assert dopo["storico_magazzino"][-1]["effetto"] == {"fatture_da_prendere": 2}
    assert accodate == [["s1", "s2"]] and esito["fatture_accodate_a_lotti"] == 2
    assert lotti["escluso"] is False


def test_solo_magazzino_di_lotti_sopravvive_all_inclusione(ambiente):
    db, db_lotti, _, _ = ambiente

    async def scenario():
        await db_lotti.fornitori.insert_one({"nome": "BETA", "escluso": True, "tipo_fornitura": "solo_magazzino"})
        from app.lotti.routers.fornitori import imposta_esclusione
        await imposta_esclusione("BETA", False)
        return await db_lotti.fornitori.find_one({"nome": "BETA"})

    assert _run(scenario())["tipo_fornitura"] == "solo_magazzino"


def test_anteprima_conta_senza_scrivere(ambiente):
    db, db_lotti, _, da_prendere = ambiente
    da_prendere.append("s9")

    async def scenario():
        await db["fornitori"].insert_one({
            "id": 9, "partita_iva": "06356400637", "ragione_sociale": "BIG FOOD SRL"})
        await db["invoices"].insert_many([
            {"id": "a", "supplier_vat": "06356400637", "invoice_date": "2026-01-09"},
            {"id": "b", "supplier_vat": "06356400637", "invoice_date": "2026-02-09", "status": "archived"},
        ])
        await db_lotti.fatture.insert_one({"id": "l1", "piva": "06356400637", "fornitore": "BIG FOOD SRL"})
        await db_lotti.lotti_fornitori.insert_many([
            {"id": "x1", "fornitore": "BIG FOOD SRL", "esaurito": False, "quantita_disponibile": 3},
            {"id": "x2", "fornitore": "BIG FOOD SRL", "esaurito": True, "quantita_disponibile": 0},
        ])
        f = await db["fornitori"].find_one({"id": 9})
        esc = await mf.anteprima(db, f, True)
        inc = await mf.anteprima(db, f, False)
        return esc, inc, await db["fornitori"].find_one({"id": 9}, {"_id": 0})

    esc, inc, fornitore = _run(scenario())
    assert esc["fatture_contabili"] == 1  # l'archiviata non conta
    assert esc["fatture_in_lotti"] == 1 and esc["lotti_creati"] == 2 and esc["lotti_con_giacenza"] == 1
    assert any("restano" in r for r in esc["effetto"])
    assert inc["fatture_da_prendere"] == 1
    assert "esclude_magazzino" not in fornitore  # l'anteprima non scrive


def test_allinea_da_lotti_dry_run_e_applicazione(ambiente):
    db, db_lotti, _, _ = ambiente

    async def scenario():
        await db["fornitori"].insert_many([
            {"id": 1, "partita_iva": "1", "ragione_sociale": "UNO"},                        # eredita
            {"id": 2, "partita_iva": "2", "ragione_sociale": "DUE", "esclude_magazzino": False},  # gia' deciso
            {"id": 3, "partita_iva": "3", "ragione_sociale": "TRE"},                        # nessuno ha deciso
        ])
        await db_lotti.fornitori.insert_many([
            {"nome": "UNO", "escluso": True}, {"nome": "DUE", "escluso": True}])
        anteprima = await mf.allinea_da_lotti(db, dry_run=True)
        prima = await db["fornitori"].find_one({"id": 1}, {"_id": 0})
        applicato = await mf.allinea_da_lotti(db, dry_run=False)
        dopo = await db["fornitori"].find_one({"id": 1}, {"_id": 0})
        secondo = await mf.allinea_da_lotti(db, dry_run=False)
        due = await db["fornitori"].find_one({"id": 2}, {"_id": 0})
        return anteprima, prima, applicato, dopo, secondo, due

    anteprima, prima, applicato, dopo, secondo, due = _run(scenario())
    assert anteprima["dry_run"] is True and anteprima["da_allineare"] == 1 and anteprima["allineati"] == 0
    assert "esclude_magazzino" not in prima
    assert applicato["allineati"] == 1 and dopo["esclude_magazzino"] is True
    assert dopo["storico_magazzino"][0]["origine"] == "allineamento"
    assert secondo["da_allineare"] == 0 and secondo["allineati"] == 0  # idempotente
    assert due["esclude_magazzino"] is False  # la scelta ERP non si tocca


def test_scelta_fatta_in_lotti_arriva_nell_anagrafica_erp(ambiente):
    db, db_lotti, _, _ = ambiente

    async def scenario():
        await db["fornitori"].insert_one({"id": 4, "partita_iva": "444", "ragione_sociale": "QUATTRO"})
        esito = await mf.registra_decisione_da_lotti("QUATTRO", "", True)
        ripetuto = await mf.registra_decisione_da_lotti("QUATTRO", "", True)
        return esito, ripetuto, await db["fornitori"].find_one({"id": 4}, {"_id": 0})

    esito, ripetuto, f = _run(scenario())
    assert f["esclude_magazzino"] is True and f["magazzino_motivo"] == mf.MOTIVO_DA_LOTTI
    assert ripetuto is None and len(f["storico_magazzino"]) == 1  # nessuna voce doppia


def test_il_ponte_salta_il_fornitore_escluso_in_erp_anche_se_lotti_non_lo_sa(ambiente, monkeypatch):
    db, db_lotti, _, _ = ambiente
    from app.lotti.routers import gestionale_fatture as gf

    async def scenario():
        await db["fornitori"].insert_one({
            "id": 5, "partita_iva": "555", "ragione_sociale": "CINQUE", "esclude_magazzino": True})

        async def dettaglio(source_id):
            return {"source_id": source_id, "supplier_vat": "IT555", "supplier_name": "CINQUE",
                    "xml_raw": "<x/>"}

        monkeypatch.setattr(gf, "_dettaglio_locale", dettaglio)
        return await gf.alimenta_lotti_da_fattura("s1")

    esito = _run(scenario())
    assert esito["stato"] == "saltata" and "fuori dal magazzino" in esito["motivo"]


def test_put_scheda_cambia_il_flag_solo_col_servizio_e_conserva_la_data_del_metodo(ambiente, monkeypatch):
    db, db_lotti, _, _ = ambiente
    import asyncio as aio
    from app.routers.suppliers_module import base
    from app.utils import iva_calculator

    async def clear_pattern(pattern):
        return None

    async def salva(*a, **k):
        return True

    monkeypatch.setattr(base.cache, "clear_pattern", clear_pattern)
    monkeypatch.setattr(iva_calculator, "save_supplier_payment_method", salva)
    monkeypatch.setattr(aio, "create_task", lambda c: c.close())

    async def scenario():
        await db["fornitori"].insert_one({
            "id": "s1", "partita_iva": "06356400637", "ragione_sociale": "BIG FOOD SRL",
            "metodo_pagamento": "cassa", "metodo_pagamento_dal": "2025-01-01"})
        # salvataggio della scheda con lo stesso metodo: la data «dal» NON torna a oggi
        r1 = await base.update_supplier("s1", {"metodo_pagamento": "cassa", "esclude_magazzino": True})
        f1 = await db["fornitori"].find_one({"id": "s1"}, {"_id": 0})
        # data scritta dal titolare
        await base.update_supplier("s1", {"metodo_pagamento": "cassa", "metodo_pagamento_dal": "2025-03-01"})
        f2 = await db["fornitori"].find_one({"id": "s1"}, {"_id": 0})
        with pytest.raises(Exception) as err:
            await base.update_supplier("s1", {"metodo_pagamento_dal": "01/01/2025"})
        return r1, f1, f2, err.value

    r1, f1, f2, err = _run(scenario())
    assert f1["metodo_pagamento_dal"] == "2025-01-01"
    assert f1["esclude_magazzino"] is True and f1["magazzino_motivo"] == mf.MOTIVO_MODIFICA_SCHEDA
    assert r1["supplier"]["esclude_magazzino"] is True
    assert f2["metodo_pagamento_dal"] == "2025-03-01"
    assert getattr(err, "status_code", None) == 400


def test_qualifica_lotti_passa_dallo_scrittore_unico_e_non_riporta_dentro_gli_esclusi(ambiente):
    db, db_lotti, _, _ = ambiente
    from app.lotti.routers import fornitori_qualifica as fq

    async def scenario():
        await db["fornitori"].insert_many([
            {"id": 1, "partita_iva": "111", "ragione_sociale": "UNO"},
            {"id": 2, "partita_iva": "222", "ragione_sociale": "DUE", "esclude_magazzino": True},
        ])
        await db_lotti.fornitori_qualifica.insert_many([
            {"piva": "111", "nome_fornitore": "UNO", "stato": "in_attesa_verifica"},
            {"piva": "222", "nome_fornitore": "DUE", "stato": "in_attesa_verifica"},
        ])
        # scelta esplicita: esclude UNO -> proiezione su Lotti e decisione nell'anagrafica ERP
        await fq.approva_qualifica_fornitore("111", includi=False, _admin=None)
        uno = await db["fornitori"].find_one({"id": 1}, {"_id": 0})
        lotti_uno = await db_lotti.fornitori.find_one({"nome": "UNO"})
        # qualifica automatica: DUE e' fuori per scelta del titolare, non rientra
        esito = await fq.auto_qualifica_tutti_attivi(_admin=None)
        due = await db_lotti.fornitori_qualifica.find_one({"piva": "222"})
        return uno, lotti_uno, esito, due

    uno, lotti_uno, esito, due = _run(scenario())
    assert uno["esclude_magazzino"] is True and uno["magazzino_motivo"] == mf.MOTIVO_DA_LOTTI
    assert lotti_uno["escluso"] is True
    assert due["stato"] == "in_attesa_verifica" and esito["aggiornati"] == 0
