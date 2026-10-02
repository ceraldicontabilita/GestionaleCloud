"""Decisione del titolare 02/10/2026 (n. 12): la tolleranza di un centesimo
sugli arrotondamenti IVA resta, ma lo scarto si scrive su una riga propria
nel conto «arrotondamenti» del piano CEE ufficiale (53.01.29 attivi /
71.03.17 passivi), cosi' ogni scrittura salvata quadra al centesimo esatto.
Oltre il centesimo resta il rifiuto. Un motore solo: fatture, corrispettivi,
scritture semplici e storni passano tutti da ``_scrivi_movimento``.
"""
import asyncio

import pytest

import app.services.registrazione_contabile as motore
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.piano_conti_ufficiale import CONTI_UFFICIALI


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _db():
    return ClientArchivioMemoria()["test"]


def _fattura(id_, **extra):
    base = {
        "id": id_, "tipo_documento": "TD01",
        "total_amount": 122.0, "total_tax": 22.0, "iva_detraibile": 22.0,
        "imponibile": 100.0, "invoice_date": "2026-05-10",
        "invoice_number": f"N-{id_}", "supplier_name": "Fornitore Srl",
        "status": "active",
    }
    base.update(extra)
    return base


def _righe_arrotondamento(mov):
    return [r for r in mov["righe"] if r.get("arrotondamento") is True]


def test_i_conti_arrotondamenti_sono_nel_piano_cee_ufficiale():
    for codice, nome in (motore._C_ARROTONDAMENTI_ATTIVI, motore._C_ARROTONDAMENTI_PASSIVI):
        assert CONTI_UFFICIALI[codice] == nome


def test_fattura_con_un_centesimo_di_scarto_quadra_con_riga_arrotondamento():
    db = _db()
    # imponibile 100 + IVA 22 = 122.00, il totale documento dice 122.01
    esito = _run(motore.registra_fattura(db, _fattura("F1", total_amount=122.01)))
    assert esito["stato"] == "registrato"
    mov = esito["movimento"]
    assert len(mov["righe"]) == 4
    dare, avere = motore.totali_decimali(mov["righe"])
    assert dare == avere
    assert motore.scrittura_quadrata(mov["righe"])
    assert mov["totale_dare"] == mov["totale_avere"] == 122.01
    (arr,) = _righe_arrotondamento(mov)
    # AVERE (debito 122.01) eccede il DARE (122.00): manca un DARE, onere passivo.
    assert arr["conto_codice"] == "71.03.17"
    assert arr["conto_nome"] == "Arrotondamenti passivi diversi"
    assert (arr["dare"], arr["avere"]) == (0.01, 0.0)
    assert arr["descrizione"] == "Arrotondamento IVA"
    salvata = _run(db["movimenti_contabili"].find_one({"id": mov["id"]}, {"_id": 0}))
    assert salvata["righe"] == mov["righe"]


def test_fattura_con_scarto_attivo_va_sul_conto_arrotondamenti_attivi():
    db = _db()
    # DARE 122.00 contro AVERE 121.99: manca un AVERE, provento attivo.
    esito = _run(motore.registra_fattura(db, _fattura("F1", total_amount=121.99)))
    assert esito["stato"] == "registrato"
    (arr,) = _righe_arrotondamento(esito["movimento"])
    assert arr["conto_codice"] == "53.01.29"
    assert (arr["dare"], arr["avere"]) == (0.0, 0.01)
    assert motore.scrittura_quadrata(esito["movimento"]["righe"])


def test_fattura_senza_scarto_non_ha_riga_arrotondamento():
    db = _db()
    esito = _run(motore.registra_fattura(db, _fattura("F1")))
    assert esito["stato"] == "registrato"
    assert len(esito["movimento"]["righe"]) == 3
    assert _righe_arrotondamento(esito["movimento"]) == []


def test_fattura_con_due_centesimi_di_scarto_resta_rifiutata():
    db = _db()
    esito = _run(motore.registra_fattura(db, _fattura("F1", total_amount=122.02)))
    assert esito["stato"] == "da_verificare"
    assert "non quadrata" in esito["motivo"]
    assert _run(db["movimenti_contabili"].count_documents({})) == 0


def test_storno_storna_anche_la_riga_di_arrotondamento():
    db = _db()
    _run(db["invoices"].insert_one(_fattura("F1", total_amount=122.01)))
    esito = _run(motore.registra_fattura(db, _fattura("F1", total_amount=122.01)))
    originale = esito["movimento"]
    storno_esito = _run(motore.storna_registrazione_fattura(db, "F1", "prova"))
    assert storno_esito["stato"] == "stornato"
    storno = _run(db["movimenti_contabili"].find_one({"id": storno_esito["storno_id"]}, {"_id": 0}))
    assert len(storno["righe"]) == 4
    (arr_storno,) = _righe_arrotondamento(storno)
    assert arr_storno["conto_codice"] == "71.03.17"
    assert (arr_storno["dare"], arr_storno["avere"]) == (0.0, 0.01)
    assert motore.scrittura_quadrata(storno["righe"])
    # Su ogni conto, arrotondamento compreso, originale e storno si annullano.
    per_conto = {}
    for m in (originale, storno):
        for r in m["righe"]:
            per_conto[r["conto_codice"]] = round(
                per_conto.get(r["conto_codice"], 0) + r["dare"] - r["avere"], 2)
    assert "71.03.17" in per_conto
    assert all(v == 0 for v in per_conto.values())


def test_corrispettivo_con_un_centesimo_di_scarto_passa_dallo_stesso_motore():
    db = _db()
    corr = {"id": "C1", "data": "2026-06-01", "totale": 110.0,
            "totale_imponibile": 100.0, "totale_iva": 10.01, "pagato_contanti": 110.0}
    esito = _run(motore.registra_corrispettivo(db, corr))
    assert esito["stato"] == "registrato"
    mov = esito["movimento"]
    assert motore.scrittura_quadrata(mov["righe"])
    (arr,) = _righe_arrotondamento(mov)
    assert arr["conto_codice"] == "71.03.17"
    assert (arr["dare"], arr["avere"]) == (0.01, 0.0)
    assert mov["totale_dare"] == mov["totale_avere"] == 110.01


def test_scrittura_semplice_con_un_centesimo_di_scarto_passa_dallo_stesso_motore():
    db = _db()
    doc = _run(motore.registra_scrittura_semplice(
        db,
        movimento={"tipo": "prova", "data": "2026-12-31", "anno": 2026},
        righe=[motore.riga(motore._C_QUOTE_TFR, dare=100.01),
               motore.riga(motore._C_FONDO_TFR, avere=100.00)],
        chiave_naturale={"tipo": "prova"},
    ))
    assert doc["gia_presente"] is False
    assert doc["numero_registrazione"] == 1
    assert motore.scrittura_quadrata(doc["righe"])
    (arr,) = _righe_arrotondamento(doc)
    assert arr["conto_codice"] == "53.01.29"
    assert (arr["dare"], arr["avere"]) == (0.0, 0.01)
    salvata = _run(db["movimenti_contabili"].find_one({"tipo": "prova"}, {"_id": 0}))
    assert len(salvata["righe"]) == 3
    with pytest.raises(motore.ScritturaNonQuadrata):
        _run(motore.registra_scrittura_semplice(
            db, movimento={"tipo": "prova2", "data": "2026-12-31", "anno": 2026},
            righe=[motore.riga(motore._C_QUOTE_TFR, dare=100.02),
                   motore.riga(motore._C_FONDO_TFR, avere=100.00)],
            chiave_naturale={"tipo": "prova2"}))
    assert _run(db["movimenti_contabili"].count_documents({"tipo": "prova2"})) == 0
