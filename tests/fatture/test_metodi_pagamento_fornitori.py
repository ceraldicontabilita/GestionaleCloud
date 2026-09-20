"""Il metodo del fornitore non deve poter sparire un'altra volta.

Il 20/09/2026 i metodi impostati non si sono ritrovati da nessuna parte: non
in `fornitori`, non nell'audit, non nelle proposte di aggiornamento, e nemmeno
nell'archivio legacy — che un campo metodo non ce l'ha proprio. Il
«dizionario» che esisteva (`/suppliers/dizionario-metodi-pagamento`) non
proteggeva niente: **legge** da `fornitori`, quindi si svuota insieme a lui.

Ora il dato ha tre appoggi: l'anagrafica, un file versionato in git, e uno
storico di ogni cambio. Questi test tengono fermi i tre.
"""
import asyncio
import json
import pathlib

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.services import metodi_pagamento_fornitori as motore


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def db(monkeypatch):
    finto = AsyncMongoMockClient()["Gestionale_Test"]
    from app.database import Database

    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: finto))
    return finto


def _fornitore(id_, nome, piva="", metodo=""):
    return {"id": id_, "nome": nome, "ragione_sociale": nome,
            "partita_iva": piva, "metodo_pagamento": metodo}


# ── il file versionato ─────────────────────────────────────────────────────

def test_il_file_esiste_ed_elenca_i_fornitori_veri():
    """E' la copia che sopravvive al database: se sparisce, siamo da capo."""
    documento = motore.leggi_file()

    assert len(documento["fornitori"]) >= 180, (
        "Il file di riferimento e' vuoto o troncato: non protegge piu' niente."
    )
    nomi = {f["nome"] for f in documento["fornitori"]}
    assert "SAIMA S.p.A." in nomi and "ME.PA. ALIMENTARI S.R.L." in nomi


def test_il_file_non_contiene_iban():
    """Le coordinate bancarie dei fornitori non vanno in un repository."""
    testo = motore.FILE_RIFERIMENTO.read_text(encoding="utf-8")

    assert "IT" not in testo or "iban" not in testo.lower(), (
        "Nel file compaiono IBAN: sono dati bancari di terzi, restano nel database."
    )


def test_il_file_e_json_valido_e_dichiara_i_metodi_ammessi():
    documento = json.loads(motore.FILE_RIFERIMENTO.read_text(encoding="utf-8"))

    assert documento["metodi_ammessi"] == list(motore.METODI_AMMESSI)


# ── la chiave ──────────────────────────────────────────────────────────────

def test_la_chiave_e_la_piva_quando_c_e():
    assert motore.chiave({"partita_iva": "01992440618", "nome": "SAIMA"}) == "01992440618"


def test_senza_piva_si_ripiega_sul_nome_normalizzato():
    """Su 188 fornitori solo 111 hanno la P.IVA: non e' un caso raro."""
    assert motore.chiave({"nome": "Nuova Bever-lì"}) == "nuova bever-li"
    assert motore.chiave({"nome": '"RONDINELLA MARKET S.R.L."'}) == "rondinella market s.r.l."


# ── l'importazione ─────────────────────────────────────────────────────────

def test_per_difetto_non_scrive_niente(db):
    run(db["fornitori"].insert_one(_fornitore("F1", "SAIMA S.p.A.", "01992440618")))

    esito = run(motore.importa(db, {"fornitori": [
        {"nome": "SAIMA S.p.A.", "partita_iva": "01992440618", "metodo_pagamento": "banca"}]}))

    assert esito["dry_run"] is True and esito["applicati"] == 1
    assert run(db["fornitori"].find_one({"id": "F1"}))["metodo_pagamento"] == ""


def test_con_dry_run_falso_applica_e_lascia_traccia(db):
    run(db["fornitori"].insert_one(_fornitore("F1", "SAIMA S.p.A.", "01992440618")))

    run(motore.importa(db, {"fornitori": [
        {"nome": "SAIMA S.p.A.", "partita_iva": "01992440618", "metodo_pagamento": "banca"}]},
        dry_run=False, attore="enzo"))

    assert run(db["fornitori"].find_one({"id": "F1"}))["metodo_pagamento"] == "banca"
    storico = run(db[motore.COLLEZIONE_STORICO].find({}).to_list(10))
    assert len(storico) == 1
    assert storico[0]["da"] == "" and storico[0]["a"] == "banca"
    assert storico[0]["attore"] == "enzo", (
        "Senza attore e timestamp non si puo' sapere chi ha cambiato cosa: e' "
        "esattamente il buio in cui i metodi sono spariti la prima volta."
    )


def test_un_metodo_vuoto_non_cancella_quello_impostato(db):
    """Il file arriva compilato a meta': le righe vuote si saltano."""
    run(db["fornitori"].insert_one(_fornitore("F1", "SAIMA S.p.A.", "01992440618", "banca")))

    run(motore.importa(db, {"fornitori": [
        {"nome": "SAIMA S.p.A.", "partita_iva": "01992440618", "metodo_pagamento": ""}]},
        dry_run=False))

    assert run(db["fornitori"].find_one({"id": "F1"}))["metodo_pagamento"] == "banca"


def test_un_metodo_inventato_viene_rifiutato(db):
    """«bonifico» non e' uno dei tre che il motore di instradamento legge."""
    run(db["fornitori"].insert_one(_fornitore("F1", "SAIMA S.p.A.", "01992440618")))

    esito = run(motore.importa(db, {"fornitori": [
        {"nome": "SAIMA S.p.A.", "partita_iva": "01992440618", "metodo_pagamento": "bonifico"}]},
        dry_run=False))

    assert esito["applicati"] == 0
    assert esito["metodi_rifiutati"] == [{"nome": "SAIMA S.p.A.", "metodo": "bonifico"}]
    assert run(db["fornitori"].find_one({"id": "F1"}))["metodo_pagamento"] == ""


def test_un_fornitore_che_non_esiste_si_segnala_non_si_crea(db):
    esito = run(motore.importa(db, {"fornitori": [
        {"nome": "MAI VISTO SRL", "partita_iva": "99999999999", "metodo_pagamento": "cassa"}]},
        dry_run=False))

    assert esito["fornitori_non_trovati"] == ["MAI VISTO SRL"]
    assert run(db["fornitori"].count_documents({})) == 0


def test_si_riconosce_il_fornitore_anche_solo_dal_nome(db):
    """77 fornitori su 188 non hanno P.IVA."""
    run(db["fornitori"].insert_one(_fornitore("F2", "Nuova Bever-lì")))

    run(motore.importa(db, {"fornitori": [
        {"nome": "Nuova Bever-lì", "partita_iva": "", "metodo_pagamento": "cassa"}]},
        dry_run=False))

    assert run(db["fornitori"].find_one({"id": "F2"}))["metodo_pagamento"] == "cassa"


# ── chi manca ──────────────────────────────────────────────────────────────

def test_sospesa_conta_come_metodo_mancante(db):
    """E' il valore che scrive l'import, ed e' il caso piu' frequente.

    La vecchia `validazione-p0` teneva la sua lista — None, "",
    "da_configurare", campo assente — e non lo conosceva: il problema piu'
    diffuso non veniva contato fra i problemi.
    """
    run(db["fornitori"].insert_many([
        _fornitore("F1", "Con metodo", "111", "banca"),
        _fornitore("F2", "Sospesa", "222", "sospesa"),
        _fornitore("F3", "Vuoto", "333", ""),
    ]))

    senza = run(motore.mancanti(db))

    assert {r["nome"] for r in senza} == {"Sospesa", "Vuoto"}


def test_si_compila_prima_chi_blocca_piu_fatture(db):
    run(db["fornitori"].insert_many([
        _fornitore("F1", "Poche fatture", "111"),
        _fornitore("F2", "Tante fatture", "222"),
    ]))
    run(db["invoices"].insert_many(
        [{"id": f"i{n}", "fornitore_id": "F2"} for n in range(5)]
        + [{"id": "x1", "fornitore_id": "F1"}]
    ))

    senza = run(motore.mancanti(db))

    assert [r["nome"] for r in senza] == ["Tante fatture", "Poche fatture"]
    assert senza[0]["fatture"] == 5


def test_la_validazione_p0_usa_lo_stesso_motore(db):
    """Due elenchi della stessa cosa vanno fuori sincrono: ne resta uno."""
    sorgente = (pathlib.Path(__file__).resolve().parents[2]
                / "app" / "routers" / "suppliers_module" / "validation.py"
                ).read_text(encoding="utf-8")

    assert "from app.services.metodi_pagamento_fornitori import mancanti" in sorgente
    assert '{"metodo_pagamento": "da_configurare"}' not in sorgente


# ── l'esportazione ─────────────────────────────────────────────────────────

def test_esporta_rilegge_i_dati_vivi(db):
    run(db["fornitori"].insert_many([
        _fornitore("F1", "SAIMA S.p.A.", "01992440618", "banca"),
        _fornitore("F2", "ME.PA. ALIMENTARI S.R.L.", "04352551214", ""),
    ]))

    documento = run(motore.esporta(db))

    per_nome = {f["nome"]: f["metodo_pagamento"] for f in documento["fornitori"]}
    assert per_nome == {"SAIMA S.p.A.": "banca", "ME.PA. ALIMENTARI S.R.L.": ""}
    assert documento["metodi_ammessi"] == list(motore.METODI_AMMESSI)


def test_esporta_e_importa_fanno_il_giro_completo(db):
    """Quello che esce deve poter rientrare: e' il recupero dopo una perdita."""
    run(db["fornitori"].insert_one(_fornitore("F1", "SAIMA S.p.A.", "01992440618", "banca")))
    copia = run(motore.esporta(db))

    run(db["fornitori"].update_one({"id": "F1"}, {"$set": {"metodo_pagamento": ""}}))
    run(motore.importa(db, copia, dry_run=False))

    assert run(db["fornitori"].find_one({"id": "F1"}))["metodo_pagamento"] == "banca"
