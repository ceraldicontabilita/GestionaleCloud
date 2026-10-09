"""
Quietanza F24 dell'Agenzia Entrate → segna COMPLETATE le scadenze del
calendario fiscale (richiesta utente 12/07/2026).

Dal 02/10/2026 `_marca_scadenze_calendario` ha un chiamante: l'abbinamento
univoco quietanza ↔ modello (`abbina_quietanza_a_f24`). Il calendario e' un
modello generato in memoria (`genera_scadenze_anno`) e in archivio sta solo lo
stato: la riga nasce con la prima prova (upsert per `id` e `anno`), con
`completato_da=quietanza_f24` (evidenza documentale, distinta dalla conferma a
mano). Una scadenza gia' completata non si tocca. Ritenute/INPS sul mese di
versamento, IVA sul mese di competenza (mese di pagamento - 1).
"""
import asyncio

from app.services import quietanze_import as qi
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def test_mappa_codice_tributo_a_tipo_scadenza():
    assert qi._tipo_scadenza_da_codice('1040') == 'RITENUTE'
    assert qi._tipo_scadenza_da_codice('1001') == 'RITENUTE'
    assert qi._tipo_scadenza_da_codice('6001') == 'IVA'
    assert qi._tipo_scadenza_da_codice('6012') == 'IVA'
    assert qi._tipo_scadenza_da_codice('DM10') == 'INPS'
    assert qi._tipo_scadenza_da_codice('C10') == 'INPS'
    # RC01 = regolarizzazione periodo precedente: NON marca il mese corrente
    assert qi._tipo_scadenza_da_codice('RC01') == ''
    # codice ignoto
    assert qi._tipo_scadenza_da_codice('9999') == ''
    assert qi._tipo_scadenza_da_codice('') == ''


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _db(scadenze=()):
    db = ClientArchivioMemoria()["quietanze_scadenze"]

    async def _carica():
        for s in scadenze:
            await db[qi.COLL_CALENDARIO].insert_one(dict(s))
    _run(_carica())
    return db


def _cal(db):
    return {(d["id"], d.get("anno")): d for d in _run(db[qi.COLL_CALENDARIO].find({}, {"_id": 0}).to_list(50))}


def _f24(tributi):
    """Costruisce un F24 fittizio con i tributi dati (codice, sezione)."""
    doc = {"id": "F24X", "sezione_erario": [], "sezione_inps": []}
    for cod in tributi:
        if cod.upper().startswith(('DM', 'C', 'RC')) and not cod.isdigit():
            doc["sezione_inps"].append({"causale": cod, "periodo_riferimento": "", "importo_debito": 100})
        else:
            doc["sezione_erario"].append({"codice_tributo": cod, "periodo_riferimento": "", "importo_debito": 100})
    return doc


def test_marca_ritenute_e_inps_sul_mese_di_pagamento():
    db = _db([
        {"id": "ritenute_2026_02", "anno": 2026, "completato": False},
        {"id": "ritenute_2026_03", "anno": 2026, "completato": False},  # altro mese: non toccare
    ])
    marcate = _run(qi._marca_scadenze_calendario(db, _f24(['1040', 'DM10']), "2026-02-16", "Q1"))
    assert set(marcate) == {"ritenute_2026_02", "inps_2026_02"}
    cal = _cal(db)
    assert cal[("ritenute_2026_02", 2026)]["completato"] is True
    assert cal[("ritenute_2026_02", 2026)]["completato_da"] == "quietanza_f24"
    assert cal[("ritenute_2026_02", 2026)]["quietanza_id"] == "Q1"
    # la riga INPS non era in archivio (il calendario e' un modello): nasce qui
    assert cal[("inps_2026_02", 2026)]["completato"] is True
    assert cal[("inps_2026_02", 2026)]["f24_id"] == "F24X"
    assert cal[("ritenute_2026_03", 2026)]["completato"] is False  # marzo intatto


def test_marca_iva_sul_mese_di_competenza():
    # IVA pagata il 16/02 → competenza gennaio → iva_liq_2026_01
    db = _db()
    marcate = _run(qi._marca_scadenze_calendario(db, _f24(['6001']), "2026-02-16", "Q2"))
    assert marcate == ["iva_liq_2026_01"]
    assert _cal(db)[("iva_liq_2026_01", 2026)]["completato"] is True


def test_iva_gennaio_competenza_dicembre_anno_precedente():
    # IVA pagata il 16/01/2026 → competenza dicembre 2025 → iva_liq_2025_12, anno 2025
    db = _db()
    marcate = _run(qi._marca_scadenze_calendario(db, _f24(['6012']), "2026-01-16", "Q3"))
    assert marcate == ["iva_liq_2025_12"]
    assert ("iva_liq_2025_12", 2025) in _cal(db)


def test_rc01_non_marca_nulla():
    db = _db([{"id": "inps_2026_02", "anno": 2026, "completato": False}])
    marcate = _run(qi._marca_scadenze_calendario(db, _f24(['RC01']), "2026-02-16", "Q4"))
    assert marcate == []
    assert _cal(db)[("inps_2026_02", 2026)]["completato"] is False


def test_non_ritocca_scadenza_gia_completata():
    db = _db([{"id": "ritenute_2026_02", "anno": 2026, "completato": True,
               "completato_da": "conferma_manuale"}])
    marcate = _run(qi._marca_scadenze_calendario(db, _f24(['1040']), "2026-02-16", "Q5"))
    assert marcate == []
    riga = _cal(db)[("ritenute_2026_02", 2026)]
    assert riga["completato_da"] == "conferma_manuale" and "quietanza_id" not in riga
    assert len(_cal(db)) == 1  # nessuna seconda riga dall'upsert


def test_senza_data_pagamento_non_marca():
    db = _db([{"id": "ritenute_2026_02", "anno": 2026, "completato": False}])
    marcate = _run(qi._marca_scadenze_calendario(db, _f24(['1040']), "", "Q6"))
    assert marcate == []
    assert _cal(db)[("ritenute_2026_02", 2026)]["completato"] is False


def test_secondo_giro_non_riscrive():
    db = _db()
    assert _run(qi._marca_scadenze_calendario(db, _f24(['1040']), "2026-02-16", "Q7")) == ["ritenute_2026_02"]
    assert _run(qi._marca_scadenze_calendario(db, _f24(['1040']), "2026-02-16", "Q7")) == []
    assert len(_cal(db)) == 1


# ── il chiamante: l'abbinamento univoco quietanza ↔ modello ───────────────────

def _modello(id_):
    return {"id": id_, "status": "da_pagare", "file_name": f"{id_}.pdf",
            "dati_generali": {"codice_fiscale": "CF1", "data_versamento": "2026-02-16"},
            "totali": {"saldo_netto": 100.0},
            "sezione_erario": [{"codice_tributo": "1040", "periodo_riferimento": "01/2026",
                                "importo_debito": 100.0}]}


def _quietanza(id_):
    return {"id": id_, "protocollo_telematico": "26021612000000000/000001",
            "data_pagamento": "2026-02-16", "codice_fiscale": "CF1", "saldo": 100.0,
            "dati_generali": {"codice_fiscale": "CF1"},
            "sezione_erario": [{"codice_tributo": "1040", "periodo_riferimento": "01/2026",
                                "importo_debito": 100.0}], "f24_associati": []}


def test_l_abbinamento_univoco_segna_la_scadenza_del_calendario():
    db = _db()
    _run(db[qi.COLL_F24_COMMERCIALISTA].insert_one(_modello("F1")))
    _run(db[qi.COLL_QUIETANZE].insert_one(_quietanza("Q1")))

    esito = _run(qi.abbina_quietanza_a_f24(db, _quietanza("Q1")))

    [m] = esito["f24_matchati"]
    assert m["f24_id"] == "F1" and m["scadenze_completate"] == ["ritenute_2026_02"]
    riga = _cal(db)[("ritenute_2026_02", 2026)]
    assert riga["completato_da"] == "quietanza_f24" and riga["quietanza_id"] == "Q1" and riga["f24_id"] == "F1"


def test_con_due_candidati_il_calendario_non_si_tocca():
    db = _db()
    _run(db[qi.COLL_F24_COMMERCIALISTA].insert_one(_modello("F1")))
    _run(db[qi.COLL_F24_COMMERCIALISTA].insert_one(_modello("F2")))
    _run(db[qi.COLL_QUIETANZE].insert_one(_quietanza("Q1")))

    esito = _run(qi.abbina_quietanza_a_f24(db, _quietanza("Q1")))

    assert esito["f24_matchati"] == [] and len(esito["candidati"]) == 2
    assert _cal(db) == {}
