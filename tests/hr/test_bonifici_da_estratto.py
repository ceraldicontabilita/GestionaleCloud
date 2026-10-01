"""Il bonifico PDF si abbina da solo al movimento d'estratto (riferimento banca + importo) e ne eredita l'esito."""
import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services.bonifici_da_estratto import abbina_bonifici_via_estratto

RIF = "MBVT40188610"


def run(coro):
    return asyncio.run(coro)


def _db(movimento=None, fattura=None, bonifico=None):
    db = AsyncMongoMockClient()["bonifici"]
    run(db["bonifici_transfers"].insert_one(bonifico or {
        "id": "b1", "data": "2026-08-14T00:00:00+00:00", "importo": 2752.98, "rif_interno": RIF,
        "beneficiario": {"nome": "Edenred Italia S.r.l."}, "hr_deposito": {"esito": "non_stipendio"}}))
    run(db["estratto_conto_movimenti"].insert_one(movimento or {
        "id": "m1", "data": "2026-08-14", "tipo": "uscita", "importo": -2752.98, "categoria": "Fatture",
        "descrizione": f"VOSTRA DISPOSIZIONE - VS.DISP. RIF. {RIF}/00111152 FAVORE Edenred Italia S.r.l.",
        "candidate_fattura_id": "850878"}))
    if fattura is not False:
        run(db["invoices"].insert_one(fattura or {
            "id": "850878", "invoice_number": "850878", "total_amount": 2752.98, "status": "imported"}))
    return db


def test_il_riferimento_banca_collega_il_bonifico_alla_fattura_del_movimento():
    db = _db()
    esito = run(abbina_bonifici_via_estratto(db))
    assert esito["fatture_collegate"] == 1
    t = run(db["bonifici_transfers"].find_one({"id": "b1"}))
    assert t["fattura_associata"] is True and t["fattura_associata_id"] == "850878"
    assert t["movimento_estratto_conto_id"] == "m1"
    # le prove dichiarate sono quelle vere: niente «numero in causale»
    assert "numero_fattura_in_causale" not in t["fattura_associazione_evidenze"]
    assert "rif_banca_in_estratto" in t["fattura_associazione_evidenze"]
    # secondo giro: niente di nuovo
    assert run(abbina_bonifici_via_estratto(db))["fatture_collegate"] == 0


def test_un_importo_diverso_non_si_collega_mai_nemmeno_col_riferimento_uguale():
    db = _db(fattura={"id": "850878", "total_amount": 2700.00})
    esito = run(abbina_bonifici_via_estratto(db))
    assert esito["fatture_collegate"] == 0 and esito["fattura_non_collegabile"] == 1
    assert "fattura_associata" not in run(db["bonifici_transfers"].find_one({"id": "b1"}))


def test_una_fattura_gia_legata_a_un_altro_bonifico_non_si_riassegna():
    db = _db(fattura={"id": "850878", "total_amount": 2752.98, "bonifico_ids": ["altro"]})
    assert run(abbina_bonifici_via_estratto(db))["fatture_collegate"] == 0


def test_una_categoria_senza_documento_toglie_il_bonifico_dalla_lista():
    db = _db(movimento={
        "id": "m2", "data": "2026-08-14", "tipo": "uscita", "importo": -2752.98, "categoria": "Assicurazioni",
        "descrizione": f"VOSTRA DISPOSIZIONE - VS.DISP. RIF. {RIF}/001 FAVORE Compagnia"}, fattura=False)
    esito = run(abbina_bonifici_via_estratto(db))
    assert esito["destinazioni_certe"] == 1
    t = run(db["bonifici_transfers"].find_one({"id": "b1"}))
    assert t["destinazione_automatica"]["categoria"] == "Assicurazioni"


def test_senza_movimento_con_lo_stesso_riferimento_non_si_indovina():
    db = _db(movimento={"id": "m3", "data": "2026-08-14", "tipo": "uscita", "importo": -2752.98,
                        "categoria": "Fatture", "descrizione": "VOSTRA DISPOSIZIONE - RIF. MBVT99999999/1"})
    esito = run(abbina_bonifici_via_estratto(db))
    assert esito["movimento_trovato"] == 0 and esito["fatture_collegate"] == 0


def test_gli_stipendi_restano_al_motore_hr():
    db = _db(movimento={"id": "m4", "data": "2026-08-14", "tipo": "uscita", "importo": -2752.98,
                        "categoria": "Stipendi", "descrizione": f"VS.DISP. RIF. {RIF}/1 FAVORE Rossi Mario"})
    assert run(abbina_bonifici_via_estratto(db))["fatture_collegate"] == 0


def test_senza_riferimento_serve_il_nome_completo_con_importo_e_data_vicina():
    db = _db(
        bonifico={"id": "b9", "data": "2026-08-14T00:00:00+00:00", "importo": 2752.98, "rif_interno": None,
                  "cro_trn": "503400", "beneficiario": {"nome": "Edenred Italia S.r.l."}},
        movimento={"id": "m9", "data": "2026-08-15", "tipo": "uscita", "importo": -2752.98, "categoria": "Fatture",
                   "descrizione": "VOSTRA DISPOSIZIONE FAVORE Edenred Italia S.r.l. CODICE CLIENTE 710960",
                   "candidate_fattura_id": "850878"})
    esito = run(abbina_bonifici_via_estratto(db))
    assert esito["fatture_collegate"] == 1
    t = run(db["bonifici_transfers"].find_one({"id": "b9"}))
    assert "nome_beneficiario_in_estratto" in t["fattura_associazione_evidenze"]


def test_senza_riferimento_un_nome_diverso_non_basta():
    db = _db(
        bonifico={"id": "b9", "data": "2026-08-14T00:00:00+00:00", "importo": 2752.98, "rif_interno": None,
                  "cro_trn": "503400", "beneficiario": {"nome": "Altro Fornitore S.r.l."}},
        movimento={"id": "m9", "data": "2026-08-15", "tipo": "uscita", "importo": -2752.98, "categoria": "Fatture",
                   "descrizione": "VOSTRA DISPOSIZIONE FAVORE Edenred Italia S.r.l.", "candidate_fattura_id": "850878"})
    assert run(abbina_bonifici_via_estratto(db))["fatture_collegate"] == 0


def test_un_movimento_che_punta_la_copia_archiviata_si_collega_alla_gemella_attiva():
    db = _db(fattura={"id": "850878-arch", "invoice_number": "850878", "total_amount": 2752.98, "status": "archived",
                      "supplier_vat": "09429840151"})
    run(db["invoices"].insert_one({"id": "attiva", "invoice_number": "850878", "total_amount": 2752.98,
                                   "status": "imported", "supplier_vat": "09429840151"}))
    run(db["estratto_conto_movimenti"].update_one({"id": "m1"}, {"$set": {"candidate_fattura_id": "850878-arch"}}))
    assert run(abbina_bonifici_via_estratto(db))["fatture_collegate"] == 1
    assert run(db["bonifici_transfers"].find_one({"id": "b1"}))["fattura_associata_id"] == "attiva"


def test_la_gemella_con_altra_partita_iva_non_basta():
    db = _db(fattura={"id": "850878-arch", "invoice_number": "850878", "total_amount": 2752.98, "status": "archived",
                      "supplier_vat": "09429840151"})
    run(db["invoices"].insert_one({"id": "altra", "invoice_number": "850878", "total_amount": 2752.98,
                                   "status": "imported", "supplier_vat": "11111111111"}))
    run(db["estratto_conto_movimenti"].update_one({"id": "m1"}, {"$set": {"candidate_fattura_id": "850878-arch"}}))
    assert run(abbina_bonifici_via_estratto(db))["fatture_collegate"] == 0


def _bonifico(id_, rif, importo, nome="A 2000 Costruzioni S.r.l"):
    return {"id": id_, "data": "2026-02-12T00:00:00+00:00", "importo": importo, "rif_interno": rif,
            "beneficiario": {"nome": nome}, "hr_deposito": {"esito": "non_stipendio"}}


def _movimento(id_, rif, importo, fattura_id=None, data="2026-02-12"):
    m = {"id": id_, "data": data, "tipo": "uscita", "importo": -importo, "categoria": "Fatture",
         "descrizione": f"VS.DISP. RIF. {rif}/00746988 FAVORE A 2000 COSTRUZIONI S.R.L"}
    if fattura_id:
        m["fattura_ids"] = [fattura_id]
    return m


def _db_vuoto():
    return AsyncMongoMockClient()["bonifici"]


def test_la_stessa_operazione_letta_da_due_fonti_si_collega_con_la_copia_che_porta_la_fattura():
    db = _db_vuoto()
    run(db["bonifici_transfers"].insert_one(_bonifico("b1", "MBVT17968737", 372.42, "ceramiche Mara srl")))
    run(db["estratto_conto_movimenti"].insert_many([
        _movimento("legacy", "MBVT17968737", 372.42, fattura_id="F1"),
        {**_movimento("ufficiale", "MBVT17968737", 372.42), "importo": 372.42},
    ]))
    run(db["invoices"].insert_one({"id": "F1", "invoice_number": "2/623", "total_amount": 372.42, "status": "imported"}))
    assert run(abbina_bonifici_via_estratto(db))["fatture_collegate"] == 1
    assert run(db["bonifici_transfers"].find_one({"id": "b1"}))["fattura_associata_id"] == "F1"


def test_due_copie_che_indicano_fatture_diverse_restano_ambigue():
    db = _db_vuoto()
    run(db["bonifici_transfers"].insert_one(_bonifico("b1", "MBVT17968737", 100.0)))
    run(db["estratto_conto_movimenti"].insert_many([
        _movimento("m1", "MBVT17968737", 100.0, fattura_id="F1"),
        _movimento("m2", "MBVT17968737", 100.0, fattura_id="F2")]))
    run(db["invoices"].insert_many([
        {"id": "F1", "invoice_number": "1", "total_amount": 100.0, "status": "imported"},
        {"id": "F2", "invoice_number": "2", "total_amount": 100.0, "status": "imported"}]))
    assert run(abbina_bonifici_via_estratto(db))["fatture_collegate"] == 0


def _scenario_acconti(importi, totale):
    db = _db_vuoto()
    run(db["invoices"].insert_one({"id": "F1", "invoice_number": "FEP 7_26", "total_amount": totale, "status": "imported"}))
    for i, importo in enumerate(importi):
        rif = f"MBVT1000000{i}"
        run(db["bonifici_transfers"].insert_one(_bonifico(f"b{i}", rif, importo)))
        run(db["estratto_conto_movimenti"].insert_one(_movimento(f"m{i}", rif, importo, fattura_id="F1")))
    return db


def test_gli_acconti_che_sommano_il_totale_si_collegano_tutti_alla_fattura():
    db = _scenario_acconti([15000.0, 9400.0], 24400.0)
    esito = run(abbina_bonifici_via_estratto(db))
    assert esito["acconti_collegati"] == 2 and esito["fatture_collegate"] == 2
    for i in (0, 1):
        t = run(db["bonifici_transfers"].find_one({"id": f"b{i}"}))
        assert t["fattura_associata_id"] == "F1" and "acconti_sommano_il_totale_al_centesimo" in t["fattura_associazione_evidenze"]
    assert sorted(run(db["invoices"].find_one({"id": "F1"}))["bonifico_ids"]) == ["b0", "b1"]
    assert run(abbina_bonifici_via_estratto(db))["fatture_collegate"] == 0          # secondo giro: niente di nuovo


def test_acconti_che_non_sommano_il_totale_non_si_collegano():
    db = _scenario_acconti([15000.0, 9000.0], 24400.0)
    esito = run(abbina_bonifici_via_estratto(db))
    assert esito["fatture_collegate"] == 0 and esito["fattura_non_collegabile"] == 2
    assert "fattura_associata" not in run(db["bonifici_transfers"].find_one({"id": "b0"}))


def test_un_acconto_si_somma_a_quelli_gia_legati_alla_fattura():
    db = _scenario_acconti([3750.0, 5000.0], 8750.0)
    run(db["bonifici_transfers"].update_one({"id": "b0"}, {"$set": {
        "fattura_associata": True, "fattura_id": "F1"}}))
    run(db["invoices"].update_one({"id": "F1"}, {"$set": {"bonifico_ids": ["b0"]}}))
    esito = run(abbina_bonifici_via_estratto(db))
    assert esito["acconti_collegati"] == 1
    assert run(db["bonifici_transfers"].find_one({"id": "b1"}))["fattura_associata_id"] == "F1"


def test_il_riferimento_dei_bonifici_urgenti_mb0b_si_riconosce():
    db = _db_vuoto()
    run(db["bonifici_transfers"].insert_one(_bonifico("b1", "MB0B54696749", 5000.0, "CIERVO FABIANA")))
    run(db["estratto_conto_movimenti"].insert_one({
        "id": "m1", "data": "2026-05-06", "tipo": "uscita", "importo": -5000.0, "categoria": "Fatture",
        "descrizione": "VS.DISP. RIF. MB0B54696749/00370093 FAVORE CIERVO FABIANA", "fattura_ids": ["F1"]}))
    run(db["invoices"].insert_one({"id": "F1", "invoice_number": "FPR 9/26", "total_amount": 5000.0, "status": "imported"}))
    assert run(abbina_bonifici_via_estratto(db))["fatture_collegate"] == 1


def test_una_fattura_con_id_numerico_riceve_i_suoi_bonifici():
    db = _db_vuoto()
    run(db["invoices"].insert_one({"id": 1785340207136, "invoice_number": "FPR 9/26", "total_amount": 8750.0, "status": "imported"}))
    for i, importo in enumerate([3750.0, 5000.0]):
        rif = f"MBVT2000000{i}"
        run(db["bonifici_transfers"].insert_one(_bonifico(f"b{i}", rif, importo, "CIERVO FABIANA")))
        run(db["estratto_conto_movimenti"].insert_one(_movimento(f"m{i}", rif, importo, fattura_id="1785340207136")))
    assert run(abbina_bonifici_via_estratto(db))["acconti_collegati"] == 2
    assert sorted(run(db["invoices"].find_one({"id": 1785340207136}))["bonifico_ids"]) == ["b0", "b1"]


def test_il_riallineamento_rimette_il_bonifico_sulla_fattura_collegata_dal_solo_lato_del_bonifico():
    db = _db_vuoto()
    run(db["invoices"].insert_one({"id": 1785340207136, "invoice_number": "FPR 9/26", "total_amount": 8750.0}))
    run(db["bonifici_transfers"].insert_one({
        **_bonifico("b0", "MBVT20000000", 3750.0), "fattura_associata": True, "fattura_id": "1785340207136",
        "fattura_ids": ["1785340207136"], "fattura_associazione_evidenze": ["rif_banca_in_estratto"]}))
    assert run(abbina_bonifici_via_estratto(db))["fatture_riallineate"] == 1
    assert run(db["invoices"].find_one({"id": 1785340207136}))["bonifico_ids"] == ["b0"]
    assert run(abbina_bonifici_via_estratto(db))["fatture_riallineate"] == 0   # secondo giro: niente di nuovo
