"""Proposte AI: client finto, tetto, cache per impronta, proposta scritta mai applicata,
conferma col motore una volta sola, rifiuto a chip, spento o senza chiave."""
import asyncio
import hashlib
import json

import pytest

from app.services import agenti_proposte as ap
from app.services.archivio_documenti_memoria import ArchivioDocumenti

PDF_A = b"%PDF-1.4 quietanza"
PDF_B = b"%PDF-1.4 verbale"


class ClientFinto:
    """Risponde col JSON scelto per nome di file e conta le chiamate."""

    def __init__(self, risposte):
        self.risposte = risposte
        self.chiamate = []

    async def send_message_con_usage(self, message):
        nome = message.content.split("«")[1].split("»")[0]
        self.chiamate.append(nome)
        testo = self.risposte.get(nome)
        if isinstance(testo, Exception):
            raise testo
        return {"testo": testo, "usage": {"input_tokens": 1500, "output_tokens": 120},
                "modello": "finto-1", "tentativi": 1}


def _risposta(tipo, **campi):
    return json.dumps({"tipo_documento": tipo, "campi": campi, "confidenza": "alta",
                       "prove": ["QUIETANZA DI PAGAMENTO"], "motivo": "intestazione"})


@pytest.fixture
def ambiente(monkeypatch):
    db = ArchivioDocumenti()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chiave-di-prova")
    monkeypatch.delenv("AGENTI_AI", raising=False)
    monkeypatch.delenv("AGENTI_AI_TETTO_GIORNALIERO", raising=False)
    byte = {"DRV-A": PDF_A, "DRV-B": PDF_B, "DRV-A2": PDF_A}

    async def scarica(file_id, md5=None):
        return byte[file_id]

    import app.services.drive_download as dd

    monkeypatch.setattr(dd, "scarica_originale", scarica)

    async def prepara():
        await db["drive_cartella_unica"].insert_many([
            {"id": "DRV-A", "nome": "quietanza.pdf", "cartella": "ERRORI", "tipo": "f24",
             "motivo": "F24 non quadrato", "aggiornato_il": "2026-10-01T10:00:00"},
            {"id": "DRV-B", "nome": "verbale.pdf", "cartella": "ERRORI", "tipo": "non_riconosciuto",
             "motivo": "tipo di documento non riconosciuto", "aggiornato_il": "2026-10-01T09:00:00"},
            {"id": "DRV-OK", "nome": "fattura.xml", "cartella": "ELABORATE", "tipo": "fattura"},
            {"id": "DRV-DOC", "nome": "contratto.docx", "cartella": "ERRORI", "tipo": "non_riconosciuto"},
        ])
    asyncio.run(prepara())
    return db


def test_giro_scrive_proposte_e_usage_senza_applicare(ambiente):
    db = ambiente
    client = ClientFinto({
        "quietanza.pdf": _risposta("quietanza_f24", data="2026-03-16", importo_cents="1.234,56", codici_tributo=[6002]),
        "verbale.pdf": "```json\n" + json.dumps({"tipo_documento": "fantasia", "confidenza": "alta"}) + "\n```",
    })
    esito = asyncio.run(ap.giro(db, client=client))
    assert esito["candidati"] == 2 and esito["proposte"] == 2 and esito["chiamate"] == 2
    assert client.chiamate == ["quietanza.pdf", "verbale.pdf"]  # il .docx non si legge

    righe = asyncio.run(db["agenti_proposte"].find({}, {"_id": 0}).to_list(None))
    per_nome = {r["documento"]["nome"]: r for r in righe}
    q = per_nome["quietanza.pdf"]
    assert q["stato"] == "proposta" and q["settore"] == "f24" and q["confidenza"] == "alta"
    assert q["documento"] == {"origine": "drive", "drive_id": "DRV-A", "inbox_id": None, "nome": "quietanza.pdf",
                              "sha256": hashlib.sha256(PDF_A).hexdigest(), "tipo_tentato": "f24",
                              "motivo_fermo": "F24 non quadrato"}
    assert q["proposta"]["campi"] == {"data": "2026-03-16", "importo_cents": 123456, "codici_tributo": ["6002"]}
    assert q["usage"] == {"input_tokens": 1500, "output_tokens": 120} and q["modello"] == "finto-1"
    # tipo fuori dallo smistatore: non riconosciuto, confidenza bassa, settore altro
    v = per_nome["verbale.pdf"]
    assert v["proposta"]["tipo_documento"] == "non_riconosciuto" and v["confidenza"] == "bassa" and v["settore"] == "altro"
    # il registro della cartella unica non e' stato toccato: nessuna applicazione
    riga = asyncio.run(db["drive_cartella_unica"].find_one({"id": "DRV-A"}, {"_id": 0}))
    assert riga["cartella"] == "ERRORI"
    chiamate = asyncio.run(db["agenti_ai_chiamate"].find({}, {"_id": 0}).to_list(None))
    assert len(chiamate) == 2 and all(c["giorno"] == ap.oggi_roma() and c["esito"] == "ok" for c in chiamate)
    stato = asyncio.run(ap.stato(db))
    assert stato["chiamate_oggi"] == 2 and stato["ultimo_giro"] == esito["eseguito_at"]

    # secondo giro: niente di nuovo da proporre e nessuna chiamata
    esito2 = asyncio.run(ap.giro(db, client=client))
    assert esito2["candidati"] == 0 and len(client.chiamate) == 2


def test_tetto_giornaliero_e_cache_per_impronta(ambiente, monkeypatch):
    db = ambiente
    monkeypatch.setenv("AGENTI_AI_TETTO_GIORNALIERO", "1")
    client = ClientFinto({"quietanza.pdf": _risposta("quietanza_f24"), "verbale.pdf": _risposta("verbale_codice_strada")})
    esito = asyncio.run(ap.giro(db, client=client))
    assert esito["chiamate"] == 1 and esito["proposte"] == 1 and esito["saltati_tetto"] == 1
    assert "tetto giornaliero" in esito["motivo"]

    # una copia byte-identica di un file gia' letto: proposta dalla cache, senza chiamata ne' tetto
    asyncio.run(db["drive_cartella_unica"].insert_one(
        {"id": "DRV-A2", "nome": "quietanza (2).pdf", "cartella": "ERRORI", "tipo": "f24", "aggiornato_il": "2026-10-02"}))
    esito2 = asyncio.run(ap.giro(db, client=client))
    assert esito2["da_cache"] == 1 and esito2["chiamate"] == 0
    copia = asyncio.run(db["agenti_proposte"].find_one({"documento.drive_id": "DRV-A2"}, {"_id": 0}))
    assert copia["proposta"]["tipo_documento"] == "quietanza_f24" and copia["modello"] is None


def test_errore_del_modello_non_scrive_proposta(ambiente):
    db = ambiente
    client = ClientFinto({"quietanza.pdf": RuntimeError("timeout"), "verbale.pdf": _risposta("verbale_codice_strada")})
    esito = asyncio.run(ap.giro(db, client=client))
    assert esito["errori"] == 1 and esito["proposte"] == 1 and "timeout" in esito["ultimo_errore"]
    chiamate = asyncio.run(db["agenti_ai_chiamate"].find({"esito": "errore"}, {"_id": 0}).to_list(None))
    assert len(chiamate) == 1 and chiamate[0]["sha256"] == hashlib.sha256(PDF_A).hexdigest()
    assert asyncio.run(db["agenti_proposte"].count_documents({"documento.drive_id": "DRV-A"})) == 0


def test_spento_o_senza_chiave_non_legge_e_lo_dice(ambiente, monkeypatch):
    db = ambiente
    client = ClientFinto({"quietanza.pdf": _risposta("quietanza_f24")})
    monkeypatch.setenv("AGENTI_AI", "false")
    esito = asyncio.run(ap.giro(db, client=client))
    assert esito["motivo"].startswith("spento") and client.chiamate == []
    assert asyncio.run(ap.stato(db))["attivo"] is False

    monkeypatch.delenv("AGENTI_AI")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    esito = asyncio.run(ap.giro(db))
    assert esito["motivo"] == "ANTHROPIC_API_KEY non configurata"
    assert asyncio.run(ap.stato(db))["chiave_presente"] is False
    assert asyncio.run(db["agenti_proposte"].count_documents({})) == 0


def test_conferma_applica_col_motore_una_volta_sola(ambiente, monkeypatch):
    db = ambiente
    client = ClientFinto({"quietanza.pdf": _risposta("quietanza_f24"), "verbale.pdf": _risposta("verbale_codice_strada")})
    asyncio.run(ap.giro(db, client=client))
    proposta = asyncio.run(db["agenti_proposte"].find_one({"documento.drive_id": "DRV-A"}, {"_id": 0}))

    applicazioni = []

    async def rielabora(db_, drive_id, tipo, *, deciso_da):
        applicazioni.append((drive_id, tipo, deciso_da))
        return {"success": True, "cartella": "ELABORATE", "motivo": None, "tipo_rilevato": tipo,
                "duplicate": False, "message": "ok", "riferimenti": {"quietanza_id": "Q1"}}

    import app.services.drive_cartella_unica as cu

    monkeypatch.setattr(cu, "rielabora_con_tipo", rielabora)

    r = asyncio.run(ap.conferma(db, proposta["id"], "titolare@test"))
    assert r["gia_decisa"] is False and r["esito"]["success"] is True
    assert applicazioni == [("DRV-A", "quietanza_f24", "titolare@test")]
    dopo = asyncio.run(db["agenti_proposte"].find_one({"id": proposta["id"]}, {"_id": 0}))
    assert dopo["stato"] == "confermata" and dopo["deciso_da"] == "titolare@test" and dopo["deciso_il"]
    assert dopo["esito_applicazione"]["riferimenti"] == {"quietanza_id": "Q1"}
    audit = asyncio.run(db["audit_log"].find({"entita_id": proposta["id"]}, {"_id": 0}).to_list(None))
    assert len(audit) == 1 and audit[0]["azione"] == "proposta_confermata"

    # seconda conferma: non si riapplica
    r2 = asyncio.run(ap.conferma(db, proposta["id"], "titolare@test"))
    assert r2["gia_decisa"] is True and applicazioni == [("DRV-A", "quietanza_f24", "titolare@test")]
    # «conferma tutte le sicure» salta la gia' decisa e applica l'altra
    r3 = asyncio.run(ap.conferma_sicure(db, "titolare@test"))
    assert r3["candidate"] == 1 and r3["confermate"] == 1
    assert applicazioni[-1] == ("DRV-B", "verbale_codice_strada", "titolare@test")


def test_conferma_fallita_lascia_la_proposta_aperta(ambiente, monkeypatch):
    db = ambiente
    client = ClientFinto({"quietanza.pdf": _risposta("quietanza_f24"), "verbale.pdf": _risposta("verbale_codice_strada")})
    asyncio.run(ap.giro(db, client=client))
    proposta = asyncio.run(db["agenti_proposte"].find_one({"documento.drive_id": "DRV-A"}, {"_id": 0}))

    async def rielabora(db_, drive_id, tipo, *, deciso_da):
        return {"success": False, "cartella": "ERRORI", "motivo": "F24 non quadrato: saldo 10,00 righe 9,00"}

    import app.services.drive_cartella_unica as cu

    monkeypatch.setattr(cu, "rielabora_con_tipo", rielabora)
    r = asyncio.run(ap.conferma(db, proposta["id"], "titolare@test"))
    assert r["esito"]["success"] is False
    dopo = asyncio.run(db["agenti_proposte"].find_one({"id": proposta["id"]}, {"_id": 0}))
    assert dopo["stato"] == "proposta" and dopo["esito_applicazione"]["motivo"].startswith("F24 non quadrato")
    with pytest.raises(ap.PropostaNonTrovata):
        asyncio.run(ap.conferma(db, "prop_inesistente", "x"))


def test_rifiuto_a_chip(ambiente):
    db = ambiente
    client = ClientFinto({"quietanza.pdf": _risposta("quietanza_f24"), "verbale.pdf": _risposta("verbale_codice_strada")})
    asyncio.run(ap.giro(db, client=client))
    proposta = asyncio.run(db["agenti_proposte"].find_one({"documento.drive_id": "DRV-B"}, {"_id": 0}))
    with pytest.raises(ap.PropostaNonApplicabile):
        asyncio.run(ap.rifiuta(db, proposta["id"], "t", "perche' si"))
    r = asyncio.run(ap.rifiuta(db, proposta["id"], "t", "doppione"))
    assert r["proposta"]["stato"] == "rifiutata" and r["proposta"]["rifiuto"] == {"motivo": "doppione", "nota": ""}
    r2 = asyncio.run(ap.rifiuta(db, proposta["id"], "t", "altro", "cambio idea"))
    assert r2["gia_decisa"] is True and r2["proposta"]["rifiuto"]["motivo"] == "doppione"
    assert asyncio.run(ap.elenco(db)) == [p for p in asyncio.run(ap.elenco(db)) if p["stato"] == "proposta"]
    assert asyncio.run(ap.conteggio_in_attesa(db)) == {"f24": 1}


def test_inbox_senza_categoria_si_legge_e_la_conferma_classifica(ambiente, monkeypatch):
    import base64

    db = ambiente
    asyncio.run(db["documents_inbox"].insert_many([
        {"id": "upload_1", "filename": "scansione.pdf", "pdf_data": base64.b64encode(b"%PDF scan").decode(),
         "downloaded_at": "2026-10-01"},
        {"id": "upload_2", "filename": "noto.pdf", "categoria": "f24", "pdf_data": "x"},
    ]))
    client = ClientFinto({"quietanza.pdf": _risposta("quietanza_f24"), "verbale.pdf": _risposta("verbale_codice_strada"),
                          "scansione.pdf": _risposta("cedolino", dipendente="ROSSI MARIO", periodo="2026-08")})
    esito = asyncio.run(ap.giro(db, client=client))
    assert esito["proposte"] == 3
    p = asyncio.run(db["agenti_proposte"].find_one({"documento.inbox_id": "upload_1"}, {"_id": 0}))
    assert p["settore"] == "cedolini" and p["documento"]["sha256"] == hashlib.sha256(b"%PDF scan").hexdigest()

    ricevuti = []

    async def smistatore(file):
        ricevuti.append((file.filename, file.tipo_rilevato_noto, await file.read(), file.source_context["inbox_id"]))
        return {"success": True, "tipo_rilevato": "cedolino", "message": "busta registrata"}

    import app.routers.documenti as documenti

    monkeypatch.setattr(documenti, "upload_documento_automatico", smistatore)
    r = asyncio.run(ap.conferma(db, p["id"], "titolare@test"))
    assert r["esito"]["success"] is True
    assert ricevuti == [("scansione.pdf", "cedolino", b"%PDF scan", "upload_1")]
    riga = asyncio.run(db["documents_inbox"].find_one({"id": "upload_1"}, {"_id": 0}))
    assert riga["categoria"] == "cedolino" and riga["processed"] is True and riga["agente_proposta_id"] == p["id"]
