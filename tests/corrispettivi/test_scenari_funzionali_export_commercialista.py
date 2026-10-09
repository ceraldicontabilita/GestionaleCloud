"""Collaudo funzionale: l'export Excel del commercialista legge l'IVA vera dei corrispettivi.

Il foglio «Riepilogo IVA» scorporava un 10% fisso dal totale incassato
(«assumiamo 10%»): con aliquote miste (22% su una parte della merce) l'IVA a
debito era un numero inventato. L'IVA dei corrispettivi e' quella dichiarata dal
registratore telematico; se una giornata non la porta si segnala, non si stima.
"""
import io

from openpyxl import load_workbook

from app.database import Database
from app.routers import commercialista

from ._comune import D, nuovo_db, run


def _scarica(db, monkeypatch):
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))

    async def corpo():
        risposta = await commercialista.export_excel_commercialista(2026, 9)
        pezzi = [p async for p in risposta.body_iterator]
        return b"".join(p if isinstance(p, bytes) else p.encode() for p in pezzi)

    return load_workbook(io.BytesIO(run(corpo())))


def _riga_iva(wb, voce):
    for riga in wb["Riepilogo IVA"].iter_rows(min_row=2, values_only=True):
        if riga[0] and str(riga[0]).startswith(voce):
            return riga[1]
    raise AssertionError(f"voce {voce!r} assente: {list(wb['Riepilogo IVA'].values)}")


def _corr(id_, giorno, totale, imponibile, iva, **altro):
    return {"id": id_, "data": giorno, "totale": totale, "totale_imponibile": imponibile,
            "totale_iva": iva, "pagato_contanti": totale, "pagato_elettronico": 0.0,
            "status": "imported", "stato": "definitivo_xml", **altro}


def test_iva_a_debito_e_quella_dichiarata_dal_registratore_non_un_10_per_cento(monkeypatch):
    db = nuovo_db("exp_iva")
    # Giornata a 10% (1.100 = 1.000 + 100) e giornata con una parte al 22% (1.220 = 1.000 + 220).
    run(db["corrispettivi"].insert_many([
        _corr("a", "2026-09-01", 1100.0, 1000.0, 100.0),
        _corr("b", "2026-09-02", 1220.0, 1000.0, 220.0),
    ]))

    wb = _scarica(db, monkeypatch)

    assert D(_riga_iva(wb, "IVA a debito")) == D("320.00")         # 100 + 220 dichiarati, non 2.320 * 10/110 = 210,91


def test_giornata_senza_iva_dichiarata_non_si_stima_si_segnala(monkeypatch):
    db = nuovo_db("exp_iva_mancante")
    run(db["corrispettivi"].insert_many([
        _corr("a", "2026-09-01", 1100.0, 1000.0, 100.0),
        {"id": "b", "data": "2026-09-02", "totale": 500.0, "pagato_contanti": 500.0,
         "status": "imported"},                                        # niente IVA ne' riepilogo
    ]))

    wb = _scarica(db, monkeypatch)

    assert D(_riga_iva(wb, "IVA a debito")) == D("100.00")          # la giornata muta non porta IVA inventata
    assert _riga_iva(wb, "ATTENZIONE") in (None, "")                # ... ed e' dichiarata
    assert "1 giorni" in [r[0] for r in wb["Riepilogo IVA"].values if r[0] and "ATTENZIONE" in str(r[0])][0]
