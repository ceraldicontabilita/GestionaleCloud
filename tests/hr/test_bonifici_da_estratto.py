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
