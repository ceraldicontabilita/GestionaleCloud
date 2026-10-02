"""Decisioni del titolare del 02/10/2026 sui verbali e il noleggio, provate sui motori veri.

1. Importo atteso: 5 giorni dopo la notifica PEC passa all'ordinario, ridotto nello storico, alert.
2. Ricevuta pagoPA senza verbale: conservata «senza verbale» con alert, mai un verbale creato;
   l'arrivo del verbale la aggancia e chiude l'alert.
3. Assegnazioni veicolo→driver con data e ora; una riga senza ora vale il giorno intero.
4. Trattenuta in busta: nasce solo a verbale pagato con quietanza, mai all'assegnazione del driver.
"""

import asyncio
import base64
import io
from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.services import pagopa_receipts
from app.services import verbali_document_import as vdi
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.noleggio.controlli import driver_alla_data, normalizza_istante_assegnazione
from app.services.notifiche_pec_verbali import registra_notifica_pec
from app.services.partenopay_archive_import import dispatch_due_verbali_notifications
from app.services.trattenute_verbali_service import proponi_trattenuta_verbale_pagato
from app.services.verbali_evidence import data_ora_evento_verbale
from app.services.verbali_importo_atteso import (
    CODICE_ALERT,
    FONTE_ORDINARIO,
    aggiorna_importi_attesi,
    applica_importo_ordinario,
)
from app.services.verbali_pagamento_finder import applica_pagamento_a_verbale


def _run(coro):
    return asyncio.run(coro)


def _db(nome):
    return ClientArchivioMemoria()[nome]


def _pdf(righe) -> bytes:
    buffer = io.BytesIO()
    pagina = canvas.Canvas(buffer, pagesize=A4)
    y = 800
    for riga in righe:
        pagina.drawString(40, y, riga)
        y -= 16
    pagina.save()
    return buffer.getvalue()


RIGHE_VERBALE = [
    "COMUNE DI NAPOLI - POLIZIA LOCALE",
    "Verbale n. A26110812778 Registro n. 20260200899 emesso in data 20/07/2026",
    "Violazione commessa il 10/04/2026 alle ore 15:25 in via Cesare Battisti",
    "Veicolo targa AB123CD",
    "Importo da pagare: 57,05 euro",
]


def _verbale(db, **extra):
    base = {
        "id": "v1", "numero_verbale": "A26110812778", "targa": "AB123CD",
        "importo": 57.05, "importo_ridotto": 57.05, "importo_ordinario": 81.50,
        "stato": "fattura_ricevuta", "driver_id": "d1", "driver": "Mario",
        "data_notifica": "2026-09-20", "data_notifica_fonte": "pec",
    }
    base.update(extra)
    _run(db["verbali_noleggio"].insert_one(base))
    return base


def _alert_aperti(db, codice, entita_id):
    return _run(db["alerts"].count_documents({"codice": codice, "entita_id": entita_id, "stato": "aperto"}))


# ── 1. Importo atteso: ridotto nei 5 giorni, poi ordinario ──────────────────────────────

class TestImportoAttesoOrdinario:
    def test_dopo_5_giorni_dalla_pec_l_atteso_e_l_ordinario_il_ridotto_resta_nello_storico(self):
        db = _db("atteso-ordinario")
        _verbale(db)
        esito = _run(aggiorna_importi_attesi(db, oggi=date(2026, 9, 26)))   # sesto giorno
        assert esito["aggiornati"] == 1, esito

        v = _run(db["verbali_noleggio"].find_one({"id": "v1"}, {"_id": 0}))
        assert v["importo"] == 81.50 and v["importo_centesimi"] == 8150
        assert v["importo_atteso"] == "81.50" and v["importo_atteso_fonte"] == FONTE_ORDINARIO
        assert v["importo_atteso_dal"] == "2026-09-26" and v["importo_ridotto_scaduto_il"] == "2026-09-25"
        assert v["importo_ridotto"] == 57.05                       # il ridotto non sparisce
        voce = v["storico"][-1]
        assert voce["tipo"] == "importo_atteso_ordinario"
        assert voce["importo_prima"] == "57.05" and voce["importo_dopo"] == "81.50"
        assert "scaduti i 5 giorni" in voce["motivo"] and "20/09/2026" in voce["motivo"]

        alert = _run(db["alerts"].find_one({"codice": CODICE_ALERT}, {"_id": 0}))
        assert alert["entita_collection"] == "verbali_noleggio" and alert["entita_id"] == "v1"
        assert "scaduti i 5 giorni" in alert["dettaglio"] and "importo ordinario 81.50" in alert["dettaglio"]

    def test_secondo_giro_zero_cambiamenti(self):
        db = _db("atteso-idempotente")
        _verbale(db)
        _run(aggiorna_importi_attesi(db, oggi=date(2026, 10, 1)))
        esito = _run(aggiorna_importi_attesi(db, oggi=date(2026, 10, 1)))
        assert esito["aggiornati"] == 0 and esito["letti"] == 0, esito
        v = _run(db["verbali_noleggio"].find_one({"id": "v1"}, {"_id": 0}))
        assert len(v["storico"]) == 1
        assert _alert_aperti(db, CODICE_ALERT, "v1") == 1

    def test_entro_i_5_giorni_resta_il_ridotto(self):
        db = _db("atteso-entro")
        _verbale(db)
        esito = _run(aggiorna_importi_attesi(db, oggi=date(2026, 9, 25)))    # quinto giorno
        assert esito["aggiornati"] == 0 and esito["saltati"] == {"entro_i_5_giorni": 1}
        assert _run(db["verbali_noleggio"].find_one({"id": "v1"}))["importo"] == 57.05
        assert _alert_aperti(db, CODICE_ALERT, "v1") == 0

    def test_pagato_o_in_quarantena_non_cambia(self):
        db = _db("atteso-chiusi")
        _verbale(db, id="pagato", stato="pagato", pagato_documentalmente=True)
        _verbale(db, id="quar", stato="quarantena")
        _verbale(db, id="dich", importo_pagato="57.05")
        esito = _run(aggiorna_importi_attesi(db, oggi=date(2026, 12, 1)))
        assert esito["aggiornati"] == 0
        for vid in ("pagato", "quar", "dich"):
            assert _run(db["verbali_noleggio"].find_one({"id": vid}))["importo"] == 57.05

    def test_senza_ordinario_letto_o_senza_pec_non_si_inventa_niente(self):
        db = _db("atteso-senza-dati")
        _verbale(db, id="no-ord", importo_ordinario=None)
        _verbale(db, id="no-pec", data_notifica_fonte="email")
        esito = _run(aggiorna_importi_attesi(db, oggi=date(2026, 12, 1)))
        assert esito["aggiornati"] == 0
        assert _run(db["verbali_noleggio"].find_one({"id": "no-ord"}))["importo"] == 57.05
        assert _run(db["verbali_noleggio"].find_one({"id": "no-pec"}))["importo"] == 57.05
        v = {"stato": "aperto", "data_notifica": "2026-01-01", "data_notifica_fonte": "pec", "importo_ordinario": "abc"}
        assert _run(applica_importo_ordinario(db, {**v, "id": "x"}, date(2026, 2, 1)))["motivo"] == "ordinario_non_letto"

    def test_all_arrivo_della_pec_oltre_i_5_giorni_l_atteso_passa_subito(self):
        db = _db("atteso-pec")
        notifica = (datetime.now(timezone.utc).date() - timedelta(days=10)).isoformat()
        verbale = _verbale(db, data_notifica=None, data_notifica_fonte=None)
        _run(registra_notifica_pec(db, verbale, {"upec_id": "1", "data_notifica": notifica, "oggetto": "o"}, []))
        v = _run(db["verbali_noleggio"].find_one({"id": "v1"}, {"_id": 0}))
        assert v["data_notifica"] == notifica and v["importo"] == 81.50
        assert v["importo_atteso_fonte"] == FONTE_ORDINARIO
        assert _alert_aperti(db, CODICE_ALERT, "v1") == 1

    def test_il_promemoria_dice_scaduti_i_5_giorni_importo_ordinario(self, monkeypatch):
        import app.services.telegram_notifications as tg

        inviati = []

        async def _manda(msg, *a, **k):
            inviati.append(msg)
            return True

        monkeypatch.setattr(tg, "is_configured", lambda: True)
        monkeypatch.setattr(tg, "send_notification", _manda)
        db = _db("atteso-promemoria")
        _verbale(db)
        _run(aggiorna_importi_attesi(db, oggi=date(2026, 10, 1)))
        _run(db["notification_log"].insert_one({
            "id": "n1", "tipo": "verbale", "verbale_id": "v1", "evento": "sconto_30_scaduto",
            "scheduled_for": "2026-09-26T00:00:00+00:00", "status": "pending"}))
        esito = _run(dispatch_due_verbali_notifications(db))
        assert esito["sent"] == 1
        assert "Scaduti i 5 giorni dalla notifica: importo ordinario 81.50 €" in inviati[0]
        assert "ridotto 57.05 €" in inviati[0]

    def test_l_alert_si_chiude_quando_il_verbale_viene_pagato(self):
        db = _db("atteso-chiusura-alert")
        _verbale(db)
        _run(aggiorna_importi_attesi(db, oggi=date(2026, 10, 1)))
        _run(db["verbali_noleggio"].update_one({"id": "v1"}, {"$set": {"stato": "pagato"}}))
        esito = _run(aggiorna_importi_attesi(db, oggi=date(2026, 10, 2)))
        assert esito["alert_chiusi"] == 1
        assert _alert_aperti(db, CODICE_ALERT, "v1") == 0


# ── 2. Ricevuta pagoPA senza verbale: conservata, alert, mai un verbale creato ──────────

def _parsed_ricevuta(**extra):
    return {
        "is_payment_receipt": True, "document_kind": "RICEVUTA_PAGOPA",
        "identificativo_bolletta": "301000000000012345", "importo": 57.05,
        "numero_verbale": "A26110812778", "targa": "AB123CD",
        "data_pagamento": "2026-04-23", **extra,
    }


class TestRicevutaSenzaVerbale:
    def test_la_ricevuta_non_crea_mai_il_verbale_e_resta_senza_verbale_con_alert(self, monkeypatch):
        db = _db("ricevuta-senza-verbale")
        monkeypatch.setattr(pagopa_receipts, "parse_receipt_pdf", lambda content, filename=None: _parsed_ricevuta())

        esito = _run(pagopa_receipts.import_receipt(db, content=_pdf(["ricevuta"]), filename="r.pdf", company_id="c"))

        assert esito["success"] is True
        assert _run(db["verbali_noleggio"].count_documents({})) == 0          # nessun verbale creato
        ricevuta = _run(db["ricevute_pagopa"].find_one({}, {"_id": 0, "pdf_data": 0}))
        assert ricevuta["stato_verbale"] == "senza_verbale"
        assert ricevuta["riconciliazione_verbale"]["reason"] == "verbale_non_trovato"
        assert "verbale_id" not in ricevuta
        alert = _run(db["alerts"].find_one({"codice": "RICEVUTA_PAGOPA_SENZA_VERBALE"}, {"_id": 0}))
        assert alert["entita_collection"] == "ricevute_pagopa" and alert["entita_id"] == ricevuta["id"]
        assert "A26110812778" in alert["dettaglio"] and "nessun verbale" in alert["dettaglio"]

        # Lo stesso file una seconda volta: un solo record, un solo alert.
        _run(pagopa_receipts.import_receipt(db, content=_pdf(["ricevuta"]), filename="r.pdf", company_id="c"))
        assert _run(db["ricevute_pagopa"].count_documents({})) == 1
        assert _run(db["alerts"].count_documents({"codice": "RICEVUTA_PAGOPA_SENZA_VERBALE"})) == 1

    def test_l_arrivo_del_verbale_aggancia_la_ricevuta_e_chiude_l_alert(self, monkeypatch):
        db = _db("ricevuta-poi-verbale")
        # Il lettore finto vale solo per la ricevuta: il verbale dopo si legge col lettore vero.
        with monkeypatch.context() as m:
            m.setattr(pagopa_receipts, "parse_receipt_pdf", lambda content, filename=None: _parsed_ricevuta())
            _run(pagopa_receipts.import_receipt(db, content=_pdf(["ricevuta"]), filename="r.pdf", company_id="c"))
        ricevuta_id = _run(db["ricevute_pagopa"].find_one({}, {"_id": 0, "id": 1}))["id"]

        _run(db["documents_inbox"].insert_one({"id": "doc-1"}))
        esito = _run(vdi.process_verbale_document(db, document_id="doc-1", content=_pdf(RIGHE_VERBALE), filename="v.pdf"))
        assert esito["status"] == "linked" and esito["ricevute_agganciate"] == {"agganciate": 1, "importo_diverso": 0}

        verbale = _run(db["verbali_noleggio"].find_one({"id": esito["verbale_id"]}, {"_id": 0, "pdf_data": 0}))
        assert verbale["stato"] == "pagato" and verbale["ricevuta_pagopa_id"] == ricevuta_id
        assert verbale["pagato_documentalmente"] is True
        ricevuta = _run(db["ricevute_pagopa"].find_one({"id": ricevuta_id}, {"_id": 0, "pdf_data": 0}))
        assert ricevuta["stato_verbale"] == "agganciata" and ricevuta["verbale_id"] == verbale["id"]
        assert _alert_aperti(db, "RICEVUTA_PAGOPA_SENZA_VERBALE", ricevuta_id) == 0
        assert _run(db["alerts"].find_one({"codice": "RICEVUTA_PAGOPA_SENZA_VERBALE"}))["resolved_by"] == "verbale_arrivato"
        assert _run(db["verbali_noleggio"].count_documents({})) == 1

    def test_importo_diverso_non_aggancia(self, monkeypatch):
        db = _db("ricevuta-importo-diverso")
        with monkeypatch.context() as m:
            m.setattr(pagopa_receipts, "parse_receipt_pdf", lambda content, filename=None: _parsed_ricevuta(importo=81.50))
            _run(pagopa_receipts.import_receipt(db, content=_pdf(["ricevuta"]), filename="r.pdf", company_id="c"))
        _run(db["documents_inbox"].insert_one({"id": "doc-1"}))
        esito = _run(vdi.process_verbale_document(db, document_id="doc-1", content=_pdf(RIGHE_VERBALE), filename="v.pdf"))
        assert esito["ricevute_agganciate"] == {"agganciate": 0, "importo_diverso": 1}
        assert _run(db["ricevute_pagopa"].find_one({}, {"_id": 0, "pdf_data": 0}))["stato_verbale"] == "senza_verbale"
        assert _run(db["verbali_noleggio"].find_one({}, {"_id": 0, "pdf_data": 0}))["stato"] != "pagato"

    def test_ricevuta_dall_inbox_verbali_senza_verbale_ha_lo_stesso_stato_e_alert(self):
        db = _db("ricevuta-inbox")
        righe = [
            "RICEVUTA DI PAGAMENTO PAGOPA",
            "Esito: Pagamento eseguito con successo",
            "Verbale n. A26110812778 targa AB123CD",
            "IUV 301000000000012345",
            "Importo pagato: 57,05 euro",
            "Data pagamento: 23/04/2026",
        ]
        _run(db["documents_inbox"].insert_one({"id": "doc-r"}))
        esito = _run(vdi.process_verbale_document(db, document_id="doc-r", content=_pdf(righe), filename="ricevuta.pdf"))
        assert esito["tipo"] == "ricevuta_pagopa" and esito["status"] == "review", esito
        assert _run(db["verbali_noleggio"].count_documents({})) == 0
        ricevuta = _run(db["ricevute_pagopa"].find_one({"id": esito["receipt_id"]}, {"_id": 0}))
        assert ricevuta["stato_verbale"] == "senza_verbale"
        assert _alert_aperti(db, "RICEVUTA_PAGOPA_SENZA_VERBALE", esito["receipt_id"]) == 1


# ── 3. Assegnazioni con data e ora ───────────────────────────────────────────────────────

VEICOLO_CON_ORA = {
    "targa": "AB123CD", "driver": "Anna", "driver_id": "d-anna",
    "assegnazioni": [
        {"driver": "Mario", "driver_id": "d-mario", "dal": "2026-04-01", "al": "2026-04-10T12:00"},
        {"driver": "Anna", "driver_id": "d-anna", "dal": "2026-04-10T12:00", "al": None},
    ],
}


class TestAssegnazioniConOra:
    def test_il_driver_e_quello_attivo_all_ora_dell_infrazione(self):
        assert driver_alla_data(VEICOLO_CON_ORA, "2026-04-10T09:30")["driver_id"] == "d-mario"
        assert driver_alla_data(VEICOLO_CON_ORA, "2026-04-10T15:25")["driver_id"] == "d-anna"
        assert driver_alla_data(VEICOLO_CON_ORA, "2026-04-11")["driver_id"] == "d-anna"
        assert driver_alla_data(VEICOLO_CON_ORA, "2026-04-05")["driver_id"] == "d-mario"
        assert driver_alla_data(VEICOLO_CON_ORA, "2026-03-31T23:59")["fonte"] == "da_assegnare"

    def test_evento_senza_ora_nel_giorno_del_passaggio_mostra_i_candidati(self):
        esito = driver_alla_data(VEICOLO_CON_ORA, "2026-04-10")
        assert esito["driver"] is None and esito["fonte"] == "da_assegnare"
        assert {c["driver_id"] for c in esito["candidati"]} == {"d-mario", "d-anna"}

    def test_una_riga_senza_ora_vale_il_giorno_intero(self):
        veicolo = {"assegnazioni": [
            {"driver_id": "d-1", "dal": "2026-04-01", "al": "2026-04-10"},
            {"driver_id": "d-2", "dal": "2026-04-11", "al": None},
        ]}
        assert driver_alla_data(veicolo, "2026-04-10T23:30")["driver_id"] == "d-1"
        assert driver_alla_data(veicolo, "2026-04-11T00:00")["driver_id"] == "d-2"
        assert driver_alla_data(veicolo, "2026-04-01T00:00")["driver_id"] == "d-1"
        # Le righe vecchie con il fuso in coda si leggono come prima.
        assert driver_alla_data(veicolo, "2026-04-05T10:00:00+02:00")["driver_id"] == "d-1"

    def test_data_ora_evento_verbale_combina_giorno_e_ora_della_violazione(self):
        assert data_ora_evento_verbale({"data_violazione": "2026-04-10", "ora_violazione": "15:25"}) == ("2026-04-10T15:25", "violazione")
        assert data_ora_evento_verbale({"data_violazione": "2026-04-10"}) == ("2026-04-10", "violazione")
        assert data_ora_evento_verbale({"data_violazione": "2026-04-10", "ora_violazione": "25:99"}) == ("2026-04-10", "violazione")
        # Col ripiego sulla data dell'atto l'ora della violazione non c'entra.
        assert data_ora_evento_verbale({"data_verbale": "2026-07-20", "ora_violazione": "15:25"}) == ("2026-07-20", "data_verbale")

    def test_normalizzazione_degli_istanti(self):
        assert normalizza_istante_assegnazione("2026-04-10") == "2026-04-10"
        assert normalizza_istante_assegnazione("2026-04-10T12:00:00") == "2026-04-10T12:00"
        assert normalizza_istante_assegnazione("2026-04-10 12:30") == "2026-04-10T12:30"
        assert normalizza_istante_assegnazione("10/04/2026") is None
        assert normalizza_istante_assegnazione("2026-04-10T25:00") is None

    def test_il_pdf_con_l_ora_dell_infrazione_sceglie_il_driver_di_quell_ora(self):
        db = _db("pdf-ora")
        _run(db["veicoli_noleggio"].insert_one({"id": "car-1", **VEICOLO_CON_ORA}))
        _run(db["documents_inbox"].insert_one({"id": "doc-1"}))
        esito = _run(vdi.process_verbale_document(db, document_id="doc-1", content=_pdf(RIGHE_VERBALE), filename="v.pdf"))
        verbale = _run(db["verbali_noleggio"].find_one({"id": esito["verbale_id"]}, {"_id": 0, "pdf_data": 0}))
        assert verbale["ora_violazione"] == "15:25"
        assert verbale["driver_id"] == "d-anna" and verbale["driver_match_basis"] == "assegnazione_storica_alla_data"

    def _client(self, monkeypatch, db):
        from app.database import Database
        from app.routers import noleggio as router_noleggio

        monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
        app = FastAPI()
        app.include_router(router_noleggio.router, prefix="/api/noleggio")
        return TestClient(app)

    def test_put_veicolo_accetta_ora_di_inizio_e_fine_e_normalizza(self, monkeypatch):
        db = _db("put-ora")
        _run(db["veicoli_noleggio"].insert_one({"id": "car-1", "targa": "AB123CD", "driver_id": "d-anna", "driver": "Anna"}))
        client = self._client(monkeypatch, db)
        righe = [
            {"driver": "Mario", "driver_id": "d-mario", "dal": "2026-04-01", "al": "2026-04-10T12:00:00"},
            {"driver": "Anna", "driver_id": "d-anna", "dal": "2026-04-10T12:00", "al": ""},
        ]
        assert client.put("/api/noleggio/veicoli/AB123CD", json={"assegnazioni": righe}).status_code == 200
        salvate = _run(db["veicoli_noleggio"].find_one({"targa": "AB123CD"}))["assegnazioni"]
        assert salvate[0]["al"] == "2026-04-10T12:00" and salvate[1]["dal"] == "2026-04-10T12:00"
        assert salvate[1]["al"] is None and salvate[0]["dal"] == "2026-04-01"
        assert driver_alla_data({"assegnazioni": salvate}, "2026-04-10T15:25")["driver_id"] == "d-anna"

    def test_put_veicolo_rifiuta_date_illeggibili_o_rovesciate(self, monkeypatch):
        db = _db("put-400")
        client = self._client(monkeypatch, db)
        base = "/api/noleggio/veicoli/AB123CD"
        assert client.put(base, json={"assegnazioni": [{"driver_id": "d", "dal": "10/04/2026"}]}).status_code == 400
        assert client.put(base, json={"assegnazioni": [{"driver_id": "d", "dal": "2026-04-10T12:00", "al": "2026-04-10T11:00"}]}).status_code == 400
        assert client.put(base, json={"assegnazioni": [{"driver_id": "d"}]}).status_code == 400
        assert client.put(base, json={"assegnazioni": [{"dal": "2026-04-10"}]}).status_code == 400
        assert _run(db["veicoli_noleggio"].count_documents({})) == 0

    def test_cambio_driver_chiude_il_periodo_al_minuto_e_apre_il_nuovo(self, monkeypatch):
        db = _db("put-cambio")
        _run(db["dipendenti"].insert_one({"id": "d-anna", "nome": "Anna", "cognome": "Oggi"}))
        _run(db["veicoli_noleggio"].insert_one({
            "id": "car-1", "targa": "AB123CD", "driver_id": "d-mario", "driver": "Mario",
            "assegnazioni": [{"driver_id": "d-mario", "driver": "Mario", "dal": "2026-01-01", "al": None}]}))
        client = self._client(monkeypatch, db)
        assert client.put("/api/noleggio/veicoli/AB123CD", json={"driver_id": "d-anna"}).status_code == 200
        storico = _run(db["veicoli_noleggio"].find_one({"targa": "AB123CD"}))["assegnazioni"]
        assert len(storico) == 2
        assert len(storico[0]["al"]) == 16 and storico[0]["al"][10] == "T"      # istante, non giorno
        assert storico[1]["dal"] == storico[0]["al"] and storico[1]["driver_id"] == "d-anna"
        assert driver_alla_data({"assegnazioni": storico}, "2026-02-01T10:00")["driver_id"] == "d-mario"


# ── 4. Trattenuta solo a verbale pagato con quietanza ──────────────────────────────────

class TestTrattenutaSoloConQuietanza:
    def test_l_assegnazione_del_driver_non_apre_nessuna_trattenuta(self, monkeypatch):
        db = _db("tratt-assegnazione")
        _run(db["dipendenti"].insert_one({"id": "d-anna", "nome": "Anna", "cognome": "Oggi"}))
        _run(db["veicoli_noleggio"].insert_one({"id": "car-1", "targa": "AB123CD"}))
        _verbale(db, driver_id=None, driver=None)
        client = TestAssegnazioniConOra()._client(monkeypatch, db)
        assert client.put("/api/noleggio/veicoli/AB123CD", json={"driver_id": "d-anna"}).status_code == 200
        _run(db["verbali_noleggio"].update_one({"id": "v1"}, {"$set": {"driver_id": "d-anna", "driver": "Anna Oggi"}}))
        assert _run(db["trattenute_dipendenti"].count_documents({})) == 0
        assert _run(db["note_presenze_consulente"].count_documents({})) == 0
        esito = _run(proponi_trattenuta_verbale_pagato(
            db, _run(db["verbali_noleggio"].find_one({"id": "v1"})), importo_pagato="57.05",
            data_pagamento="2026-04-23", fonte="test"))
        assert esito["motivo"] == "verbale_non_pagato_con_quietanza"
        assert _run(db["trattenute_dipendenti"].count_documents({})) == 0

    def test_pagamento_dichiarato_senza_quietanza_non_apre_la_trattenuta(self):
        db = _db("tratt-attesa-quietanza")
        verbale = _verbale(db, stato="pagato_attesa_quietanza", pagato_documentalmente=False, importo_pagato="57.05")
        esito = _run(proponi_trattenuta_verbale_pagato(db, verbale, importo_pagato="57.05", data_pagamento="2026-04-23", fonte="test"))
        assert esito["motivo"] == "verbale_non_pagato_con_quietanza"
        assert _run(db["trattenute_dipendenti"].count_documents({})) == 0

    def test_con_la_quietanza_nasce_la_proposta_da_confermare_una_sola_volta(self):
        db = _db("tratt-quietanza")
        verbale = _verbale(db, stato="pagato", pagato_documentalmente=True, quietanza_ricevuta=True)
        primo = _run(proponi_trattenuta_verbale_pagato(db, verbale, importo_pagato="57.05", data_pagamento="2026-04-23", fonte="test"))
        secondo = _run(proponi_trattenuta_verbale_pagato(db, verbale, importo_pagato="57.05", data_pagamento="2026-04-23", fonte="test"))
        assert primo["trattenuta_creata"] and primo["nota_creata"]
        assert not secondo["trattenuta_creata"] and secondo["motivo"] == "proposta_gia_presente"
        trattenute = _run(db["trattenute_dipendenti"].find({}).to_list(10))
        assert len(trattenute) == 1 and trattenute[0]["stato"] == "proposta"      # la conferma e' del titolare
        assert trattenute[0]["importo_da_recuperare"] == 57.05 and trattenute[0]["verbale_id"] == "v1"
        assert _run(db["note_presenze_consulente"].count_documents({})) == 1

    def test_la_ricevuta_pagopa_e_una_quietanza_e_apre_la_proposta(self):
        db = _db("tratt-ricevuta")
        _verbale(db)
        ok = _run(applica_pagamento_a_verbale(db, "v1", {
            "fonte": "ricevuta_pagopa", "importo": 57.05, "data_pagamento": "2026-04-23",
            "metodo_pagamento": "PagoPA", "ricevuta_pagopa_id": "r1", "iuv_usato": "3010"}))
        assert ok is True
        assert _run(db["verbali_noleggio"].find_one({"id": "v1"}))["stato"] == "pagato"
        assert _run(db["trattenute_dipendenti"].count_documents({"verbale_id": "v1", "stato": "proposta"})) == 1

    def test_la_sola_prova_bancaria_non_apre_la_proposta(self):
        db = _db("tratt-banca")
        _verbale(db)
        ok = _run(applica_pagamento_a_verbale(db, "v1", {
            "fonte": "banca", "importo": 57.05, "data_pagamento": "2026-04-23", "movimento_id": "m1"}))
        assert ok is True
        assert _run(db["verbali_noleggio"].find_one({"id": "v1"}))["stato"] == "pagato_attesa_quietanza"
        assert _run(db["trattenute_dipendenti"].count_documents({})) == 0

    def test_upload_quietanza_senza_pdf_non_apre_la_trattenuta(self, monkeypatch):
        from app.database import Database
        from app.routers import verbali_noleggio_api as api
        from app.utils.dependencies import get_current_admin_user

        db = _db("tratt-upload-senza-pdf")
        _verbale(db, stato="aperto")
        monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
        app = FastAPI()
        app.include_router(api.router, prefix="/api/verbali-noleggio")
        app.dependency_overrides[get_current_admin_user] = lambda: {"sub": "a", "role": "admin"}
        client = TestClient(app)
        url = "/api/verbali-noleggio/v1/upload-quietanza"
        assert client.post(url, json={"importo_pagato": "57,05", "data_pagamento": "23/04/2026"}).status_code == 200
        assert _run(db["verbali_noleggio"].find_one({"id": "v1"}))["stato"] == "pagato_attesa_quietanza"
        assert _run(db["trattenute_dipendenti"].count_documents({})) == 0
        assert _run(db["note_presenze_consulente"].count_documents({})) == 0
        pdf = base64.b64encode(_pdf(["Quietanza", "Importo 57,05"])).decode()
        assert client.post(url, json={"importo_pagato": "57,05", "data_pagamento": "23/04/2026", "pdf_base64": pdf}).status_code == 200
        assert _run(db["trattenute_dipendenti"].count_documents({"stato": "proposta"})) == 1


# ── Extra: le PEC di notifica si agganciano da sole nel giro delle 07:10 ─────────────────

class TestGiroAutomaticoPec:
    OGGETTO = "POSTA CERTIFICATA: Notifica di atto amministrativo Atto {atto} del 15/03/2026 [upec{upec}]"
    MITTENTE = '"Per conto di: notifica.pl.napoli@pec.it" <posta-certificata@pec.aruba.it>'
    DATA = "Thu, 18 Jun 2026 17:22:30 +0200"

    def _db(self, monkeypatch):
        from app.services.notifiche_pec_verbali import giro_aggancio_automatico

        db = _db("pec-giro-automatico")
        testi = {
            b"pec-con-verbale": "Verbale n. A26110812778 - cronologico Registro n. 1 data verbale 15/03/2026",
            b"pec-senza-verbale": "Verbale n. A26199999999 - cronologico Registro n. 2 data verbale 15/03/2026",
        }
        monkeypatch.setattr("app.services.verbali_document_import._extract_text", lambda c: testi[c])
        for upec, contenuto in (("111", b"pec-con-verbale"), ("222", b"pec-senza-verbale")):
            _run(db["verbali_email_attachments"].insert_one({
                "id": f"att-{upec}", "filename": f"COPIACONFORMEPEC_{upec}.pdf", "pdf_hash": f"h{upec}",
                "pdf_data": base64.b64encode(contenuto).decode(),
                "email_subject": self.OGGETTO.format(atto=upec, upec=upec),
                "email_from": self.MITTENTE, "email_date": self.DATA}))
        _verbale(db, data_notifica=None, data_notifica_fonte=None)       # il verbale vero A26110812778
        return db, giro_aggancio_automatico

    def test_due_pec_una_agganciata_una_senza_verbale_stato_scritto_e_secondo_giro_zero(self, monkeypatch):
        db, giro = self._db(monkeypatch)

        primo = _run(giro(db))
        assert (primo["totali"], primo["agganciate"], primo["senza_verbale"], primo["ambigue"]) == (2, 1, 1, 0)
        stato = _run(db["sistema_stato"].find_one({"chiave": "notifiche_pec_verbali_ultimo_giro"}, {"_id": 0}))
        assert stato["agganciate"] == 1 and stato["senza_verbale"] == 1 and stato["totali"] == 2
        assert stato["elenco_da_agganciare"] == [{"upec_id": "222", "numero_verbale": "A26199999999", "motivo": "senza_verbale"}]
        verbale = _run(db["verbali_noleggio"].find_one({"id": "v1"}, {"_id": 0}))
        assert verbale["data_notifica"] == "2026-06-18" and verbale["data_notifica_fonte"] == "pec"
        assert _run(db["verbali_email_attachments"].find_one({"id": "att-111"}))["notifica_stato"] == "agganciata"
        assert _run(db["verbali_email_attachments"].find_one({"id": "att-222"}))["notifica_stato"] == "da_agganciare"
        assert _run(db["verbali_noleggio"].count_documents({})) == 1                  # nessun verbale creato

        secondo = _run(giro(db))
        assert secondo["agganciate"] == 0 and secondo["gia_agganciate"] == 1 and secondo["senza_verbale"] == 1
        assert len(_run(db["verbali_noleggio"].find_one({"id": "v1"}))["notifiche_pec"]) == 1
        stato = _run(db["sistema_stato"].find_one({"chiave": "notifiche_pec_verbali_ultimo_giro"}, {"_id": 0}))
        assert stato["agganciate"] == 0 and stato["gia_agganciate"] == 1
        assert _run(db["sistema_stato"].count_documents({})) == 1

    def test_due_verbali_veri_con_lo_stesso_numero_sono_ambigui_e_nessuno_riceve_la_pec(self, monkeypatch):
        db, giro = self._db(monkeypatch)
        _verbale(db, id="v2", data_notifica=None, data_notifica_fonte=None)
        esito = _run(giro(db))
        assert esito["agganciate"] == 0 and esito["ambigue"] == 1 and esito["senza_verbale"] == 1
        assert _run(db["verbali_noleggio"].find_one({"id": "v1"})).get("notifiche_pec") is None
        assert _run(db["verbali_email_attachments"].find_one({"id": "att-111"}))["notifica_motivo"] == "verbali_ambigui"
