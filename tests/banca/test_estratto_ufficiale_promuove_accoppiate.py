"""L'estratto ufficiale (PDF) scrive la causale senza il prefisso dell'export
CSV («SDD CORE: …» contro «ADDEBITO DIRETTO SDD - SDD CORE: …»): la riga si
riconosce solo per giorno, verso e importo (`accoppia`). Prima contava come
doppione ma restava operativa: Q1 2026, 330 promosse su 616 lette."""
import asyncio

import pytest

from app.parsers import estratto_conto_bpm_parser as parser_bpm
from app.routers.bank import estratto_conto as modulo
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

FILE_PDF = "Estratto conto corrente_30-06-2026.pdf"
CAUSALE_CSV = "ADDEBITO DIRETTO SDD - SDD CORE: 0000000000000000000001 FORNITORE UNO SRL"
CAUSALE_PDF = "SDD CORE: 0000000000000000000001 FORNITORE UNO SRL"


class _File:
    skip_duplicate_repairs = True

    def __init__(self, contenuto, filename):
        self.filename = filename
        self._contenuto = contenuto

    async def read(self):
        return self._contenuto


def _run(awaitable):
    return asyncio.run(awaitable)


@pytest.fixture
def db(monkeypatch):
    finto = ClientArchivioMemoria()["promozione_accoppiate_test"]
    monkeypatch.setattr(modulo.Database, "get_db", staticmethod(lambda: finto))
    monkeypatch.setattr(parser_bpm, "parse_estratto_conto_bpm", lambda _content: {
        "success": True, "tipo_documento": "estratto_conto_banco_bpm", "totale_transazioni": 1,
        "transazioni": [{
            "data": "2026-04-01", "data_valuta": "2026-04-01", "data_disponibile": "2026-04-01",
            "descrizione": CAUSALE_PDF, "importo": -850.34, "tipo": "uscita",
            "banca": "Banco BPM", "divisa": "EUR",
        }],
    })
    _run(finto["estratto_conto_movimenti"].insert_one({
        "id": "EC-2026-04-01-850.34-operativa", "data": "2026-04-01", "tipo": "uscita",
        "importo": 850.34, "descrizione": CAUSALE_CSV, "descrizione_originale": CAUSALE_CSV,
        "banca": "05034 - BANCO BPM S.P.A.", "divisa": "EUR", "source_filename": "export.csv",
        "fingerprint": "fp-operativa", "operation_key": "ok-operativa", "operation_id": "bank:ok-operativa",
        "livello_evidenza": "provvisorio", "evidenza_bancaria_ufficiale": False,
        "in_attesa_estratto_ufficiale": True, "riconciliato": False,
    }))
    return finto


def _importa_pdf():
    return _run(modulo.import_estratto_conto(_File(b"%PDF-1.4 finto", FILE_PDF)))


def test_la_riga_accoppiata_per_giorno_verso_importo_diventa_ufficiale(db):
    esito = _importa_pdf()

    righe = _run(db["estratto_conto_movimenti"].find({"data": "2026-04-01"}).to_list(None))
    assert len(righe) == 1, "la causale diversa non crea una seconda riga"
    riga = righe[0]
    assert riga["evidenza_bancaria_ufficiale"] is True
    assert riga["source_filename_ufficiale"] == FILE_PDF
    assert riga.get("in_attesa_estratto_ufficiale") is False
    assert esito["stats"]["nuovi"] == 0 and esito["stats"]["duplicati"] == 1


def test_il_secondo_import_dello_stesso_pdf_non_cambia_nulla(db):
    _importa_pdf()
    esito = _importa_pdf()

    assert esito["stats"]["nuovi"] == 0
    assert _run(db["estratto_conto_movimenti"].count_documents({"data": "2026-04-01"})) == 1
