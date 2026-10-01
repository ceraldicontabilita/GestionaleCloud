"""Collaudo funzionale Assegni: dal modulo del carnet alla prova in banca, con i motori veri.

ATTESO secondo CLAUDE.md («un solo motore abbina», numero **e** importo al centesimo,
collegare una fattura all'intero importo la dichiara pagata subito, la prova bancaria la
sostituisce, annullo e storno riaprono la fattura).
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.routers.bank import assegni as router
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture
def db(monkeypatch):
    db = ClientArchivioMemoria()["assegni-scenari"]
    monkeypatch.setattr(router.Database, "get_db", staticmethod(lambda: db))
    return db


NUMERO = "0208770651"


def _assegno(db, numero=NUMERO, importo=300.0, stato="compilato", **extra):
    _run(db["assegni"].insert_one({"id": f"a-{numero}", "numero": numero, "stato": stato,
                                   "importo": importo, **extra}))


def _fattura(db, fid="f1", totale=300.0, piva="00000000001", **extra):
    _run(db["invoices"].insert_one({
        "id": fid, "invoice_number": f"N-{fid}", "invoice_date": "2026-05-01", "total_amount": totale,
        "importo_residuo": totale, "pagato": False, "supplier_vat": piva,
        "supplier_name": "FORNITORE TEST", **extra}))


def _collega(db, assegno_id, *quote):
    return _run(router.collega_fatture_assegno(
        assegno_id, router.FattureCollegateIn(
            fatture=[router.FatturaQuotaIn(fattura_id=f, quota=q) for f, q in quote])))


def _addebito(db, numero=NUMERO, importo=300.0, mid="ec-1", data="2026-05-08"):
    _run(db["estratto_conto_movimenti"].insert_one({
        "id": mid, "data": data, "data_pagamento": data, "importo": importo, "tipo": "uscita",
        "descrizione": f"PRELIEVO ASSEGNO - DM 05387 CRA: 26050700167309 NUM: {numero}",
        "riconciliato": False}))


def _righe_banca(db, fid):
    return _run(db["prima_nota_banca"].find(
        {"fattura_id": fid, "status": {"$nin": ["deleted", "archived"]}}, {"_id": 0}).to_list(10))


def test_collegare_la_fattura_la_dichiara_pagata_e_la_prova_bancaria_la_sostituisce(db):
    """ATTESO: subito pagata «dichiarata» (una riga dichiarato_titolare); quando l'addebito
    (numero + importo al centesimo) arriva, resta UNA riga con la prova vera e la fattura e' riconciliata."""
    _assegno(db)
    _fattura(db)
    _collega(db, f"a-{NUMERO}", ("f1", 300.0))
    f = _run(db["invoices"].find_one({"id": "f1"}))
    assert f["pagato"] is True and f["stato_finanziario"] == "pagata_dichiarata_in_attesa_banca"
    prima = _righe_banca(db, "f1")
    assert len(prima) == 1 and prima[0]["dichiarato_titolare"] is True

    _addebito(db)
    esito = _run(router.sync_assegni_da_estratto_conto())
    assert esito["assegni_riconciliati"] == 1 and esito["assegni_creati"] == 0
    a = _run(db["assegni"].find_one({"id": f"a-{NUMERO}"}))
    assert a["stato"] == "incassato" and a["incassato_confermato_banca"] is True
    dopo = _righe_banca(db, "f1")
    assert len(dopo) == 1, dopo
    assert not dopo[0].get("dichiarato_titolare")
    f = _run(db["invoices"].find_one({"id": "f1"}))
    assert f["stato_finanziario"] == "riconciliato" and f["riconciliato_con_ec"] is True
    # la dichiarazione non resta viva accanto alla prova
    assert _run(db["prima_nota_banca"].count_documents(
        {"fattura_id": "f1", "dichiarato_titolare": True, "status": {"$nin": ["deleted", "archived"]}})) == 0
    # secondo giro: niente di nuovo
    esito2 = _run(router.sync_assegni_da_estratto_conto())
    assert esito2["assegni_creati"] == 0
    assert len(_righe_banca(db, "f1")) == 1


def test_addebito_con_lo_stesso_numero_ma_importo_diverso_non_riconcilia_ne_paga(db):
    _assegno(db)
    _fattura(db)
    _collega(db, f"a-{NUMERO}", ("f1", 300.0))
    _addebito(db, importo=300.01)
    esito = _run(router.sync_assegni_da_estratto_conto())
    assert esito["assegni_riconciliati"] == 0
    a = _run(db["assegni"].find_one({"id": f"a-{NUMERO}"}))
    assert a["stato"] != "incassato" and not a.get("incassato_confermato_banca")
    assert a["riscontro_banca_da_verificare"]["importo_banca"] == 300.01
    f = _run(db["invoices"].find_one({"id": "f1"}))
    assert f["stato_finanziario"] == "pagata_dichiarata_in_attesa_banca"      # resta dichiarata, non provata


def test_due_export_dello_stesso_addebito_sono_un_solo_assegno(db):
    """ATTESO: stesso numero e stesso importo = una scheda sola, anche con due movimenti copia."""
    _addebito(db, mid="ec-export-1")
    _addebito(db, mid="ec-export-2", data="2026-05-09")
    _run(router.sync_assegni_da_estratto_conto())
    _run(router.sync_assegni_da_estratto_conto())
    assert _run(db["assegni"].count_documents({"numero": NUMERO})) == 1


def test_la_quota_deve_fare_l_intero_importo_dell_assegno_e_della_fattura(db):
    _assegno(db)
    _fattura(db, totale=500.0)
    with pytest.raises(HTTPException) as exc:
        _collega(db, f"a-{NUMERO}", ("f1", 300.0))          # parziale sulla fattura
    assert exc.value.status_code == 400
    f = _run(db["invoices"].find_one({"id": "f1"}))
    assert f["pagato"] is False and _righe_banca(db, "f1") == []
    with pytest.raises(HTTPException):
        _collega(db, f"a-{NUMERO}", ("f1", 299.99))         # un centesimo di meno dell'assegno


def test_una_fattura_gia_pagata_in_banca_non_si_paga_una_seconda_volta_con_un_assegno(db):
    _assegno(db)
    _fattura(db, pagato=True, importo_residuo=0.0, stato_finanziario="riconciliato",
             riconciliato_con_ec=True, payment_status="paid")
    with pytest.raises(HTTPException) as exc:
        _collega(db, f"a-{NUMERO}", ("f1", 300.0))
    assert exc.value.status_code in (400, 409)
    assert _righe_banca(db, "f1") == []


def test_fatture_di_fornitori_diversi_non_stanno_sullo_stesso_assegno(db):
    _assegno(db, importo=600.0)
    _fattura(db, "f1", 300.0, piva="00000000001")
    _fattura(db, "f2", 300.0, piva="00000000002")
    with pytest.raises(HTTPException) as exc:
        _collega(db, f"a-{NUMERO}", ("f1", 300.0), ("f2", 300.0))
    assert exc.value.status_code == 400


def test_l_annullo_riapre_la_fattura_ritira_la_dichiarazione_e_il_numero_non_torna_libero(db):
    _assegno(db)
    _fattura(db)
    _collega(db, f"a-{NUMERO}", ("f1", 300.0))
    _run(router.annulla_assegno(f"a-{NUMERO}", router.AnnulloAssegnoIn(motivo="Scritto male")))
    f = _run(db["invoices"].find_one({"id": "f1"}))
    assert f["pagato"] is False and f["in_attesa_riscontro_banca"] is False
    assert _righe_banca(db, "f1") == []
    with pytest.raises(HTTPException) as exc:
        _run(router.update_assegno(f"a-{NUMERO}", {"stato": "vuoto"}))
    assert exc.value.status_code == 409
    # la fattura riaperta si puo' pagare con un altro assegno
    _assegno(db, numero="0208770652")
    _collega(db, "a-0208770652", ("f1", 300.0))
    assert _run(db["invoices"].find_one({"id": "f1"}))["pagato"] is True


def test_il_carnet_rimette_lo_zero_perso_e_un_secondo_carnet_sovrapposto_non_salva_nulla(db):
    """ATTESO: «208770641» (zero perso da un foglio di calcolo) = «0208770641»; 10 numeri da …1 a …0;
    un carnet che ne ripete uno e' rifiutato per intero, senza righe parziali."""
    primo = _run(router.genera_assegni(numero_primo="208770641", quantita=10, anno=2026))
    assert primo["primo"] == "0208770641" and primo["ultimo"] == "0208770650"
    assert primo["numeri"][0] == "0208770641" and len(primo["numeri"]) == 10
    assert _run(db["assegni"].count_documents({})) == 10
    with pytest.raises(HTTPException) as exc:
        _run(router.genera_assegni(numero_primo="0208770648", quantita=10, anno=2026))
    assert exc.value.status_code == 400
    assert _run(db["assegni"].count_documents({})) == 10


def test_un_numero_emesso_non_si_elimina_e_non_torna_vuoto(db):
    _assegno(db, stato="emesso")
    with pytest.raises(HTTPException) as exc:
        _run(router.update_assegno(f"a-{NUMERO}", {"stato": "vuoto"}))
    assert exc.value.status_code == 409
    with pytest.raises(HTTPException) as exc:
        _run(router.delete_assegno(f"a-{NUMERO}"))
    assert exc.value.status_code in (400, 409)
    assert _run(db["assegni"].count_documents({"numero": NUMERO})) == 1
