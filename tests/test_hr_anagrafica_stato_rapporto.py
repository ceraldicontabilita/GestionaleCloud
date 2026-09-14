"""Anagrafica HR, titolare 14/09/2026 (B1-B7): un solo stato del rapporto con
data e motivo, PUT non distruttivo, PIN nella scheda, documenti con file,
buste in attesa separate per anno."""
import asyncio
import hashlib
import io

import pytest
from fastapi import HTTPException, UploadFile
from mongomock_motor import AsyncMongoMockClient

from app.hr.routers import dipendenti_cloud as mod
from app.hr.services import stato_rapporto


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def hr(monkeypatch):
    from app.hr.database import Database as DatabaseHR

    db = AsyncMongoMockClient()["hr_test"]
    monkeypatch.setattr(DatabaseHR, "get_db", classmethod(lambda cls: db))
    monkeypatch.setenv("PIN_HASH_ADMIN", hashlib.sha256(b"990011").hexdigest())
    _run(db.dipendenti.insert_many([
        {"id": "dip-mosc", "nome": "Emanuele", "cognome": "Moscato", "codice_fiscale": "MSCMNL88R26F839C",
         "matricola": "0200020", "data_nascita": "1988-10-26", "indirizzo": "Via Emanuele de Deo, Napoli",
         "data_assunzione": "2012-03-13", "stato": "inattivo", "attivo": True, "ruolo": "5.2.2.3.2.4 - cameriere di bar"},
        {"id": "dip-pocci", "nome": "Salvatore", "cognome": "Pocci", "codice_fiscale": "PCCSVT69P30F839G",
         "stato": "attivo", "attivo": True, "pin_hash": "x"},
        {"id": "dip-fuso", "nome": "Antonella", "cognome": "Ceraldi", "merged_into": "altro"},
    ]))
    return db


def test_stato_unico_con_data_e_motivo():
    assert stato_rapporto.riepilogo_stato({"stato": "attivo", "attivo": True})["stato"] == "attivo"
    # "inattivo" con attivo=true (Moscato il 14/09) = cessato, non un terzo stato
    st = stato_rapporto.riepilogo_stato({"stato": "inattivo", "attivo": True})
    assert st["stato"] == "cessato" and st["attivo"] is False and st["data_fine_rapporto"] is None
    st = stato_rapporto.riepilogo_stato({"stato": "cessato", "attivo": False, "data_cessazione": "01/07/2026",
                                         "motivo_cessazione": "storico_cedolini"})
    assert st["data_fine_rapporto"] == "2026-07-01" and st["motivo_cessazione"] == "altro"
    assert stato_rapporto.riepilogo_stato({"merged_into": "x"})["stato"] == "cessato"
    with pytest.raises(ValueError):
        stato_rapporto.campi_cessazione("31-13-2026")
    campi = stato_rapporto.campi_cessazione("31/08/2026", "dimissioni", "20260730155946178")
    assert campi["data_fine_rapporto"] == "2026-08-31" and campi["attivo"] is False and campi["stato"] == "cessato"


def test_lista_espone_stato_normalizzato_e_mai_il_pin(hr):
    out = {d["id"]: d for d in _run(mod.get_dipendenti())}
    assert "dip-fuso" not in out
    assert out["dip-mosc"]["stato"] == "cessato" and out["dip-mosc"]["matricola"] == "0200020"
    assert out["dip-pocci"]["stato"] == "attivo" and out["dip-pocci"]["pin_impostato"] is True
    assert out["dip-pocci"]["lotti_operatore"] is True
    assert not any("pin_hash" in d for d in out.values())


def test_put_aggiorna_solo_i_campi_inviati_e_non_tocca_lo_stato(hr):
    esito = _run(mod.update_dipendente("dip-mosc", mod.DipendenteCloud(nome="Emanuele", cognome="Moscato",
                                                                       email="e@example.com", stato="attivo")))
    dip = _run(hr.dipendenti.find_one({"id": "dip-mosc"}, {"_id": 0}))
    assert dip["matricola"] == "0200020" and dip["data_nascita"] == "1988-10-26" and dip["indirizzo"]
    assert dip["data_assunzione"] == "2012-03-13" and dip["email"] == "e@example.com"
    assert dip["stato"] == "inattivo"  # lo stato non passa dal PUT
    assert esito["dipendente"]["stato"] == "cessato" and esito["dipendente"]["nome_completo"] == "Moscato Emanuele"
    with pytest.raises(HTTPException):
        _run(mod.update_dipendente("manca", mod.DipendenteCloud(nome="a", cognome="b")))


def test_cessa_con_data_motivo_riferimento_e_riattiva(hr):
    with pytest.raises(HTTPException) as exc:
        _run(mod.cessa_dipendente("dip-pocci", mod.CessazioneCloud(data_cessazione="", motivo="dimissioni")))
    assert exc.value.status_code == 400
    esito = _run(mod.cessa_dipendente("dip-pocci", mod.CessazioneCloud(
        data_cessazione="2026-08-31", motivo="dimissioni", riferimento="20260730155946178")))
    assert esito["ok"] and esito["dipendente"]["stato"] == "cessato"
    assert esito["dipendente"]["data_fine_rapporto"] == "2026-08-31"
    assert esito["dipendente"]["motivo_cessazione_etichetta"] == "Dimissioni"
    assert esito["dipendente"]["riferimento_cessazione"] == "20260730155946178"
    dip = _run(hr.dipendenti.find_one({"id": "dip-pocci"}, {"_id": 0}))
    assert dip["attivo"] is False and dip["in_carico"] is False and dip["data_cessazione"] == "2026-08-31"
    assert "pin_hash" not in dip  # l'handler di cessazione revoca il PIN
    lista = {d["id"]: d for d in _run(mod.get_dipendenti())}
    assert lista["dip-pocci"]["stato"] == "cessato"

    esito = _run(mod.riattiva_dipendente("dip-pocci"))
    assert esito["dipendente"]["stato"] == "attivo" and esito["dipendente"]["data_fine_rapporto"] is None
    dip = _run(hr.dipendenti.find_one({"id": "dip-pocci"}, {"_id": 0}))
    assert dip["cessazioni_precedenti"][0]["data_fine_rapporto"] == "2026-08-31"
    assert "motivo_cessazione" not in dip and dip["attivo"] is True


def test_pin_dalla_scheda(hr):
    with pytest.raises(HTTPException) as exc:
        _run(mod.imposta_pin_dipendente("dip-pocci", mod.PinCloud(pin="12")))
    assert exc.value.status_code == 400
    assert _run(mod.imposta_pin_dipendente("dip-pocci", mod.PinCloud(pin="4455")))["pin_impostato"] is True
    dip = _run(hr.dipendenti.find_one({"id": "dip-pocci"}, {"_id": 0}))
    assert dip["pin_hash"].startswith("$2") and dip["pin_lookup"]
    assert _run(mod.rimuovi_pin_dipendente("dip-pocci"))["pin_impostato"] is False


def test_nuovo_documento_con_file_e_lista_senza_base64(hr):
    pdf = b"%PDF-1.4 finto " + b"x" * 600
    up = UploadFile(filename="Lettera.pdf", file=io.BytesIO(pdf))
    doc = _run(mod.create_documento(dipendente_id="dip-pocci", titolo="Lettera di licenziamento",
                                    tipo="Lettera di licenziamento", scadenza=None, file=up))
    assert doc["categoria"] == "LICENZIAMENTO" and doc["ha_file"] is True and "file_data" not in doc
    with pytest.raises(HTTPException) as exc:
        _run(mod.create_documento(dipendente_id="dip-pocci", titolo="doppio", tipo="Altro", scadenza=None,
                                  file=UploadFile(filename="Lettera.pdf", file=io.BytesIO(pdf))))
    assert exc.value.status_code == 409
    solo_meta = _run(mod.create_documento(dipendente_id="dip-pocci", titolo="Nota", tipo="Dimissioni / cessazione",
                                          scadenza="2026-08-31", file=None))
    assert solo_meta["categoria"] == "DIMISSIONI" and solo_meta["ha_file"] is False
    lista = _run(mod.get_documenti())
    assert len(lista) == 2 and all("file_data" not in d for d in lista)
    assert {d["ha_file"] for d in lista} == {True, False}
    assert mod.classifica_documento("Modulo recesso rapporto di lavoro ...", "x.pdf") == "DIMISSIONI"
    assert mod.classifica_documento("", "MSCMNL88R26F839C_Dimissione.pdf") == "DIMISSIONI"


def test_buste_in_attesa_anno_corrente_prima_e_storico_separato(hr):
    from datetime import datetime
    anno = datetime.now().year
    _run(hr.paghe_mensili.insert_many([
        {"dipendente_id": "dip-pocci", "anno": 2019, "mese": 5, "importo_busta": 1000, "bonifico_importo": 0, "stato_pagamento": "in_attesa_pagamento"},
        {"dipendente_id": "dip-pocci", "anno": anno, "mese": 2, "importo_busta": 1200, "bonifico_importo": 0, "stato_pagamento": "in_attesa_pagamento"},
        {"dipendente_id": "dip-pocci", "anno": anno, "mese": 1, "importo_busta": 1200, "bonifico_importo": 1200, "stato_pagamento": "pagato"},
    ]))
    out = _run(mod.paghe_in_attesa())
    assert [(r["anno"], r["storico"]) for r in out["righe"]] == [(anno, False), (2019, True)]
    assert out["da_pagare"] == {"totale": 1, "importo": 1200.0}
    assert out["non_agganciate"] == {"totale": 1, "importo": 1000.0}
    stats = _run(mod.get_dashboard_stats())
    assert stats["buste_in_attesa"] == 1 and stats["importo_in_attesa"] == 1200.0
    assert stats["buste_storiche_non_agganciate"] == 1 and stats["importo_storico_non_agganciato"] == 1000.0
    assert stats["dipendenti_attivi"] == 1  # Moscato "inattivo" non conta, il fuso nemmeno
