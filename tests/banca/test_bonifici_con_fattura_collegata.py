"""Archivio bonifici: un bonifico con la fattura collegata mostra la fattura (e se salda o e' acconto), non il periodo."""
import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.routers.bonifici_module import transfers as t


def _run(c):
    return asyncio.run(c)


def _db():
    db = AsyncMongoMockClient()["x"]
    _run(db["invoices"].insert_many([
        {"id": "1776634707747", "invoice_number": "FPR 1/26", "total_amount": 3750.0, "supplier_name": "CIERVO FABIANA"},
        {"id": 7, "invoice_number": "FPR 9/26", "total_amount": 8750.0},
        {"id": "9", "invoice_number": "RIT 1", "total_amount": 1000.0, "importo_ritenuta": 200.0},
    ]))
    return db


def test_intero_acconto_ritenuta_ed_id_numerico():
    db = _db()
    righe = [
        {"id": "a", "importo": 3750, "fattura_associata": True, "fattura_id": "1776634707747", "fattura_ids": ["1776634707747"]},
        {"id": "b", "importo": 5000, "fattura_associata": True, "fattura_id": "7"},            # id numerico in archivio
        {"id": "c", "importo": 800, "fattura_associata": True, "fattura_ids": ["9"]},           # netto di ritenuta = 800
        {"id": "d", "importo": 100, "fattura_associata": False},
    ]
    _run(t._arricchisci_con_fattura(db, righe))
    a, b, c, d = righe
    assert a["fattura_numero"] == "FPR 1/26" and a["fattura_esito"] == "intero"
    assert b["fattura_numero"] == "FPR 9/26" and b["fattura_esito"] == "acconto" and b["fattura_dovuto_cents"] == 875000
    assert c["fattura_esito"] == "intero" and c["fattura_dovuto_cents"] == 80000
    assert "fattura_numero" not in d and "fattura_esito" not in d


def test_piu_fatture_non_dice_acconto_per_il_totale():
    db = _db()
    r = {"id": "e", "importo": 3750, "fattura_associata": True, "fattura_ids": ["1776634707747", "7"]}
    _run(t._arricchisci_con_fattura(db, [r]))
    assert r["fattura_numero"] == "FPR 1/26, FPR 9/26" and "fattura_esito" not in r


def test_causale_con_fattura_non_e_uno_stipendio_nemmeno_col_nome_di_un_dipendente():
    from app.routers.bonifici_module.classification import classifica_destinazione_dipendente as c

    dip = [{"id": "d1", "nome": "Fabiana", "cognome": "Prova", "nome_completo": "Fabiana Prova"}]
    fattura = {"beneficiario": {"nome": "Fabiana Prova"}, "causale": "Fabiana Prova fattura FPR 1/26"}
    assert c(fattura, dip)["destinazione_dipendente"] is False
    assert c(fattura, dip)["motivo_destinazione"] == "causale_fattura"
    # lo stipendio resta stipendio, il TFR resta TFR
    assert c({"beneficiario": {"nome": "Fabiana Prova"}, "causale": "stipendio agosto"}, dip)["destinazione_dipendente"] is True
    assert c({"beneficiario": {"nome": "Fabiana Prova"}, "causale": "TFR liquidazione"}, dip)["tipo_retribuzione"] == "tfr"
