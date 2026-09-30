"""MINI-01: ogni documento importato porta `canale` e uno stato esplicito.

Il vocabolario sta in un posto solo (`app/constants/canale_documento.py`);
questi test provano che gli scrittori lo usano davvero alla creazione, non
che esiste.
"""
import asyncio
import base64

import pytest

from app.constants import canale_documento as cd
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(coro):
    return asyncio.run(coro)


# ── Il normalizzatore ─────────────────────────────────────────────────────

@pytest.mark.parametrize("grezzo,atteso", [
    # valori scritti oggi dagli scrittori: nessuno deve cadere in «altro» per sbaglio
    ("gmail_scan", "posta"), ("email_f24", "posta"), ("documents_inbox_email", "posta"),
    ("email_f24_fallback", "posta"), ("cedolino_gmail_import", "posta"),
    ("upload_manuale", "caricato"), ("f24_upload_pdf", "caricato"),
    ("f24_commercialista_upload", "caricato"), ("documenti_upload_auto", "caricato"),
    ("upload_manuale_pagina_salari", "caricato"), ("f24_quietanze_upload", "caricato"),
    ("drive", "drive"), ("google_drive", "drive"), ("drive_f24_email_import", "drive"),
    ("posta", "posta"), ("caricato", "caricato"), ("altro", "altro"),
    ("ai_parser_auto", "altro"), ("cedolino_v2", "altro"),
    ("", None), (None, None),
])
def test_canale_da_fonte_riduce_i_valori_grezzi(grezzo, atteso):
    assert cd.canale_da_fonte(grezzo) == atteso


def test_canale_obbligatorio_non_e_mai_vuoto():
    assert cd.canale_obbligatorio(None) == "altro"
    assert cd.canale_obbligatorio("qualcosa di nuovo") == "altro"
    # l'etichetta che dice il canale vince: un allegato di posta copiato su Drive resta posta
    assert cd.canale_obbligatorio("gmail_scan", drive_file_id="1abc") == "posta"
    # l'id Drive decide solo quando l'etichetta manca o non dice niente
    assert cd.canale_obbligatorio("", drive_file_id="1abc") == "drive"
    assert cd.canale_obbligatorio("ai_parser_auto", drive_file_id="1abc") == "drive"


def test_canali_documento_legge_prima_il_campo_canale_poi_l_archivio():
    assert cd.canali_documento({"canale": "posta"}) == ["posta"]
    assert cd.canali_documento({"fonte": "gmail_scan", "drive_file_id": "x"}) == ["posta", "drive"]
    assert cd.canali_documento({"fonte": "quietanze_f24"}, fonti_registro=("quietanze_f24",)) == ["altro"]
    assert cd.canali_documento({}) == ["altro"]


def test_il_motore_f24_usa_lo_stesso_normalizzatore():
    from app.services import f24_controllo_incrociato as fci
    assert fci.ORIGINI is cd.CANALI
    assert fci.origini_documento({"fonte": "quietanze_f24", "source_occurrences": [{"source": "gmail"}]}) == ["posta"]


# ── Gli scrittori ─────────────────────────────────────────────────────────

def test_il_modello_f24_nasce_col_canale_e_la_prima_copia_lo_fissa():
    from app.services.f24_canonico import COLL, salva_f24
    db = ClientArchivioMemoria()["test_canale_f24"]
    modello = {
        "dati_generali": {"codice_fiscale": "04523831214", "data_versamento": "2026-07-16"},
        "sezione_erario": [{"codice_tributo": "6006", "anno": "2026", "importo_debito_cents": 10000,
                            "importo_credito_cents": 0}],
        "totali": {"saldo_delega_cents": 10000},
    }
    id1 = _run(salva_f24(db, dict(modello), source="gmail_scan"))
    id2 = _run(salva_f24(db, dict(modello), source="f24_upload_pdf"))
    assert id1 == id2
    doc = _run(db[COLL].find_one({"id": id1}))
    assert doc["canale"] == "posta"


def test_la_lipe_nasce_canonica_e_la_ritrasmissione_ricorda_cosa_sostituisce(monkeypatch):
    from app.services import lipe_deposito as mod
    periodo = {
        "pagina": 4, "mese": "03", "periodo": "2026-03", "iva_esigibile": 10.0,
        "iva_detratta": 4.0, "iva_da_versare_o_credito": 6.0,
        "iva_da_versare_o_credito_segno": "debito", "quadratura_ok": True,
    }
    monkeypatch.setattr(mod, "parse_lipe", lambda _b: {"anno": "2026", "periodi": [periodo], "periodi_letti": 1})
    db = ClientArchivioMemoria()["test_canale_lipe"]

    _run(mod.deposita_lipe(db, b"pdf", nome_file="LIPE_2026_100.pdf", origine="drive", drive_file_id="f1"))
    prima = _run(db[mod.COLL_LIPE].find_one({"periodo": "2026-03"}))
    assert prima["canale"] == "drive" and prima["stato"] == "canonica" and prima["sostituisce"] == []

    _run(mod.deposita_lipe(db, b"pdf", nome_file="LIPE_2026_200.pdf", origine="documenti_upload_auto"))
    dopo = _run(db[mod.COLL_LIPE].find_one({"periodo": "2026-03"}))
    assert dopo["protocollo"] == 200 and dopo["sostituisce"] == [100]
    assert dopo["canale"] == "caricato" and dopo["stato"] in cd.STATI_LIPE_PERIODO
    assert _run(db[mod.COLL_LIPE].count_documents({})) == 1


def test_la_ricevuta_di_bonifico_nasce_documentata(monkeypatch):
    from app.services import bonifici_pdf_ingest as mod
    monkeypatch.setattr(mod, "read_pdf_bytes", lambda _c: "testo")
    monkeypatch.setattr(mod, "extract_transfers_from_text", lambda _t, filename=None: [{
        "importo": 1234.56, "data": "2026-07-27", "cro_trn": "TRN123",
        "beneficiario": {"nome": "ROSSI MARIO"},
    }])
    db = ClientArchivioMemoria()["test_canale_bonifico"]
    esito = _run(mod.importa_pdf_bonifico(
        db, b"%PDF-1.4 finto", "bonifico.pdf", source="upload_manuale_pagina_salari", auto_associa=False))
    assert esito["status"] == "saved", esito
    doc = _run(db["bonifici_transfers"].find_one({"id": esito["transfer_id"]}))
    assert doc["canale"] == "caricato"
    assert doc["stato_riconciliazione"] == cd.STATO_BONIFICO_DOCUMENTATO


def test_l_alert_nasce_aperto_col_vocabolario_unico():
    from app.services import alert_engine as mod
    db = ClientArchivioMemoria()["test_canale_alert"]
    codice = next(iter(mod.ALERT_CATALOG))
    alert = _run(mod.genera_alert(codice, "e1", "invoices", "prova", db))
    assert alert["stato"] == cd.STATO_ALERT_APERTO
    assert set(cd.STATI_ALERT) == {"aperto", "risolto", "ignorato"}


def test_ogni_busta_scritta_dal_motore_unico_porta_il_canale(monkeypatch):
    from app.services import cedolini_manager as mod
    from app.services.cedolini_motore import ESITO_BUSTE

    buste_viste = []

    async def _registra(db, ced, **_kw):
        buste_viste.append(dict(ced))

    monkeypatch.setattr(mod, "registra_busta", _registra)
    monkeypatch.setattr(mod, "_scrivi_scheda", lambda *a, **k: asyncio.sleep(0))
    monkeypatch.setattr("app.services.cedolini_motore.leggi_pdf", lambda *a, **k: {
        "esito": ESITO_BUSTE, "buste": [{"nome_dipendente": "X", "anno": 2026, "mese": 7}],
        "presenze": [], "fuori_periodo": [], "non_cedolino": [], "motivo": "",
    })
    db = ClientArchivioMemoria()["test_canale_cedolini"]
    pdf = base64.b64encode(b"%PDF-1.4").decode()
    _run(mod.processa_tutti_cedolini_pdf(db, pdf, "busta.pdf", fonte="posta"))
    _run(mod.processa_tutti_cedolini_pdf(db, pdf, "busta.pdf", drive_file_id="1abc"))
    _run(mod.processa_tutti_cedolini_pdf(db, pdf, "busta.pdf", drive_file_id="1abc", fonte="posta"))
    assert [b["canale"] for b in buste_viste] == ["posta", "drive", "posta"]
