"""Scadenzario tributi: nei termini, in ritardo, ravveduto (casi reali anonimi)."""
from datetime import date

from app.services import f24_controllo_incrociato as reg
from app.services import scadenzario_tributi as sc


def _riga(codice, periodo, debito=0, credito=0):
    return {"codice_tributo": codice, "periodo_riferimento": periodo,
            "importo_debito_cents": debito, "importo_credito_cents": credito}


def _q(id_, data, erario=(), regioni=(), locali=(), saldo=None):
    righe = list(erario) + list(regioni) + list(locali)
    s = sum(r["importo_debito_cents"] - r["importo_credito_cents"] for r in righe) if saldo is None else saldo
    return reg._quietanza_legacy({
        "id": id_, "data_pagamento": data, "protocollo_telematico": f"P-{id_}",
        "sezione_erario": list(erario), "sezione_regioni": list(regioni), "sezione_tributi_locali": list(locali),
        "sezione_inps": [], "totali": {"saldo_netto_cents": s}, "f24_associati": [],
    })


def _calcola(*quietanze, **kw):
    return {v["chiave"]: v for v in sc.calcola(reg.pagamenti_da_quietanze(quietanze), **kw)}


def test_calendario_ferragosto_e_festivi():
    assert sc.termine_effettivo(date(2020, 8, 16)) == date(2020, 8, 20)
    assert sc.termine_effettivo(date(2026, 5, 16)) == date(2026, 5, 18)  # sabato
    assert sc.termine_effettivo(date(2024, 12, 16)) == date(2024, 12, 16)


def test_pagato_nei_termini():
    voci = _calcola(_q("a", "2026-04-16", erario=[_riga("1001", "03/2026", 100000)]))
    v = voci["sezione_erario|1001|2026|3"]
    assert v["stato"] == sc.PUNTUALE and v["scadenza"] == "2026-04-16"


def test_ritardo_senza_sanzione_e_non_ravveduto():
    voci = _calcola(_q("a", "2026-05-20", erario=[_riga("1001", "03/2026", 100000)]))
    v = voci["sezione_erario|1001|2026|3"]
    assert v["stato"] == sc.RITARDO_NON_RAVVEDUTO
    p = v["pagamenti"][0]
    assert p["giorni_ritardo"] == 34 and p["sanzione_attesa_cents"] == 1389  # 1,3889% (31–90 gg, nuovo regime)


def test_ritenuta_2020_ravveduta_in_compensazione():
    # F24 del 05/10/2020 a saldo zero: 1012 07/2020 scaduto il 20/08/2020
    # (Ferragosto), sanzione 8906 per il periodo, crediti 1631/1655/1701.
    q = _q("z", "2020-10-05", saldo=0, erario=[
        _riga("1012", "07/2020", 39573), _riga("8906", "07/2020", 3878),
        _riga("1655", "07/2020", 0, 2630), _riga("1701", "07/2020", 0, 4538), _riga("1631", "2019", 0, 96000),
        _riga("8906", "07/2019", 799)],
        regioni=[_riga("3802", "07/2019", 35294), _riga("3802", "07/2020", 7575)],
        locali=[_riga("3848", "07/2019", 11591), _riga("3847", "07/2020", 2856)])
    voci = _calcola(q)
    v = voci["sezione_erario|1012|2020|7"]
    assert v["scadenza"] == "2020-08-20" and v["pagamenti"][0]["giorni_ritardo"] == 46
    assert v["stato"] == sc.RAVVEDUTO and v["pagamenti"][0]["compensazione_totale"] is True
    # Addizionale del 2019 trattenuta a luglio 2020: stesso periodo della sanzione 8906 07/2019.
    add = voci["sezione_regioni|3802|2019|7"]
    assert add["scadenza"] == "2020-08-20" and add["stato"] == sc.RAVVEDUTO


def test_sanzione_troppo_bassa_e_insufficiente():
    q = _q("a", "2026-09-30", erario=[_riga("1001", "03/2026", 1000000), _riga("8906", "03/2026", 1000)])
    v = _calcola(q)["sezione_erario|1001|2026|3"]
    assert v["stato"] == sc.RAVVEDIMENTO_INSUFFICIENTE  # 3,125% di 10.000 = 312,50 attesi


def test_interessi_legali_per_anno():
    # 1.000 € dal 01/12/2023 al 31/01/2024: 31 gg al 5% + 30 gg al 2,5%
    assert sc.interessi_legali_cents(100000, date(2023, 12, 1), date(2024, 1, 31)) == 425 + 205


def test_codice_senza_regola_non_inventa_la_scadenza():
    v = _calcola(_q("a", "2026-06-30", erario=[_riga("9001", "2023", 5000)]))["sezione_erario|9001|2023|"]
    assert v["stato"] == sc.SCADENZA_NON_DETERMINATA and v["scadenza"] is None


def test_scadenza_del_commercialista_vince_sulla_regola():
    q = _q("a", "2025-07-21", erario=[_riga("2003", "2024", 50000)])
    senza = _calcola(q)["sezione_erario|2003|2024|"]
    assert senza["stato"] == sc.RITARDO_NON_RAVVEDUTO  # regola: 30/06/2025
    con = _calcola(q, scadenze_modello={("sezione_erario", "2003", 2024, None): "2025-07-21"})["sezione_erario|2003|2024|"]
    assert con["stato"] == sc.PUNTUALE


def test_avviso_non_dovuto_se_pagato_nei_termini_o_ravveduto():
    voci = sc.calcola(reg.pagamenti_da_quietanze([
        _q("a", "2026-04-16", erario=[_riga("1001", "03/2026", 100000)]),
        _q("b", "2026-05-25", erario=[_riga("1040", "03/2026", 21000), _riga("8948", "03/2026", 300)]),
    ]))
    righe = [sc.verdetto_riga("1001", 2026, 3, 100000, voci), sc.verdetto_riga("1040", 2026, 3, 21000, voci)]
    assert [r["verdetto"] for r in righe] == [sc.NON_DOVUTO, sc.NON_DOVUTO]
    v = sc.verdetto_avviso("0123456789", righe)
    assert v["esito"] == sc.NON_DOVUTO
    assert v["testo"].startswith("Avviso n. 0123456789 non dovuto: F24 pagati regolarmente con sanzioni e interessi")


def test_avviso_dovuto_per_differenza_o_senza_quietanza():
    voci = sc.calcola(reg.pagamenti_da_quietanze([_q("a", "2026-04-16", erario=[_riga("1001", "03/2026", 90000)])]))
    r1 = sc.verdetto_riga("1001", 2026, 3, 100000, voci, data_versamento_ade="2026-04-20")
    assert r1["verdetto"] == sc.DOVUTO_DIFFERENZA and r1["differenza_cents"] == 10000
    assert "chiedere lo sgravio" in r1["note"][0]
    r2 = sc.verdetto_riga("6031", 2026, None, 50000, voci)
    assert r2["verdetto"] == sc.DOVUTO
    assert sc.verdetto_avviso(None, [r1, r2])["da_pagare_cents"] == 60000


def test_quietanze_a_saldo_zero_gia_importate_si_allineano():
    import asyncio
    from mongomock_motor import AsyncMongoMockClient
    from app.services import quietanze_import as qi

    db = AsyncMongoMockClient()["t"]
    asyncio.run(db[qi.COLL_QUIETANZE].insert_many([
        {"id": "z", "saldo": 0.0, "stato_quietanza": "QUIETANZA_PRESENTE_F24_MANCANTE",
         "sezione_erario": [{"codice_tributo": "1012", "periodo_riferimento": "07/2020", "importo_debito": 395.73},
                            {"codice_tributo": "1631", "periodo_riferimento": "2019", "importo_credito": 395.73}]},
        {"id": "n", "saldo": 10.0, "stato_quietanza": "QUIETANZA_PRESENTE_F24_MANCANTE",
         "sezione_erario": [{"codice_tributo": "1001", "periodo_riferimento": "07/2020", "importo_debito": 10.0}]},
    ]))
    asyncio.run(db[qi.COLL_F24_ALERTS].insert_one(
        {"id": "al", "quietanza_id": "z", "tipo": "quietanza_senza_match", "status": "pending"}))
    r = asyncio.run(qi.allinea_quietanze_saldo_zero(db))
    assert r == {"controllate": 2, "aggiornate": 1, "alert_chiusi": 1}
    z = asyncio.run(db[qi.COLL_QUIETANZE].find_one({"id": "z"}))
    assert z["stato_quietanza"] == "QUIETANZA_COMPENSAZIONE_TOTALE" and z["calcolo_fiscale_sospeso"] is False
    assert asyncio.run(qi.allinea_quietanze_saldo_zero(db))["aggiornate"] == 0
