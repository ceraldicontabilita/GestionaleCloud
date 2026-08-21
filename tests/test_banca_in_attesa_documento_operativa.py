import asyncio

from app.services.sheets_document_store import MemorySheetsClient

from app.routers.prima_nota_module import banca


def _run(awaitable):
    return asyncio.run(awaitable)


def test_coda_esclude_gia_collegati_e_mostra_i_candidati(monkeypatch):
    db = MemorySheetsClient()["banca_in_attesa_documento_test"]
    monkeypatch.setattr(banca.Database, "get_db", staticmethod(lambda: db))
    _run(db["estratto_conto_movimenti"].insert_many([
        {
            "id": "ec-gia-collegato", "data": "2026-08-01", "tipo": "uscita",
            "importo": 100.0, "stato_riconciliazione": "in_attesa_documento",
            "riconciliato": False, "fattura_id": "fattura-esistente",
        },
        {
            "id": "ec-riba", "data": "2026-08-08", "tipo": "uscita",
            "importo": 1119.48, "stato_riconciliazione": "in_attesa_documento",
            "riconciliato": False,
            "descrizione_originale": "RIB LEASYS ITALIA SPA",
        },
        {
            "id": "ec-stipendio-classificato", "data": "2026-08-07",
            "tipo": "uscita", "importo": 1400.0,
            "stato_riconciliazione": "in_attesa_documento",
            "riconciliato": False, "classificato_contabilmente": True,
            "tipo_classificazione_contabile": "stipendio",
            "dipendente_id": "valerio-ceraldi",
            "prima_nota_banca_id": "pn-stipendio-valerio",
        },
    ]))
    _run(db["operazioni_da_confermare"].insert_one({
        "id": "op-riba", "movimento_ec_id": "ec-riba", "stato": "da_confermare",
        "created_at": "2026-08-08T10:00:00",
        "dettagli": {
            "motivo_dubbio": "Importo al centesimo, ma 2 fatture sono candidate",
            "fatture_candidate": [
                {"id": "f1", "numero": "100", "fornitore": "LEASYS ITALIA SPA", "importo": 1119.48},
                {"id": "f2", "numero": "101", "fornitore": "LEASYS ITALIA SPA", "importo": 1119.48},
            ],
        },
    }))

    risultato = _run(banca.movimenti_in_attesa_documento(anno=2026))

    assert risultato["totale"] == 1
    assert risultato["gia_collegati_da_allineare"] == 1
    assert risultato["movimenti"][0]["id"] == "ec-riba"
    assert risultato["movimenti"][0]["strumento_bancario"]["codice"] == "riba"
    assert {c["id"] for c in risultato["movimenti"][0]["candidati"]} == {"f1", "f2"}
    assert "2 fatture" in risultato["movimenti"][0]["motivo_sospensione"]


def test_coda_mostra_estratti_drive_legacy_senza_stato(monkeypatch):
    """Le righe reali idratate da vecchi fogli non devono sparire.

    Un record senza ``stato_riconciliazione`` e' ancora aperto; se invece ha
    gia' evidenza di collegamento resta fuori dalla coda operativa.
    """
    db = MemorySheetsClient()["banca_in_attesa_documento_legacy"]
    monkeypatch.setattr(banca.Database, "get_db", staticmethod(lambda: db))
    _run(db["estratto_conto_movimenti"].insert_many([
        {
            "id": "ec-legacy-aperto", "data": "2026-01-02",
            "tipo": "uscita", "importo": 10.0,
            "descrizione_originale": "BONIFICO A FORNITORE DA ASSOCIARE",
            "categoria": "Fatture",
        },
        {
            "id": "ec-legacy-collegato", "data": "2026-01-03",
            "tipo": "uscita", "importo": 20.0,
            "descrizione_originale": "PAGAMENTO FATTURA GIA COLLEGATA",
            "categoria": "Fatture", "fattura_id": "fattura-1",
        },
        {
            "id": "ec-legacy-riconciliato", "data": "2026-01-04",
            "tipo": "uscita", "importo": 30.0,
            "descrizione_originale": "PAGAMENTO GIA RICONCILIATO",
            "categoria": "Fatture", "riconciliato": True,
        },
        {
            "id": "ec-altro-anno", "data": "2025-01-02",
            "tipo": "uscita", "importo": 40.0,
            "descrizione_originale": "BONIFICO 2025",
            "categoria": "Fatture",
        },
    ]))

    risultato = _run(banca.movimenti_in_attesa_documento(anno=2026))

    assert risultato["totale"] == 1
    assert risultato["gia_collegati_da_allineare"] == 1
    assert risultato["movimenti"][0]["id"] == "ec-legacy-aperto"
