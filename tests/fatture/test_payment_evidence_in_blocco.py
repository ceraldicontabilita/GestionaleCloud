"""Le prove di pagamento dell'archivio Fatture si leggono in blocco, con lo stesso esito."""
import asyncio

from app.services.archivio_documenti_memoria import ArchivioDocumenti
from app.services.payment_evidence_projection import (
    project_invoice_payment_evidence,
    project_payment_evidence_many,
)


class _Contatore:
    """Avvolge l'archivio in memoria e conta le letture per collezione."""

    def __init__(self, db):
        self._db = db
        self.letture = {}

    def __getitem__(self, nome):
        collezione = self._db[nome]
        contatore = self

        class _Vista:
            def find(self, *a, **k):
                contatore.letture[nome] = contatore.letture.get(nome, 0) + 1
                return collezione.find(*a, **k)

            async def find_one(self, *a, **k):
                contatore.letture[nome] = contatore.letture.get(nome, 0) + 1
                return await collezione.find_one(*a, **k)

        return _Vista()


def _archivio():
    db = ArchivioDocumenti("test")

    async def semina():
        await db["assegni"].insert_many([
            {"id": "a1", "numero": "0001", "data_incasso": "2026-03-02", "movimento_estratto_conto_id": "m9",
             "sha256": "h-a1", "payload": "x" * 50},
            {"id": "a2", "numero": "0002", "data": "2026-03-05"},
        ])
        await db["bonifici_transfers"].insert_many([
            {"id": "b1", "importo": -120.5, "data": "2026-04-01T10:00:00", "causale": "FT 12",
             "movimento_estratto_conto_id": "m7", "document_hash": "h-b1"},
            {"id": "b2", "importo": 30, "data": "2026-04-02", "transaction_code": "TX2"},
        ])
        await db["estratto_conto_movimenti"].insert_many([
            {"id": "m1", "importo": -99.9, "data": "2026-05-01", "descrizione": "BONIFICO A FORNITORE",
             "sha256": "h-m1", "xml_raw": "<grande/>"},
        ])

    asyncio.run(semina())
    return db


FATTURE = [
    {"id": "f1", "assegni_collegati": [{"assegno_id": "a1", "quota": 50, "banca_confermata": True, "numero": "0001"}]},
    {"id": "f2", "payment_document_ids": ["b1", "b2", "sparito"], "movimento_bancario_id": "m1"},
    {"id": "f3", "movimento_bancario_id": "m-non-esiste",
     "assegni_collegati": [{"assegno_id": "a2", "quota": 10}, {"assegno_id": "a-non-esiste", "quota": 5}]},
    {"id": "f4", "payment_evidence": [{"tipo": "ricevuta", "importo": 12.3, "data": "2026-06-01"}]},
    {"id": "f5"},
]


def test_in_blocco_da_le_stesse_prove_della_lettura_singola():
    db = _archivio()
    singole = [asyncio.run(project_invoice_payment_evidence(db, f)) for f in FATTURE]
    in_blocco = asyncio.run(project_payment_evidence_many(db, FATTURE))
    assert in_blocco == singole
    # Qualche prova concreta, per non confrontare due vuoti.
    assert in_blocco[0][0]["bank_movement_id"] == "m9"
    assert [p["document_id"] for p in in_blocco[1] if p["type"] == "bonifico_pdf"] == ["b1", "b2"]
    assert in_blocco[1][-1]["status"] == "confirmed" and in_blocco[1][-1]["amount_cents"] == 9990
    assert in_blocco[2][-1]["conflict_reason"] == "movimento_non_trovato"
    assert in_blocco[3][0]["amount_cents"] == 1230
    assert in_blocco[4] == []


def test_tre_letture_in_tutto_non_tre_per_fattura():
    db = _Contatore(_archivio())
    asyncio.run(project_payment_evidence_many(db, FATTURE * 200))
    assert db.letture == {"assegni": 1, "bonifici_transfers": 1, "estratto_conto_movimenti": 1}


def test_senza_collegamenti_nessuna_lettura():
    db = _Contatore(_archivio())
    assert asyncio.run(project_payment_evidence_many(db, [{"id": "x"}, {"id": "y"}])) == [[], []]
    assert db.letture == {}
