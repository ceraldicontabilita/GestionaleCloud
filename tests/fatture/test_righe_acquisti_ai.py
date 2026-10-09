import asyncio
import json

import pytest

from app.routers.righe_acquisti import costruisci_righe
from app.services import agenti_proposte as ap
from app.services import audit_logger
from app.services.archivio_documenti_memoria import ArchivioDocumenti


class ClientRigheFinto:
    def __init__(self):
        self.chiamate = 0

    async def send_message_con_usage(self, message):
        self.chiamate += 1
        ricevute = json.loads(message.content.split("\n", 1)[1])
        risposta = [{
            "id": riga["id"], "natura": "utensile", "categoria": "utensili cucina",
            "conto": "05.01.06", "centro_costo": "produzione", "destinazione_operativa": "pasticceria",
            "confidenza": 0.91, "spiegazione": "Descrizione inequivocabile della singola riga.",
            "regola": "P.IVA e codice articolo esatti",
        } for riga in ricevute]
        return {"testo": json.dumps(risposta), "modello": "finto", "usage": {}, "tentativi": 1}


def _fattura(descrizione="Pentola a pressione"):
    return {
        "id": "fatt-1", "invoice_number": "A-1", "invoice_date": "2026-10-03",
        "supplier_name": "Fornitore", "supplier_vat": "IT12345678901", "content_hash": "a" * 64,
        "linee": [{
            "numero_linea": "1", "descrizione": descrizione,
            "codici_articolo": [{"tipo": "SKU", "valore": "PENT-01"}],
            "quantita": "1", "unita_misura": "PZ", "prezzo_totale": "67.71", "aliquota_iva": "22",
        }],
    }


def test_proposta_per_riga_e_idempotente_finche_la_riga_non_cambia():
    db = ArchivioDocumenti()
    client = ClientRigheFinto()
    asyncio.run(db["invoices"].insert_one(_fattura()))

    primo = asyncio.run(ap.giro_righe_acquisti(db, client=client))
    assert primo["candidate"] == 1 and primo["proposte"] == 1 and primo["chiamate"] == 1
    assert client.chiamate == 1

    secondo = asyncio.run(ap.giro_righe_acquisti(db, client=client))
    assert secondo["candidate"] == 0 and secondo["proposte"] == 0
    assert client.chiamate == 1

    righe = costruisci_righe([_fattura()])
    record = asyncio.run(ap.classificazioni_righe(db, [righe[0]["id"]]))
    ap.sovrapponi_classificazioni(righe, record)
    assert righe[0]["classificazione"]["stato"] == "PROPOSTA"
    assert righe[0]["classificazione"]["natura"] == "utensile"


def test_decisione_umana_conserva_prima_dopo_autore_e_motivazione():
    db = ArchivioDocumenti()
    client = ClientRigheFinto()
    asyncio.run(db["invoices"].insert_one(_fattura()))
    asyncio.run(ap.giro_righe_acquisti(db, client=client))

    deciso = asyncio.run(ap.decidi_riga_acquisto(
        db, "fatt-1:1", "titolare", azione="correggi", motivazione="Uso documentato in laboratorio",
        correzione={
            "natura": "attrezzatura", "categoria": "attrezzature cucina", "conto": "05.01.06",
            "centro_costo": "produzione", "destinazione_operativa": "pasticceria", "confidenza": 1,
            "spiegazione": "Verificata dal titolare", "regola": "SKU PENT-01",
        },
    ))
    assert deciso["stato"] == "confermata"
    assert deciso["classificazione_confermata"]["natura"] == "attrezzatura"
    assert deciso["motivazione"] == "Uso documentato in laboratorio"

    audit = asyncio.run(db["audit_log"].find_one({"entita_id": "fatt-1:1"}, {"_id": 0}))
    assert audit["utente"] == "titolare"
    assert audit["vecchio_stato"]["stato"] == "proposta"
    assert audit["nuovo_stato"]["stato"] == "confermata"


def test_cespite_non_si_conferma_senza_regola_fiscale_esplicita():
    db = ArchivioDocumenti()
    fattura = _fattura()
    riga = costruisci_righe([fattura])[0]
    asyncio.run(db["invoices"].insert_one(fattura))
    asyncio.run(db[ap.COLL_RIGHE_ACQUISTI].insert_one({
        "id": "fatt-1:1", "fattura_id": "fatt-1", "stato": "proposta", "proposta": {"natura": "cespite"},
        "impronta_riga": ap.impronta_riga(riga),
    }))
    with pytest.raises(ap.PropostaNonApplicabile, match="regola fiscale"):
        asyncio.run(ap.decidi_riga_acquisto(
            db, "fatt-1:1", "titolare", azione="conferma", motivazione="Da verificare come cespite",
        ))


def test_una_proposta_vecchia_non_puo_essere_confermata_dopo_la_modifica_della_riga():
    db = ArchivioDocumenti()
    client = ClientRigheFinto()
    asyncio.run(db["invoices"].insert_one(_fattura()))
    asyncio.run(ap.giro_righe_acquisti(db, client=client))
    asyncio.run(db["invoices"].update_one(
        {"id": "fatt-1"}, {"$set": {"linee": _fattura("Pentola modificata")["linee"]}},
    ))

    with pytest.raises(ap.PropostaNonApplicabile, match="riga e' cambiata"):
        asyncio.run(ap.decidi_riga_acquisto(
            db, "fatt-1:1", "titolare", azione="conferma", motivazione="Confermo",
        ))


def test_due_decisioni_concorrenti_non_si_sovrascrivono():
    db = ArchivioDocumenti()
    client = ClientRigheFinto()
    asyncio.run(db["invoices"].insert_one(_fattura()))
    asyncio.run(ap.giro_righe_acquisti(db, client=client))

    async def decidi_due_volte():
        risultati = await asyncio.gather(
            ap.decidi_riga_acquisto(
                db, "fatt-1:1", "primo", azione="conferma", motivazione="Prima decisione",
            ),
            ap.decidi_riga_acquisto(
                db, "fatt-1:1", "secondo", azione="rifiuta", motivazione="Seconda decisione",
            ),
            return_exceptions=True,
        )
        return risultati

    risultati = asyncio.run(decidi_due_volte())
    assert sum(isinstance(r, dict) for r in risultati) == 1
    assert sum(isinstance(r, ap.PropostaNonApplicabile) for r in risultati) == 1


def test_decisione_conserva_audit_nel_record_anche_se_log_esterno_fallisce(monkeypatch):
    db = ArchivioDocumenti()
    client = ClientRigheFinto()
    asyncio.run(db["invoices"].insert_one(_fattura()))
    asyncio.run(ap.giro_righe_acquisti(db, client=client))

    async def audit_non_disponibile(**_kwargs):
        raise RuntimeError("audit non disponibile")

    monkeypatch.setattr(audit_logger, "log_evento", audit_non_disponibile)
    deciso = asyncio.run(ap.decidi_riga_acquisto(
        db, "fatt-1:1", "titolare", azione="conferma", motivazione="Conferma verificata",
    ))

    assert deciso["audit_decisione"]["utente"] == "titolare"
    assert deciso["audit_decisione"]["prima"]["stato"] == "proposta"
    assert deciso["audit_decisione"]["dopo"]["stato"] == "confermata"


def test_tetto_agenti_include_le_chiamate_documentali_prima_delle_righe(monkeypatch):
    db = ArchivioDocumenti()
    client = ClientRigheFinto()
    asyncio.run(db["invoices"].insert_one(_fattura()))
    asyncio.run(db[ap.COLL_CHIAMATE].insert_many([
        {"id": f"call-{i}", "giorno": ap.oggi_roma(), "scopo": ap.SCOPO, "esito": "ok"}
        for i in range(ap.TETTO_DEFAULT)
    ]))
    monkeypatch.setenv("AGENTI_AI_TETTO_GIORNALIERO", str(ap.TETTO_DEFAULT))

    esito = asyncio.run(ap.giro_righe_acquisti(db, client=client))

    assert client.chiamate == 0
    assert esito["saltati_tetto"] == 1


def test_regole_umane_in_conflitto_non_generano_riuso_ne_chiamata_ai():
    db = ArchivioDocumenti()
    client = ClientRigheFinto()
    fattura = _fattura()
    riga = costruisci_righe([fattura])[0]
    identita = ap.identita_regola_riga(riga)
    asyncio.run(db["invoices"].insert_one(fattura))
    asyncio.run(db[ap.COLL_RIGHE_ACQUISTI].insert_many([
        {
            "id": "vecchia-1:1", "stato": ap.STATO_CONFERMATA, "identita_regola": identita,
            "classificazione_confermata": {"natura": "utensile", "categoria": "cucina"},
        },
        {
            "id": "vecchia-2:1", "stato": ap.STATO_CONFERMATA, "identita_regola": identita,
            "classificazione_confermata": {"natura": "attrezzatura", "categoria": "cucina"},
        },
    ]))

    esito = asyncio.run(ap.giro_righe_acquisti(db, client=client))

    assert client.chiamate == 0
    assert esito["conflitti_regole"] == 1
    assert asyncio.run(db[ap.COLL_RIGHE_ACQUISTI].find_one({"id": "fatt-1:1"})) is None


def test_correzione_umana_rifiuta_una_natura_non_ammessa():
    db = ArchivioDocumenti()
    client = ClientRigheFinto()
    asyncio.run(db["invoices"].insert_one(_fattura()))
    asyncio.run(ap.giro_righe_acquisti(db, client=client))

    with pytest.raises(ap.PropostaNonApplicabile, match="natura non ammessa"):
        asyncio.run(ap.decidi_riga_acquisto(
            db, "fatt-1:1", "titolare", azione="correggi", motivazione="Correzione manuale",
            correzione={"natura": "attrezzatura_typo"},
        ))


def test_decisione_legge_solo_la_fattura_del_record():
    db = ArchivioDocumenti()
    client = ClientRigheFinto()
    asyncio.run(db["invoices"].insert_one(_fattura()))
    asyncio.run(ap.giro_righe_acquisti(db, client=client))
    originale = db["invoices"]

    class SoloFindOne:
        async def find_one(self, *args, **kwargs):
            return await originale.find_one(*args, **kwargs)

        def find(self, *_args, **_kwargs):
            raise AssertionError("una decisione non deve scansionare tutte le fatture")

    db._tables["invoices"] = SoloFindOne()
    deciso = asyncio.run(ap.decidi_riga_acquisto(
        db, "fatt-1:1", "titolare", azione="conferma", motivazione="Conferma verificata",
    ))
    assert deciso["stato"] == ap.STATO_CONFERMATA
