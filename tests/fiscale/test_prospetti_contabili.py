"""Prospetto contabile del consulente: cosa l'F24 del mese deve versare, e l'aggancio all'F24."""
import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services import prospetti_contabili as pc


def run(coro):
    return asyncio.run(coro)


def _testo(mese="Febbraio", anno=2018, ritenute="384,66", stampa="07/03/2018  ALLE : 17:09"):
    return f"""[PAGINA 1]
FERRANTINI FULVIO                            STAMPATO IL : {stampa}
|                                                                                   |{mese} {anno}                                        *** PROSPETTO CONTABILE ***
DITTA : CERALDI GROUP S.R.L.                                        CODICE :     16
RETRIBUZIONE LORDA OPERAI                              6.490,36+|
TOTALE RETRIBUZIONI LORDE                                              8.331,33+|
RITENUTE PREVIDENZIALI                                   778,19-|
RITENUTE FISCALI                                         {ritenute}-|
CREDITO BONUS IRPEF                                      240,00+|
ADD. REGIONALE ANNO PRECEDENTE                            98,36-|
ADD. COMUNALE ANNO PRECEDENTE                             28,43-|
IMPORTO VERSATO DM/10                                                 1.800,00+|
ADD. REGIONALE VERSATO                                    98,00+|
RITENUTE FISCALI A DEBITO                                384,66-|
"""


def _riga(sezione, codice, mese, anno, deb, cred, campo="codice_tributo"):
    return {campo: codice, "anno": str(anno), "mese": f"{mese:02d}", "periodo_riferimento": f"{mese:02d}/{anno}",
            "importo_debito_cents": deb, "importo_credito_cents": cred}


def _f24(id_, ritenute=38466, versamento="2018-03-16", saldo=207145):
    return {
        "id": id_, "status": "da_pagare",
        "dati_generali": {"data_versamento": versamento, "saldo_delega_cents": saldo},
        "sezione_erario": [_riga("e", "1001", 2, 2018, ritenute, 0), _riga("e", "1655", 2, 2018, 0, 24000)],
        "sezione_inps": [_riga("i", "DM10", 2, 2018, 180000, 0, campo="causale")],
        "sezione_regioni": [_riga("r", "3802", 2, 2017, 9836, 0)],
        # il 3848 con due comuni: le righe dello stesso codice e periodo si sommano
        "sezione_tributi_locali": [_riga("l", "3848", 2, 2017, 1176, 0), _riga("l", "3848", 2, 2017, 1667, 0)],
    }


def _db(*f24):
    db = AsyncMongoMockClient()["prospetti"]
    if f24:
        run(db["f24_unificato"].insert_many([dict(f) for f in f24]))
    return db


def _deposita(db, testo, sha="a" * 64):
    return run(pc.deposita_prospetto(db, pc.leggi_prospetto(testo), documento_id="d1", filename="l.pdf", sha256=sha))


def _prospetto(db, pid):
    return run(db["prospetti_contabili"].find_one({"id": pid}, {"_id": 0}))


def test_si_leggono_gli_importi_attesi_e_il_periodo_delle_addizionali_e_dell_anno_prima():
    testo = _testo()
    assert pc.riconosci(testo)
    p = pc.leggi_prospetto(testo)
    assert (p["mese"], p["anno"], p["codice_ditta"], p["stampato_il"]) == (2, 2018, "16", "2018-03-07T17:09")
    attesi = {a["codice"]: (a["importo_cents"], a["lato"], a["mese"], a["anno"]) for a in p["attesi"]}
    assert attesi == {
        "1001": (38466, "debito", 2, 2018),
        "1655": (24000, "credito", 2, 2018),
        "3802": (9836, "debito", 2, 2017),      # «anno precedente»: l'F24 lo riferisce al 2017
        "3848": (2843, "debito", 2, 2017),
        "DM10": (180000, "debito", 2, 2018),
    }
    # le addizionali arrotondate «versate» non sono un importo da F24: si vedono, non si usano
    assert any(v["etichetta"] == "ADD. REGIONALE VERSATO" for v in p["non_mappate"])
    assert not pc.riconosci("DITTA : X\nRITENUTE FISCALI   1,00-|")      # senza intestazione non e' un prospetto


def test_l_f24_si_aggancia_per_codice_periodo_e_importo_in_tutti_e_due_i_sensi():
    for primo in ("prospetto", "f24"):
        db = _db(_f24("f24-feb")) if primo == "f24" else _db()
        pid = _deposita(db, _testo())
        if primo == "prospetto":
            run(db["f24_unificato"].insert_one(_f24("f24-feb")))     # l'F24 arriva dopo
        run(pc.collega_prospetti(db))
        p = _prospetto(db, pid)
        assert p["esito"] == pc.COMPLETO and p["f24_id"] == "f24-feb", primo
        assert [r["esito"] for r in p["riscontro"]] == ["OK"] * 5


def test_importo_diverso_non_si_forza_e_due_f24_uguali_non_si_scelgono():
    db = _db(_f24("f24-feb", ritenute=38000))
    pid = _deposita(db, _testo())
    run(pc.collega_prospetti(db))
    p = _prospetto(db, pid)
    assert p["esito"] == pc.PARZIALE                       # 4 su 5 al centesimo, la ritenuta e' diversa
    assert next(r for r in p["riscontro"] if r["codice"] == "1001")["esito"] == "DIFFERENZA"

    ambiguo = _db(_f24("a", versamento="2018-03-16", saldo=207145), _f24("b", versamento="2018-03-19", saldo=207145))
    pid = _deposita(ambiguo, _testo())
    run(pc.collega_prospetti(ambiguo))
    p = _prospetto(ambiguo, pid)
    assert p["esito"] == pc.AMBIGUO and p["f24_id"] is None and set(p["candidati"]) == {"a", "b"}


def test_nessun_f24_del_mese_resta_senza_aggancio_e_non_si_inventa():
    altro_mese = _f24("f24-gen")
    for sezione in ("sezione_erario", "sezione_inps", "sezione_regioni", "sezione_tributi_locali"):
        for riga in altro_mese[sezione]:
            riga["mese"] = "01"
            riga["periodo_riferimento"] = "01/" + riga["periodo_riferimento"].split("/")[1]
    db = _db(altro_mese)
    pid = _deposita(db, _testo())
    run(pc.collega_prospetti(db))
    p = _prospetto(db, pid)
    assert p["esito"] == pc.NESSUN_F24 and p["f24_id"] is None


def test_stessa_stampa_una_volta_e_una_stampa_piu_recente_sostituisce_la_vecchia():
    db = _db()
    primo = _deposita(db, _testo(), sha="a" * 64)
    assert _deposita(db, _testo(), sha="a" * 64) == primo                    # idempotente
    corretto = _deposita(db, _testo(ritenute="400,00", stampa="09/03/2018  ALLE : 10:00"), sha="b" * 64)
    assert _prospetto(db, primo)["stato"] == pc.SUPERATO
    nuovo = _prospetto(db, corretto)
    assert nuovo["stato"] == pc.CANONICA and nuovo["sostituisce"] == primo and nuovo["versione"] == 2
    vecchia = _deposita(db, _testo(ritenute="1,00", stampa="01/03/2018  ALLE : 08:00"), sha="c" * 64)
    assert _prospetto(db, vecchia)["stato"] == pc.SUPERATO                    # arriva dopo, ma e' piu' vecchia
    assert _prospetto(db, corretto)["stato"] == pc.CANONICA


def test_l_import_smista_il_prospetto_contabile(monkeypatch):
    from app.routers import documenti

    monkeypatch.setattr(documenti, "_pdf_text_for_detection", lambda _c: _testo())
    assert documenti.detect_document_type("l001170909.pdf", b"%PDF-x") == "prospetto_contabile"
