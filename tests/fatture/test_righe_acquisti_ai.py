import asyncio
import json

import pytest

from app.routers.righe_acquisti import costruisci_righe
from app.services import agenti_proposte as ap
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
        "id": "fatt-1:1", "stato": "proposta", "proposta": {"natura": "cespite"},
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
