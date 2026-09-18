"""Audit del commercialista 03/09/2026 §2, PR 7: un solo piano dei conti (CEE).

- ``scritture_contabili.scrivi_movimento`` non scrive mai una riga senza
  ``conto_contabile`` valido nel piano ufficiale (tesoreria) e, per le
  categorie note, senza ``conto_contropartita`` CEE; un conto fuori piano
  viene rifiutato;
- il backfill delle righe storiche (117 in Banca: Fatture 25, Stipendi 48,
  Assegni 23, PayPal 12, Commissioni 9; tutte quelle di Cassa) assegna solo
  i campi mancanti ed e' idempotente;
- le API del piano dei conti espongono i conti CEE con il codice operativo
  come alias e non scrivono piu' la collezione ``piano_conti``.
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.services.sheets_document_store import MemorySheetsClient

import app.routers.accounting.piano_conti as pc
from app.services import bonifica_prima_nota_conti as bonifica
from app.services import mapping_piano_conti as mpc
from app.services.piano_conti_ufficiale import CONTI_UFFICIALI, MACRO_UFFICIALE
from app.services.scritture_contabili import (
    ScritturaNonValida,
    scrivi_movimento,
    scrivi_movimento_se_assente,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── motore unico ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("registro,tipo,categoria,tesoreria,contropartita", [
    ("banca", "uscita", "Fatture", "19.01.01", "33.03.01"),
    ("banca", "uscita", "Assegni", "19.01.01", "33.03.01"),
    ("banca", "uscita", "Pagamento PayPal", "19.01.01", "33.03.01"),
    ("banca", "uscita", "Stipendi", "19.01.01", "39.07.01"),
    ("banca", "uscita", "TFR", "19.01.01", "39.07.05"),
    ("banca", "uscita", "Commissioni bancarie", "19.01.01", "75.01.07.04"),
    ("banca", "entrata", "Finanziamento soci", "19.01.01", "31.03.15"),
    ("banca", "entrata", "Versamento Banca", "19.01.01", "19.03.03"),
    ("cassa", "uscita", "Versamento Banca", "19.03.03", "19.01.01"),
    ("cassa", "entrata", "Corrispettivi", "19.03.03", "47.01.03"),
    ("cassa", "uscita", "POS NUMIA Verso Banca", "19.03.03", "15.07.01"),
    ("cassa", "uscita", "POS SUMUP Verso Banca", "19.03.03", "15.07.02"),
])
def test_scrivi_movimento_assegna_conti_cee_per_categoria(registro, tipo, categoria, tesoreria, contropartita):
    db = MemorySheetsClient()[f"conti-{registro}-{categoria}"]
    collezione = "prima_nota_banca" if registro == "banca" else "prima_nota_cassa"
    riga_id = _run(scrivi_movimento(db, registro, {
        "data": "2026-03-10", "tipo": tipo, "importo": 100.0,
        "categoria": categoria, "source": "test",
    }))
    riga = _run(db[collezione].find_one({"id": riga_id}, {"_id": 0}))
    assert riga["conto_contabile"] == tesoreria
    assert riga["conto_nome"] == CONTI_UFFICIALI[tesoreria]
    assert riga["conto_contropartita"] == contropartita
    assert riga["conto_contropartita_nome"] == CONTI_UFFICIALI[contropartita]
    assert riga["importo"] == 100.0


def test_conto_esplicito_valido_viene_rispettato_e_ha_la_contropartita():
    db = MemorySheetsClient()["conti-esplicito"]
    riga_id, _ = _run(scrivi_movimento_se_assente(db, "banca", {"id": "x"}, {
        "data": "2026-03-10", "tipo": "uscita", "importo": 2.0,
        "categoria": "Commissioni e spese bancarie", "source": "commissioni_sumup",
        "conto_contabile": "75.01.07.02", "gestore": "sumup",
    }))
    riga = _run(db.prima_nota_banca.find_one({"id": riga_id}, {"_id": 0}))
    assert riga["conto_contabile"] == "75.01.07.02"
    assert riga["conto_contropartita"] == "15.07.02"


def test_conto_fuori_dal_piano_cee_viene_rifiutato():
    db = MemorySheetsClient()["conti-rifiuto"]
    with pytest.raises(ScritturaNonValida):
        _run(scrivi_movimento(db, "banca", {
            "data": "2026-03-10", "tipo": "uscita", "importo": 10.0,
            "categoria": "Fatture", "source": "test", "conto_contabile": "02.01.01",
        }))
    with pytest.raises(ScritturaNonValida):
        _run(scrivi_movimento(db, "cassa", {
            "data": "2026-03-10", "tipo": "uscita", "importo": 10.0,
            "categoria": "Spese", "source": "test", "conto_contropartita": "99.99.99",
        }))
    assert _run(db.prima_nota_banca.count_documents({})) == 0
    assert _run(db.prima_nota_cassa.count_documents({})) == 0


def test_categoria_ignota_ha_il_conto_di_tesoreria_ma_nessuna_contropartita_inventata():
    db = MemorySheetsClient()["conti-ignota"]
    riga_id = _run(scrivi_movimento(db, "banca", {
        "data": "2026-03-10", "tipo": "uscita", "importo": 10.0,
        "categoria": "Altro", "source": "test",
    }))
    riga = _run(db.prima_nota_banca.find_one({"id": riga_id}, {"_id": 0}))
    assert riga["conto_contabile"] == "19.01.01"
    assert "conto_contropartita" not in riga
    assert riga["contropartita_da_classificare"] is True


def test_ogni_conto_assegnato_esiste_nel_piano_ufficiale():
    for chiave, regola in mpc._CONTROPARTITE.items():
        for registro in ("banca", "cassa"):
            for gestore in ("numia", "sumup", "paypal"):
                codice = regola(registro, "uscita", gestore) if callable(regola) else regola
                assert mpc.conto_cee_valido(codice), (chiave, codice)
    for codice in ("19.01.01", "19.03.03", "19.01.05"):
        assert codice in CONTI_UFFICIALI
    for op, uff in mpc.OPERATIVO_A_UFFICIALE.items():
        assert uff in CONTI_UFFICIALI or uff in MACRO_UFFICIALE, (op, uff)


def test_ogni_conto_operativo_esteso_ha_un_alias_cee():
    from app.services.categorizzazione_contabile import PIANO_CONTI_ESTESO
    from app.routers.accounting.piano_conti import STRUTTURA_BASE

    codici = set(PIANO_CONTI_ESTESO) | {
        c["codice"] for g in STRUTTURA_BASE.values() for c in g["conti_tipici"]
    }
    senza = sorted(c for c in codici if not mpc.risolvi_codice_cee(c))
    assert senza == [], senza


# ── backfill ─────────────────────────────────────────────────────────────────

def _db_storico():
    db = MemorySheetsClient()["backfill-conti"]

    async def semina():
        await db.prima_nota_banca.insert_many([
            {"id": "f1", "data": "2026-02-23", "tipo": "uscita", "importo": 2787.08,
             "categoria": "Fatture", "source": "ric_auto_identita_unica"},
            {"id": "s1", "data": "2026-02-27", "tipo": "uscita", "importo": 1200.0,
             "categoria": "Stipendi", "source": "proiezione_semantica_ec"},
            {"id": "a1", "data": "2026-01-02", "tipo": "uscita", "importo": 1403.01,
             "categoria": "Assegni", "source": "assegno_estratto_conto"},
            {"id": "p1", "data": "2026-01-05", "tipo": "uscita", "importo": 11.99,
             "categoria": "Pagamento PayPal", "source": "proiezione_semantica_ec"},
            {"id": "c1", "data": "2026-01-31", "tipo": "uscita", "importo": 3.0,
             "categoria": "Commissioni bancarie", "source": "proiezione_semantica_ec"},
            # riga POS gia' con conto: solo la contropartita manca
            {"id": "pos1", "data": "2026-01-03", "tipo": "entrata", "importo": 3007.9,
             "categoria": "Corrispettivi POS", "source": "trasferimento_pos",
             "gestore": "numia", "conto_contabile": "15.07.01", "conto_nome": "Crediti verso Nexi/Numia"},
            # riga marcata: non si tocca
            {"id": "del", "data": "2026-01-03", "tipo": "uscita", "importo": 1.0,
             "categoria": "Fatture", "source": "x", "status": "deleted", "entity_status": "deleted"},
        ])
        await db.prima_nota_cassa.insert_many([
            {"id": "k1", "data": "2026-03-22", "tipo": "entrata", "importo": 4629.20,
             "categoria": "Corrispettivi", "source": "corrispettivo_import"},
            {"id": "k2", "data": "2026-03-22", "tipo": "uscita", "importo": 2962.30,
             "categoria": "POS NUMIA Verso Banca", "source": "corrispettivo_import"},
        ])

    _run(semina())
    return db


def test_backfill_dry_run_conta_e_non_scrive():
    db = _db_storico()
    esito = _run(bonifica.esegui(db, dry_run=True))
    assert esito["dry_run"] is True
    assert esito["totale_righe_da_aggiornare"] == 8
    assert esito["registri"]["banca"]["senza_conto_contabile"] == 5
    assert esito["registri"]["banca"]["righe_da_aggiornare"] == 6
    assert esito["registri"]["banca"]["per_categoria"] == {
        "Fatture": 1, "Stipendi": 1, "Assegni": 1, "Pagamento PayPal": 1,
        "Commissioni bancarie": 1, "Corrispettivi POS": 1,
    }
    assert esito["registri"]["cassa"]["righe_da_aggiornare"] == 2
    assert esito["totale_conti_non_validi"] == 0
    assert "conto_contabile" not in _run(db.prima_nota_banca.find_one({"id": "f1"}))


def test_backfill_applica_solo_i_campi_mancanti_ed_e_idempotente():
    db = _db_storico()
    esito = _run(bonifica.esegui(db, dry_run=False, actor="test"))
    assert esito["righe_aggiornate"] == 8

    banca = {r["id"]: r for r in _run(db.prima_nota_banca.find({}).to_list(None))}
    cassa = {r["id"]: r for r in _run(db.prima_nota_cassa.find({}).to_list(None))}
    attese = {
        "f1": ("19.01.01", "33.03.01"), "s1": ("19.01.01", "39.07.01"),
        "a1": ("19.01.01", "33.03.01"), "p1": ("19.01.01", "33.03.01"),
        "c1": ("19.01.01", "75.01.07.04"), "pos1": ("15.07.01", "19.03.03"),
    }
    for riga_id, (conto, contro) in attese.items():
        assert banca[riga_id]["conto_contabile"] == conto, riga_id
        assert banca[riga_id]["conto_contropartita"] == contro, riga_id
    assert banca["f1"]["importo"] == 2787.08 and banca["f1"]["categoria"] == "Fatture"
    assert "conto_contabile" not in banca["del"]
    assert cassa["k1"]["conto_contabile"] == "19.03.03" and cassa["k1"]["conto_contropartita"] == "47.01.03"
    assert cassa["k2"]["conto_contabile"] == "19.03.03" and cassa["k2"]["conto_contropartita"] == "15.07.01"

    di_nuovo = _run(bonifica.esegui(db, dry_run=False, actor="test"))
    assert di_nuovo["righe_aggiornate"] == 0 and di_nuovo["totale_righe_da_aggiornare"] == 0
    assert _run(db.prima_nota_migrazioni_audit.count_documents({})) == 1


def test_il_saldo_bpm_non_cambia_dopo_il_backfill():
    """Le letture di tesoreria trattano conto assente e 19.01.01 allo stesso
    modo: assegnare la contropartita in un campo separato non sposta soldi."""
    from app.routers.prima_nota_module.common import saldi_finanziari

    db = _db_storico()
    prima = _run(saldi_finanziari(db, 2026))
    _run(bonifica.esegui(db, dry_run=False))
    dopo = _run(saldi_finanziari(db, 2026))
    assert prima["conti_reali"] == dopo["conti_reali"]
    assert prima["crediti_pos"] == dopo["crediti_pos"]


def test_endpoint_bonifica_prima_nota_include_i_conti(monkeypatch):
    from app.database import Database
    from app.routers.admin import bonifica_prima_nota_doppioni

    db = _db_storico()
    monkeypatch.setattr(Database, "db", db)
    utente = {"sub": "admin-test", "role": "admin"}
    analisi = _run(bonifica_prima_nota_doppioni(dry_run=True, current_user=utente))
    assert analisi["righe_conti_da_aggiornare"] == 8
    applicata = _run(bonifica_prima_nota_doppioni(dry_run=False, current_user=utente))
    assert applicata["righe_conti_aggiornate"] == 8


# ── API piano dei conti ──────────────────────────────────────────────────────

def test_api_piano_conti_espone_solo_il_cee_con_alias(monkeypatch):
    db = MemorySheetsClient()["piano-cee-api"]
    _run(db.piano_conti.insert_many([
        {"id": "1", "codice": "05.01.01", "nome": "Acquisto merci", "categoria": "costi", "saldo": 0},
        {"id": "2", "codice": "77.77.77", "nome": "Conto a mano", "categoria": "costi", "saldo": 0},
    ]))
    monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))

    async def _saldi(_db, anno=None):
        return {"05.01.01": 100.0, "05.01.02": 40.0, "01.01.02": 3000.0, "55.01.07": 5.0}
    monkeypatch.setattr(pc, "_calcola_saldi_piano_conti", _saldi)

    res = _run(pc.get_piano_conti(anno="2026"))
    assert res["schema"] == "CEE" and res["totale"] == len(mpc.CODICI_PIANO)
    per_codice = {c["codice"]: c for c in res["conti"]}
    assert set(per_codice) == set(mpc.CODICI_PIANO) >= set(CONTI_UFFICIALI)
    assert per_codice["41"]["alias_operativi"] == ["01.05.01", "05.04.01", "05.04.02", "05.04.03"]
    assert per_codice["55.01.07"]["alias_operativo"] == "05.01.01"
    assert per_codice["55.01.07"]["saldo"] == 105.0   # alias + codice gia' CEE
    assert per_codice["55.01.01"]["saldo"] == 40.0
    assert per_codice["19.01.01"]["saldo"] == 3000.0 and per_codice["19.01.01"]["categoria"] == "attivo"
    assert per_codice["15.07.01"]["categoria"] == "attivo"
    assert per_codice["75.01.07.02"]["categoria"] == "costi"
    assert res["conti_operativi_non_mappati"] == [
        {"codice": "77.77.77", "nome": "Conto a mano", "categoria": "costi"},
    ]
    assert len(res["grouped"]["costi"]) == len([c for c in res["conti"] if c["categoria"] == "costi"])
    # nessuna scrittura sulla collezione dismessa
    assert _run(db.piano_conti.count_documents({})) == 2


def test_api_piano_conti_non_crea_ne_modifica_conti(monkeypatch):
    db = MemorySheetsClient()["piano-cee-crud"]
    monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))
    with pytest.raises(HTTPException) as nuovo:
        _run(pc.create_conto({"codice": "05.02.03", "nome": "Spese telefoniche", "categoria": "costi"}))
    assert nuovo.value.status_code == 409 and "65" in nuovo.value.detail
    with pytest.raises(HTTPException) as ignoto:
        _run(pc.create_conto({"codice": "99.99.99", "nome": "X", "categoria": "costi"}))
    assert ignoto.value.status_code == 409
    with pytest.raises(HTTPException):
        _run(pc.update_conto("cee:55.01.07", {"nome": "altro"}))
    with pytest.raises(HTTPException):
        _run(pc.delete_conto("cee:55.01.07"))
    assert _run(db.piano_conti.count_documents({})) == 0
    assert _run(pc.inizializza_piano_conti_base(db)) == mpc.piano_conti_cee()
    assert _run(db.piano_conti.count_documents({})) == 0


def test_bilancio_usa_il_piano_cee(monkeypatch):
    db = MemorySheetsClient()["piano-cee-bilancio"]
    monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))

    async def _saldi(_db, anno=None):
        return {"01.01.01": 100.0, "05.01.01": 25.0}
    monkeypatch.setattr(pc, "_calcola_saldi_piano_conti", _saldi)

    res = _run(pc.get_bilancio(anno="2026"))
    attivo = res["stato_patrimoniale"]["attivo"]["conti"]
    assert res["stato_patrimoniale"]["attivo"]["totale"] == 100.0
    assert res["conto_economico"]["costi"]["totale"] == 25.0
    assert len({c["codice"] for c in attivo}) == len(attivo)
    cassa = next(c for c in attivo if c["codice"] == "19.03.03")
    assert cassa["saldo"] == 100.0 and cassa["alias_operativi"] == ["01.01.01"]
    assert res["bilancio_ufficiale"]["conto_economico"][0]["descrizione"] == "Acquisti merci"


def test_movimenti_per_conto_accetta_codice_cee_e_alias(monkeypatch):
    db = MemorySheetsClient()["piano-cee-movimenti"]
    _run(db.prima_nota_cassa.insert_one({
        "id": "k1", "data": "2026-03-22", "tipo": "entrata", "importo": 10.0,
        "categoria": "Corrispettivi",
    }))
    monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))
    per_cee = _run(pc.get_movimenti_per_conto(codice="19.03.03", anno="2026"))
    per_alias = _run(pc.get_movimenti_per_conto(codice="01.01.01", anno="2026"))
    assert per_cee["fonte"] == per_alias["fonte"] == "prima_nota_cassa"
    assert per_cee["totale_movimenti"] == per_alias["totale_movimenti"] == 1
    assert per_cee["conto"]["codice"] == per_alias["conto"]["codice"] == "19.03.03"
    with pytest.raises(HTTPException) as ignoto:
        _run(pc.get_movimenti_per_conto(codice="99.99.99"))
    assert ignoto.value.status_code == 404
