"""Dimissioni telematiche ricevute -> alert HR + scadenza UNILAV (5 giorni).

Caso reale: modulo Ministero del Lavoro di D'Alma Vincenzo (decorrenza
13/06/2024, trasmesso il 12/06/2024 da un patronato).
"""
import asyncio
from datetime import date

from mongomock_motor import AsyncMongoMockClient

from app.services import dimissioni_adempimenti as mod

METADATA = {
    "tipo_documento": "dimissioni_telematiche",
    "lavoratore_cf": "DLMVCN59E09F839T", "lavoratore_cognome": "D'ALMA", "lavoratore_nome": "VINCENZO",
    "datore_cf": "04523831214", "data_inizio_rapporto": "2023-07-15",
    "data_decorrenza_recesso": "2024-06-13", "tipo_comunicazione": "Dimissioni volontarie",
    "codice_modulo": "20240612173015973", "data_trasmissione": "2024-06-12",
}


def _run(coro):
    return asyncio.run(coro)


def _basi(monkeypatch):
    from app.hr.database import Database as DatabaseHR

    db = AsyncMongoMockClient()["gc"]
    hr = AsyncMongoMockClient()["hr"]
    monkeypatch.setattr(DatabaseHR, "get_db", classmethod(lambda cls: hr))
    return db, hr


def test_scadenze_unilav_5_giorni_e_revoca_7_giorni():
    scad = mod.scadenze_dimissioni(METADATA, oggi=date(2024, 6, 14))
    assert scad["scadenza_unilav"] == "2024-06-18"
    assert scad["giorni_alla_scadenza_unilav"] == 4
    assert scad["unilav_scaduta"] is False
    assert scad["revoca_possibile_fino_al"] == "2024-06-19"
    assert scad["revoca_ancora_possibile"] is True
    dopo = mod.scadenze_dimissioni(METADATA, oggi=date(2024, 7, 1))
    assert dopo["unilav_scaduta"] is True and dopo["revoca_ancora_possibile"] is False


def test_dimissioni_fresche_creano_alert_hr_e_scadenza_gestionale(monkeypatch):
    db, hr = _basi(monkeypatch)
    _run(hr.dipendenti.insert_one({"id": "dip-dalma", "nome_completo": "D'Alma Vincenzo",
                                   "codice_fiscale": "DLMVCN59E09F839T", "attivo": True, "stato": "attivo"}))

    esito = _run(mod.registra_dimissioni(db, METADATA, documento_id="doc-1", filename="DLMVCN59E09F839T_Dimissione.pdf",
                                         oggi=date(2024, 6, 14)))

    assert esito["hr"] == "aggiornato" and esito["alert"] is True and esito["scadenza_gestionale"] is True
    dip = _run(hr.dipendenti.find_one({"id": "dip-dalma"}, {"_id": 0}))
    assert dip["data_cessazione_prevista"] == "2024-06-13"
    assert dip["dimissioni"]["scadenza_unilav"] == "2024-06-18"
    assert dip["dimissioni"]["codice_modulo"] == "20240612173015973"
    assert len(dip["dimissioni"]["adempimenti"]) >= 5
    alert = _run(hr.alerts.find_one({"codice": "DIP_DIMISSIONI_RICEVUTE"}, {"_id": 0}))
    assert alert["entita_id"] == "dip-dalma" and alert["severita"] == "critical" and alert["stato"] == "aperto"
    assert "2024-06-18" in alert["dettaglio"] and "consulente del lavoro" in alert["dettaglio"]
    assert alert["extra"]["scadenza_unilav"] == "2024-06-18"
    scad = _run(db.notifiche_scadenze.find_one({"tipo": "UNILAV_CESSAZIONE"}, {"_id": 0}))
    assert scad["data_scadenza"] == "2024-06-18" and scad["priorita"] == "alta" and scad["completata"] is False
    assert "D'Alma Vincenzo" in scad["descrizione"]

    # idempotente: stesso modulo ricevuto di nuovo (email + Drive)
    ancora = _run(mod.registra_dimissioni(db, METADATA, documento_id="doc-2", oggi=date(2024, 6, 15)))
    assert ancora["alert"] is False and ancora["scadenza_gestionale"] is False
    assert _run(hr.alerts.count_documents({})) == 1
    assert _run(db.notifiche_scadenze.count_documents({})) == 1


def test_dimissioni_storiche_di_un_cessato_non_generano_alert(monkeypatch):
    """Il modulo di D'Alma del 2024 caricato oggi: archiviato sull'anagrafica,
    nessun alert e nessuna scadenza (gia' cessato, limite passato da mesi)."""
    db, hr = _basi(monkeypatch)
    _run(hr.dipendenti.insert_one({"id": "dip-dalma", "nome_completo": "D'Alma Vincenzo",
                                   "codice_fiscale": "DLMVCN59E09F839T", "attivo": False, "stato": "cessato",
                                   "data_cessazione": "2024-06-13"}))
    esito = _run(mod.registra_dimissioni(db, METADATA, documento_id="doc-1", oggi=date(2026, 9, 14)))
    assert esito["storico"] is True and esito["hr"] == "aggiornato"
    assert esito["alert"] is False and esito["scadenza_gestionale"] is False
    assert _run(hr.dipendenti.find_one({"id": "dip-dalma"}))["dimissioni"]["data_decorrenza"] == "2024-06-13"
    assert _run(hr.alerts.count_documents({})) == 0


def test_dipendente_non_in_anagrafica_hr_crea_comunque_la_scadenza(monkeypatch):
    db, hr = _basi(monkeypatch)
    esito = _run(mod.registra_dimissioni(db, METADATA, documento_id="doc-1", oggi=date(2024, 6, 14)))
    assert esito["hr"] == "dipendente_non_trovato" and esito["alert"] is False
    assert esito["scadenza_gestionale"] is True
    scad = _run(db.notifiche_scadenze.find_one({}, {"_id": 0}))
    assert "D'ALMA VINCENZO" in scad["descrizione"]


def test_archivio_documento_dimissioni_chiama_gli_adempimenti(monkeypatch):
    """Il PDF reale del Ministero passa dal riconoscimento del gestionale e
    arriva in HR senza altri passaggi."""
    import pathlib
    from app.routers import documenti as router_mod

    db, hr = _basi(monkeypatch)
    _run(hr.dipendenti.insert_one({"id": "dip-dalma", "nome_completo": "D'Alma Vincenzo",
                                   "codice_fiscale": "DLMVCN59E09F839T", "attivo": True}))
    pdf = pathlib.Path("/tmp/claude-0/-home-user/dc70995a-f7ab-510f-9b52-2067c1ed41ee/scratchpad/dimissioni_dalma.pdf")
    if not pdf.exists():
        import pytest
        pytest.skip("PDF reale non disponibile in questo ambiente")
    content = pdf.read_bytes()
    from app.services.administrative_document_parser import extract_administrative_metadata

    metadata = extract_administrative_metadata(content=content, filename=pdf.name, document_type="dimissioni_telematiche")
    assert metadata["lavoratore_cf"] == "DLMVCN59E09F839T"
    assert metadata["data_decorrenza_recesso"] == "2024-06-13"
    esito = _run(router_mod._archive_non_payment_document(
        db, filename=pdf.name, content=content, document_type="dimissioni_telematiche", metadata=metadata))
    assert esito["success"] is True
    assert esito["adempimenti_dimissioni"]["hr"] == "aggiornato"
    assert _run(hr.alerts.count_documents({"codice": "DIP_DIMISSIONI_RICEVUTE"})) == 1
